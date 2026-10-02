"""Los reembolsos contra el motor: solo-inserción, aislamiento, `CHECK`s y concurrencia (ADR-0010).

Lo que ningún doble puede probar vive acá:

- **`reembolso` es solo-inserción**: la aplicación no puede `UPDATE` ni `DELETE` (caso 25).
- **RLS aísla empresas**, y `mp_refund_id` es único **por empresa** (caso 25).
- **Los `CHECK`** son lo que un bug futuro no puede saltear (caso 26).
- **Dos reembolsos simultáneos no superan lo pagado** (caso 27): el `CHECK` solo **no alcanza**
  (dos transacciones que leen acumulado 0 terminan con el acumulado de la última: se pierde una
  actualización y el `CHECK` pasa), así que el test fuerza el solapamiento y afirma que el segundo
  espera al bloqueo `FOR UPDATE` y ve el acumulado nuevo.
- **La suma de las filas es el acumulado** después de cada camino (caso 28).

Necesitan PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from cheatsheet.contexts.payments.application.errors import ReembolsoEnProceso
from cheatsheet.contexts.payments.application.reembolsos import (
    EnviarReembolso,
    SolicitarReembolso,
)
from cheatsheet.contexts.payments.application.reembolsos_manuales import (
    CorregirReembolso,
    RegistrarReembolsoManual,
)
from cheatsheet.contexts.payments.domain.cobro import (
    MENSAJE_REEMBOLSO_EXCEDIDO,
    Cobro,
    EstadoCobro,
    LinkDePago,
    MedioDePago,
)
from cheatsheet.contexts.payments.domain.reembolso import OrigenDeReembolso, Reembolso
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.contexts.payments.infrastructure.repositorio_reembolso import (
    RepositorioReembolsoPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.payments.application.test_confirmacion import (
    PasarelaFalsa,
    PublicadorFalso,
    SaldosFalsos,
)
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
PAGADO = AHORA - timedelta(days=2)
USUARIO = UsuarioId(uuid.uuid4())
ADMIN = RolUsuario.ADMINISTRADOR

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
)
INSERTAR_FILA = text(
    "INSERT INTO reembolso (id, empresa_id, cobro_id, monto, fecha_devolucion, origen, motivo, "
    "corrige_a, mp_refund_id, created_at) "
    "VALUES (:id, :empresa_id, :cobro_id, :monto, :ahora, :origen, :motivo, :corrige_a, "
    ":mp_refund_id, :ahora)"
)


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


async def _cliente(engine_dueno: AsyncEngine, empresa_id: EmpresaId) -> uuid.UUID:
    cliente_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
        )
    return cliente_id


async def _cobro_pagado(
    sesiones: async_sessionmaker[AsyncSession],
    engine_dueno: AsyncEngine,
    empresa_id: EmpresaId,
    *,
    monto: str = "1000.00",
    transferencia: bool = False,
    payment_id: str | None = None,
) -> Cobro:
    """Un cobro pagado y **guardado**, listo para que un reembolso lo toque."""
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = Cobro(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        monto=Decimal(monto),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA - timedelta(days=10),
        updated_at=AHORA - timedelta(days=10),
        medio_de_pago=(
            MedioDePago.TRANSFERENCIA if transferencia else MedioDePago.LINK_MERCADOPAGO
        ),
    )
    preferencia = f"pref-{cobro.id}"
    cobro.asignar_link(
        LinkDePago(preference_id=preferencia, url=f"https://mp.com/{preferencia}"), AHORA
    )
    cobro.aprobar(payment_id=payment_id or f"pago-{cobro.id}", ahora=PAGADO)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioCobroPostgres(sesion).agregar(cobro)
    return cobro


def _fila(
    cobro: Cobro,
    monto: str = "100.00",
    *,
    mp_refund_id: str | None = None,
    corrige_a: uuid.UUID | None = None,
) -> Reembolso:
    return Reembolso(
        id=uuid.uuid4(),
        empresa_id=cobro.empresa_id,
        cobro_id=cobro.id,
        monto=Decimal(monto),
        fecha_devolucion=AHORA,
        origen=OrigenDeReembolso.MANUAL if corrige_a else OrigenDeReembolso.API_MERCADOPAGO,
        created_at=AHORA,
        mp_refund_id=mp_refund_id,
        corrige_a=corrige_a,
        motivo="Se cargo por error" if corrige_a else None,
    )


async def _agregar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, *filas: Reembolso
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioReembolsoPostgres(sesion)
        for fila in filas:
            await repo.agregar(fila)


async def _sql(
    sesiones: async_sessionmaker[AsyncSession],
    empresa_id: EmpresaId,
    sentencia: str,
    **parametros: object,
) -> None:
    """Una sentencia como la aplicación (rol `cheatsheet_app`, con RLS)."""
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await sesion.execute(text(sentencia), parametros)


# ------------------------------------------------------------------ ida y vuelta


async def test_un_reembolso_y_su_correccion_sobreviven_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id, transferencia=True)
    original = Reembolso(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        cobro_id=cobro.id,
        monto=Decimal("250.50"),
        fecha_devolucion=AHORA,
        origen=OrigenDeReembolso.MANUAL,
        created_at=AHORA,
        referencia="OP-77",
        motivo="Devolucion por transferencia",
        registrado_por=USUARIO,
    )
    correccion = _fila(cobro, "-250.50", corrige_a=original.id)
    await _agregar(sesiones, empresa_id, original)
    await _agregar(sesiones, empresa_id, correccion)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioReembolsoPostgres(sesion)
        historial = await repo.de_cobro(cobro.id)
        suelto = await repo.buscar_por_id(original.id)

    assert [f.id for f in historial] == [original.id, correccion.id]
    assert suelto == original
    assert isinstance(historial[0].monto, Decimal)
    assert historial[1].monto == Decimal("-250.50")
    assert historial[1].corrige_a == original.id


# ------------------------------------------------------------------ caso 25: permisos y RLS


async def test_la_aplicacion_no_puede_actualizar_ni_borrar_un_reembolso(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id)
    await _agregar(sesiones, empresa_id, _fila(cobro))

    with pytest.raises(ProgrammingError, match=r"permission denied|permiso denegado"):
        await _sql(sesiones, empresa_id, "UPDATE reembolso SET monto = 1")
    with pytest.raises(ProgrammingError, match=r"permission denied|permiso denegado"):
        await _sql(sesiones, empresa_id, "DELETE FROM reembolso")


async def test_una_empresa_no_ve_ni_escribe_los_reembolsos_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_a)
    fila = _fila(cobro)
    await _agregar(sesiones, empresa_a, fila)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        repo = RepositorioReembolsoPostgres(sesion)
        assert await repo.de_cobro(cobro.id) == []
        assert await repo.buscar_por_id(fila.id) is None
        cuenta = await sesion.execute(text("SELECT count(*) FROM reembolso"))
        assert cuenta.scalar_one() == 0
    # WITH CHECK: anunciar una empresa y escribir la fila de otra se rechaza.
    with pytest.raises(ProgrammingError):
        await _agregar(sesiones, empresa_b, _fila(cobro, "5.00"))


async def test_mp_refund_id_es_unico_por_empresa_y_repetible_en_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Una misma respuesta de MercadoPago, una sola fila (la clave de idempotencia de la
    confirmación); pero otra empresa puede tener el mismo id."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    en_a = await _cobro_pagado(sesiones, engine_dueno, empresa_a)
    en_b = await _cobro_pagado(sesiones, engine_dueno, empresa_b)
    await _agregar(sesiones, empresa_a, _fila(en_a, "10.00", mp_refund_id="ref-1"))

    with pytest.raises(IntegrityError):
        await _agregar(sesiones, empresa_a, _fila(en_a, "20.00", mp_refund_id="ref-1"))
    await _agregar(sesiones, empresa_b, _fila(en_b, "10.00", mp_refund_id="ref-1"))
    # Sin id (los manuales) no hay nada que repetir.
    await _agregar(sesiones, empresa_a, _fila(en_a, "1.00"), _fila(en_a, "2.00"))


async def test_una_fila_se_corrige_una_sola_vez(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El índice único sobre `corrige_a` cierra la carrera de dos correcciones simultáneas."""
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id, transferencia=True)
    original = _fila(cobro, "100.00")
    await _agregar(sesiones, empresa_id, original)
    await _agregar(sesiones, empresa_id, _fila(cobro, "-100.00", corrige_a=original.id))

    with pytest.raises(IntegrityError):
        await _agregar(sesiones, empresa_id, _fila(cobro, "-100.00", corrige_a=original.id))


# ------------------------------------------------------------------ caso 26: los CHECK


def _insertar(
    cobro: Cobro,
    *,
    monto: str,
    origen: str = "API_MERCADOPAGO",
    motivo: str | None = None,
    corrige_a: uuid.UUID | None = None,
) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "empresa_id": cobro.empresa_id,
        "cobro_id": cobro.id,
        "monto": Decimal(monto),
        "ahora": AHORA,
        "origen": origen,
        "motivo": motivo,
        "corrige_a": corrige_a,
        "mp_refund_id": None,
    }


@pytest.mark.parametrize(
    ("monto", "origen", "motivo"),
    [
        pytest.param("0", "API_MERCADOPAGO", None, id="monto-cero"),
        pytest.param("-10.00", "API_MERCADOPAGO", None, id="negativo-sin-correccion"),
        pytest.param("10.00", "OTRO", None, id="origen-invalido"),
        pytest.param("10.00", "MANUAL", None, id="manual-sin-motivo"),
        pytest.param("10.00", "MANUAL", "   ", id="motivo-vacio"),
    ],
)
async def test_el_esquema_rechaza_filas_de_reembolso_invalidas(
    sesiones: async_sessionmaker[AsyncSession],
    engine_dueno: AsyncEngine,
    monto: str,
    origen: str,
    motivo: str | None,
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id)

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                INSERTAR_FILA, _insertar(cobro, monto=monto, origen=origen, motivo=motivo)
            )


async def test_una_correccion_positiva_se_rechaza(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id, transferencia=True)
    original = _fila(cobro, "100.00")
    await _agregar(sesiones, empresa_id, original)

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                INSERTAR_FILA,
                _insertar(
                    cobro,
                    monto="50.00",
                    origen="MANUAL",
                    motivo="Se cargo por error",
                    corrige_a=original.id,
                ),
            )


#: Sentencias literales (no interpoladas), una por regla que el esquema tiene que hacer cumplir.
CAMBIOS_INVALIDOS = [
    pytest.param(
        "UPDATE cobro SET monto_reembolsado = 1500 WHERE id = :id", id="acumulado-sobre-el-monto"
    ),
    pytest.param("UPDATE cobro SET monto_reembolsado = -1 WHERE id = :id", id="acumulado-negativo"),
    pytest.param(
        "UPDATE cobro SET estado = 'REEMBOLSADO_PARCIAL' WHERE id = :id", id="parcial-sin-acumulado"
    ),
    pytest.param(
        "UPDATE cobro SET estado = 'REEMBOLSADO' WHERE id = :id", id="reembolsado-sin-acumulado"
    ),
    pytest.param(
        "UPDATE cobro SET monto_reembolsado = 400 WHERE id = :id",
        id="acumulado-sin-derivar-el-estado",
    ),
    pytest.param(
        "UPDATE cobro SET estado = 'REEMBOLSADO_PARCIAL', monto_reembolsado = 1000 WHERE id = :id",
        id="parcial-por-el-total",
    ),
    pytest.param(
        "UPDATE cobro SET reembolso_solicitado_en = now() WHERE id = :id",
        id="en-vuelo-sin-monto-ni-clave",
    ),
    pytest.param(
        "UPDATE cobro SET reembolso_mp_refund_id = 'ref-1' WHERE id = :id", id="id-sin-solicitud"
    ),
]


@pytest.mark.parametrize("sentencia", CAMBIOS_INVALIDOS)
async def test_el_esquema_rechaza_un_cobro_cuyo_acumulado_o_estado_no_cierran(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine, sentencia: str
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id)

    with pytest.raises(IntegrityError):
        await _sql(sesiones, empresa_id, sentencia, id=cobro.id)


async def test_el_esquema_admite_un_reembolso_parcial_y_el_acumulado_en_cero(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Los dos lados de los `CHECK`: lo que sí entra (incluido el cero de una corrección total)."""
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id)

    await _sql(
        sesiones,
        empresa_id,
        "UPDATE cobro SET estado = 'REEMBOLSADO_PARCIAL', monto_reembolsado = 400 WHERE id = :id",
        id=cobro.id,
    )
    await _sql(
        sesiones,
        empresa_id,
        "UPDATE cobro SET estado = 'APROBADO', monto_reembolsado = 0 WHERE id = :id",
        id=cobro.id,
    )


# ------------------------------------------------------------------ caso 27: concurrencia


class RepositorioQueSostieneElBloqueo(RepositorioCobroPostgres):
    """Agranda la ventana **después** de tomar el bloqueo: mientras esta transacción duerme, la
    otra ya está esperando en la base. Sin `FOR UPDATE` la segunda leería el acumulado viejo."""

    async def buscar_para_actualizar(self, cobro_id: uuid.UUID) -> Cobro | None:
        cobro = await super().buscar_para_actualizar(cobro_id)
        await asyncio.sleep(0.4)
        return cobro


async def _registrar_manual(
    sesiones: async_sessionmaker[AsyncSession], cobro: Cobro, monto: str
) -> Cobro:
    async with sesion_de_empresa(sesiones, cobro.empresa_id) as sesion:
        return await RegistrarReembolsoManual(
            cobros=RepositorioQueSostieneElBloqueo(sesion),
            reembolsos=RepositorioReembolsoPostgres(sesion),
            saldos=SaldosFalsos(),
            publicador=PublicadorFalso(),
        ).ejecutar(
            empresa_id=cobro.empresa_id,
            usuario_id=USUARIO,
            rol=ADMIN,
            cobro_id=cobro.id,
            monto=Decimal(monto),
            dia=date(2026, 9, 7),
            referencia=None,
            motivo="Devolucion por transferencia",
            ahora=AHORA,
        )


async def _suma_y_acumulado(
    engine_dueno: AsyncEngine, cobro_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    async with engine_dueno.connect() as conexion:
        fila = (
            await conexion.execute(
                text(
                    "SELECT COALESCE((SELECT sum(monto) FROM reembolso WHERE cobro_id = c.id), 0), "
                    "c.monto_reembolsado FROM cobro c WHERE c.id = :id"
                ),
                {"id": cobro_id},
            )
        ).one()
    return fila[0], fila[1]


async def test_dos_registros_manuales_concurrentes_que_superan_el_cobro_entran_de_a_uno(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 27: 700 + 700 sobre un cobro de 1000. Uno entra; el otro espera, ve 700 acumulado y
    se rechaza. Sin el bloqueo, los dos leerían 0, los dos entrarían y quedarían 1400 de filas
    contra un acumulado de 700 que el `CHECK` no distingue."""
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id, transferencia=True)

    resultados = await asyncio.gather(
        _registrar_manual(sesiones, cobro, "700.00"),
        _registrar_manual(sesiones, cobro, "700.00"),
        return_exceptions=True,
    )

    aceptados = [r for r in resultados if isinstance(r, Cobro)]
    rechazados = [r for r in resultados if isinstance(r, EntradaInvalida)]
    assert len(aceptados) == 1, resultados
    assert len(rechazados) == 1, resultados
    assert str(rechazados[0]) == MENSAJE_REEMBOLSO_EXCEDIDO
    suma, acumulado = await _suma_y_acumulado(engine_dueno, cobro.id)
    assert suma == acumulado == Decimal("700.00")


async def test_dos_solicitudes_concurrentes_por_api_dejan_una_sola_en_vuelo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La solicitud en vuelo es el mutex del reembolso por API: la segunda espera al bloqueo y la
    ve ya escrita."""
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro_pagado(sesiones, engine_dueno, empresa_id)

    async def solicitar() -> Cobro:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            return await SolicitarReembolso(
                cobros=RepositorioQueSostieneElBloqueo(sesion), publicador=PublicadorFalso()
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=USUARIO,
                rol=ADMIN,
                cobro_id=cobro.id,
                monto=Decimal("100.00"),
                ahora=AHORA,
            )

    resultados = await asyncio.gather(solicitar(), solicitar(), return_exceptions=True)

    assert len([r for r in resultados if isinstance(r, Cobro)]) == 1, resultados
    assert len([r for r in resultados if isinstance(r, ReembolsoEnProceso)]) == 1, resultados


# ------------------------------------------------------------------ caso 28: la suma cierra


async def test_despues_de_cada_camino_la_suma_de_las_filas_es_el_acumulado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """API (T1 + T2), manual y corrección: tres caminos, una sola forma de sumar plata."""
    empresa_id = await _empresa(engine_dueno)
    por_api = await _cobro_pagado(sesiones, engine_dueno, empresa_id)
    manual = await _cobro_pagado(sesiones, engine_dueno, empresa_id, transferencia=True)
    pasarela = PasarelaFalsa()

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await SolicitarReembolso(
            cobros=RepositorioCobroPostgres(sesion), publicador=PublicadorFalso()
        ).ejecutar(
            empresa_id=empresa_id,
            usuario_id=USUARIO,
            rol=ADMIN,
            cobro_id=por_api.id,
            monto=Decimal("400.00"),
            ahora=AHORA,
        )
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        resultado = await EnviarReembolso(
            cobros=RepositorioCobroPostgres(sesion),
            reembolsos=RepositorioReembolsoPostgres(sesion),
            pasarela=pasarela,
            saldos=SaldosFalsos(),
            publicador=PublicadorFalso(),
        ).ejecutar(
            empresa_id=empresa_id, usuario_id=USUARIO, rol=ADMIN, cobro_id=por_api.id, ahora=AHORA
        )
    assert resultado.cobro.estado is EstadoCobro.REEMBOLSADO_PARCIAL
    assert await _suma_y_acumulado(engine_dueno, por_api.id) == (Decimal("400.00"),) * 2

    await _registrar_manual_simple(sesiones, manual, "300.00")
    await _registrar_manual_simple(sesiones, manual, "200.00")
    assert await _suma_y_acumulado(engine_dueno, manual.id) == (Decimal("500.00"),) * 2

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        primera = (await RepositorioReembolsoPostgres(sesion).de_cobro(manual.id))[0]
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await CorregirReembolso(
            cobros=RepositorioCobroPostgres(sesion),
            reembolsos=RepositorioReembolsoPostgres(sesion),
            saldos=SaldosFalsos(),
            publicador=PublicadorFalso(),
        ).ejecutar(
            empresa_id=empresa_id,
            usuario_id=USUARIO,
            rol=ADMIN,
            cobro_id=manual.id,
            reembolso_id=primera.id,
            motivo="Se cargo por error",
            ahora=AHORA,
        )
    assert await _suma_y_acumulado(engine_dueno, manual.id) == (Decimal("200.00"),) * 2


async def _registrar_manual_simple(
    sesiones: async_sessionmaker[AsyncSession], cobro: Cobro, monto: str
) -> None:
    async with sesion_de_empresa(sesiones, cobro.empresa_id) as sesion:
        await RegistrarReembolsoManual(
            cobros=RepositorioCobroPostgres(sesion),
            reembolsos=RepositorioReembolsoPostgres(sesion),
            saldos=SaldosFalsos(),
            publicador=PublicadorFalso(),
        ).ejecutar(
            empresa_id=cobro.empresa_id,
            usuario_id=USUARIO,
            rol=ADMIN,
            cobro_id=cobro.id,
            monto=Decimal(monto),
            dia=date(2026, 9, 7),
            referencia=None,
            motivo="Devolucion por transferencia",
            ahora=AHORA,
        )
