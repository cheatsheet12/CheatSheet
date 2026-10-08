"""Los pagos sin imputar contra el motor (unidad `pagos-sin-cobro-asociado`, casos 12 a 14).

Lo que ningún doble puede probar vive acá:

- **La ida y vuelta** conserva el monto en `NUMERIC(14, 2)` y el motivo (caso 12).
- **`pago_sin_imputar` es solo-inserción** y **RLS aísla empresas**: la empresa B no ve los de A,
  y una `external_reference` con el id de un cobro de A recibida por B queda `SIN_COBRO` en B
  (caso 13).
- **El índice único `(empresa, payment_id)`** deja una fila ante dos notificaciones simultáneas,
  y la que pierde se traduce a «ya registrado» y no a un error (caso 14).
- **Dos pagos distintos sobre el mismo cobro abierto** no lo aprueban los dos: la confirmación lo
  lee con `FOR UPDATE`, el segundo espera y queda `COBRO_YA_PAGADO` (caso 15).
- **Los `CHECK`** que un bug futuro no puede saltear.

Necesitan PostgreSQL: se saltean sin base y corren en CI. **Nunca contra Neon/staging.**
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from cheatsheet.contexts.payments.application.confirmacion import ConfirmarPago
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago
from cheatsheet.contexts.payments.domain.pago_sin_imputar import MotivoSinImputar, PagoSinImputar
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.contexts.payments.infrastructure.repositorio_pago_sin_imputar import (
    RepositorioPagoSinImputarPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
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

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
)
INSERTAR_PAGO = text(
    "INSERT INTO pago_sin_imputar (id, empresa_id, mp_payment_id, cobro_id, motivo, recibido_en) "
    "VALUES (:id, :empresa_id, :pago, :cobro_id, :motivo, :ahora)"
)


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


async def _cobro(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine, empresa_id: EmpresaId
) -> Cobro:
    cliente_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
        )
    cobro = Cobro(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        monto=Decimal("1210.00"),
        descripcion="Consulta de octubre",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA,
    )
    cobro.asignar_link(
        LinkDePago(preference_id=f"pref-{cobro.id}", url="https://mp.com/checkout/x"), AHORA
    )
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioCobroPostgres(sesion).agregar(cobro)
    return cobro


def _pago(
    empresa_id: EmpresaId,
    payment_id: str = "pago-1",
    *,
    motivo: MotivoSinImputar = MotivoSinImputar.SIN_COBRO,
    cobro_id: uuid.UUID | None = None,
    monto: str | None = "1210.005",
) -> PagoSinImputar:
    return PagoSinImputar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        mp_payment_id=payment_id,
        motivo=motivo,
        recibido_en=AHORA,
        referencia_externa=str(uuid.uuid4()),
        cobro_id=cobro_id,
        monto=Decimal(monto) if monto is not None else None,
        fecha_aprobacion=AHORA - timedelta(minutes=1),
    )


async def _agregar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, pago: PagoSinImputar
) -> bool:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        return await RepositorioPagoSinImputarPostgres(sesion).agregar(pago)


async def _cuenta(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, payment_id: str
) -> int:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        resultado = await sesion.execute(
            text("SELECT count(*) FROM pago_sin_imputar WHERE mp_payment_id = :pago"),
            {"pago": payment_id},
        )
        return int(resultado.scalar_one())


# ------------------------------------------------------------------ caso 12: ida y vuelta


async def test_un_pago_sin_imputar_sobrevive_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro(sesiones, engine_dueno, empresa_id)
    pago = _pago(empresa_id, "pago-77", motivo=MotivoSinImputar.COBRO_YA_PAGADO, cobro_id=cobro.id)

    assert await _agregar(sesiones, empresa_id, pago) is True

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioPagoSinImputarPostgres(sesion).buscar_por_payment_id("pago-77")
    assert leido == pago
    assert leido is not None
    assert leido.monto == Decimal("1210.01")
    assert isinstance(leido.monto, Decimal)


async def test_un_pago_sin_monto_vuelve_con_monto_none(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)

    await _agregar(sesiones, empresa_id, _pago(empresa_id, "pago-sin-monto", monto=None))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioPagoSinImputarPostgres(sesion).buscar_por_payment_id(
            "pago-sin-monto"
        )
    assert leido is not None
    assert leido.monto is None


# ------------------------------------------------------------------ caso 13: permisos y RLS


async def test_la_aplicacion_no_puede_actualizar_ni_borrar_un_pago_sin_imputar(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    await _agregar(sesiones, empresa_id, _pago(empresa_id))

    for sentencia in ("UPDATE pago_sin_imputar SET monto = 1", "DELETE FROM pago_sin_imputar"):
        with pytest.raises(ProgrammingError, match=r"permission denied|permiso denegado"):
            async with sesion_de_empresa(sesiones, empresa_id) as sesion:
                await sesion.execute(text(sentencia))


async def test_una_empresa_no_ve_ni_escribe_los_pagos_sin_imputar_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    await _agregar(sesiones, empresa_a, _pago(empresa_a, "pago-de-a"))

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        repo = RepositorioPagoSinImputarPostgres(sesion)
        assert await repo.buscar_por_payment_id("pago-de-a") is None
        cuenta = await sesion.execute(text("SELECT count(*) FROM pago_sin_imputar"))
        assert cuenta.scalar_one() == 0
    # WITH CHECK: anunciar una empresa y escribir la fila de otra se rechaza.
    with pytest.raises(ProgrammingError):
        await _agregar(sesiones, empresa_b, _pago(empresa_a, "pago-cruzado"))


async def test_una_referencia_con_el_cobro_de_otra_empresa_queda_sin_cobro_en_esta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 13. B recibe un pago cuyo `external_reference` es el id de un cobro de A: bajo RLS
    no lo ve, no lo toca y queda registrado como `SIN_COBRO` **en B**."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cobro_de_a = await _cobro(sesiones, engine_dueno, empresa_a)
    publicador = PublicadorFalso()

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        resultado = await ConfirmarPago(
            cobros=RepositorioCobroPostgres(sesion),
            pasarela=PasarelaFalsa(preferencia=None, referencia=str(cobro_de_a.id)),
            saldos=SaldosFalsos(),
            publicador=publicador,
            sin_imputar=RepositorioPagoSinImputarPostgres(sesion),
        ).ejecutar(empresa_id=empresa_b, payment_id="pago-cruzado", ahora=AHORA)

    assert resultado.sin_imputar
    assert await _cuenta(sesiones, empresa_b, "pago-cruzado") == 1
    assert await _cuenta(sesiones, empresa_a, "pago-cruzado") == 0
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        intacto = await RepositorioCobroPostgres(sesion).buscar_por_id(cobro_de_a.id)
    assert intacto is not None
    assert intacto.estado is EstadoCobro.PENDIENTE


# ------------------------------------------------------------------ caso 14: concurrencia


async def test_dos_inserciones_simultaneas_del_mismo_pago_dejan_una_fila(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La segunda espera el índice único de la primera y, al perderlo, devuelve `False`: no
    levanta, porque un 500 haría que MercadoPago reintentara una notificación ya guardada."""
    empresa_id = await _empresa(engine_dueno)

    resultados = await asyncio.gather(
        _agregar(sesiones, empresa_id, _pago(empresa_id, "pago-carrera")),
        _agregar(sesiones, empresa_id, _pago(empresa_id, "pago-carrera")),
    )

    assert sorted(resultados) == [False, True]
    assert await _cuenta(sesiones, empresa_id, "pago-carrera") == 1


async def test_el_mismo_payment_id_se_puede_registrar_en_otra_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    assert await _agregar(sesiones, empresa_a, _pago(empresa_a, "pago-1")) is True
    assert await _agregar(sesiones, empresa_b, _pago(empresa_b, "pago-1")) is True


async def test_otra_violacion_de_integridad_no_se_traga_como_ya_registrado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Solo el índice del pago, por nombre: un cobro inexistente (FK) sigue siendo un error."""
    empresa_id = await _empresa(engine_dueno)
    huerfano = _pago(empresa_id, motivo=MotivoSinImputar.COBRO_YA_PAGADO, cobro_id=uuid.uuid4())

    with pytest.raises(IntegrityError):
        await _agregar(sesiones, empresa_id, huerfano)


# ------------------------------------------------------------------ los CHECK del esquema


@pytest.mark.parametrize(
    ("motivo", "con_cobro"),
    [
        pytest.param("INVENTADO", False, id="motivo-fuera-del-catalogo"),
        pytest.param("SIN_COBRO", True, id="sin-cobro-con-cobro"),
        pytest.param("COBRO_YA_PAGADO", False, id="con-cobro-sin-cobro"),
    ],
)
async def test_el_esquema_rechaza_un_motivo_o_un_cobro_incoherente(
    engine_dueno: AsyncEngine,
    sesiones: async_sessionmaker[AsyncSession],
    motivo: str,
    con_cobro: bool,
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro(sesiones, engine_dueno, empresa_id)

    with pytest.raises(IntegrityError, match=r"ck_pago_sin_imputar"):
        async with engine_dueno.begin() as conexion:
            await conexion.execute(
                INSERTAR_PAGO,
                {
                    "id": uuid.uuid4(),
                    "empresa_id": empresa_id,
                    "pago": "pago-x",
                    "cobro_id": cobro.id if con_cobro else None,
                    "motivo": motivo,
                    "ahora": AHORA,
                },
            )


# ------------------------------------------------------------------ caso 15: dos pagos, un cobro


class RepositorioQueSostieneElBloqueo(RepositorioCobroPostgres):
    """Agranda la ventana **después** de tomar el bloqueo: mientras esta transacción duerme, la
    otra ya está esperando en la base. Sin `FOR UPDATE` la segunda leería el cobro todavía abierto."""

    async def buscar_para_actualizar(self, cobro_id: uuid.UUID) -> Cobro | None:
        cobro = await super().buscar_para_actualizar(cobro_id)
        await asyncio.sleep(0.4)
        return cobro


async def test_dos_pagos_distintos_sobre_el_mismo_cobro_abierto_se_aprueba_uno_solo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 15. Dos webhooks con otro `payment_id` cada uno sobre el mismo cobro abierto. Sin el
    bloqueo los dos lo ven `PENDIENTE`, los dos lo aprueban, el segundo pisa `mp_payment_id` y el
    primer pago nunca queda registrado. Con él, el segundo espera, ve `APROBADO` y su pago queda
    como `COBRO_YA_PAGADO`."""
    empresa_id = await _empresa(engine_dueno)
    cobro = await _cobro(sesiones, engine_dueno, empresa_id)

    async def confirmar(payment_id: str) -> bool:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            resultado = await ConfirmarPago(
                cobros=RepositorioQueSostieneElBloqueo(sesion),
                pasarela=PasarelaFalsa(preferencia=None, referencia=str(cobro.id)),
                saldos=SaldosFalsos(),
                publicador=PublicadorFalso(),
                sin_imputar=RepositorioPagoSinImputarPostgres(sesion),
            ).ejecutar(empresa_id=empresa_id, payment_id=payment_id, ahora=AHORA)
        return resultado.aprobado

    aprobados = await asyncio.gather(confirmar("pago-a"), confirmar("pago-b"))

    assert sorted(aprobados) == [False, True]
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        final = await RepositorioCobroPostgres(sesion).buscar_por_id(cobro.id)
        perdedor = (
            await sesion.execute(
                text("SELECT mp_payment_id, motivo FROM pago_sin_imputar WHERE cobro_id = :id"),
                {"id": cobro.id},
            )
        ).one()
    assert final is not None
    assert final.estado is EstadoCobro.APROBADO
    assert final.mp_payment_id in {"pago-a", "pago-b"}
    assert perdedor.motivo == MotivoSinImputar.COBRO_YA_PAGADO.value
    assert {final.mp_payment_id, perdedor.mp_payment_id} == {"pago-a", "pago-b"}
