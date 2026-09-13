"""Los cobros contra el motor: aislamiento, idempotencia y los dos índices que la sostienen.

**Los dos índices únicos son el corazón del épico** y ninguno existe fuera de PostgreSQL:

1. `uq_cobro_mp_payment_id` — decisión **D20**. Una clave en Redis protege durante su TTL y
   deja de proteger justo cuando llega la notificación tardía; esto protege siempre y
   sobrevive a un `FLUSHALL`.
2. `uq_recordatorio_cobro_paso` — decisión **D25**. Es lo que atrapa a dos barridos solapados
   calculando el mismo paso a la vez, que es el caso que HS-T3 RN-05 describe.

Los dos se prueban a la manera que este repositorio ya usó con D14: **intentando el
duplicado**, no confiando en que el código no lo intente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from cheatsheet.contexts.business_config.domain.regla import (
    CanalNotificacion,
    ConfiguracionDeEscalamiento,
    PasoDeEscalamiento,
    ReglaDeNegocio,
    TipoRegla,
)
from cheatsheet.contexts.business_config.infrastructure.repositories import (
    RepositorioReglasPostgres,
)
from cheatsheet.contexts.payments.application.errors import RecordatorioDuplicado
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.contexts.payments.infrastructure.repositories import (
    RepositorioCobroPostgres,
    RepositorioRecordatoriosPostgres,
    empresas_con_cobros_abiertos,
)
from cheatsheet.platform.database import sesion_de_empresa, sesion_sin_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
UN_LINK = LinkDePago(preference_id="pref-1", url="https://mp.com/checkout/pref-1")

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
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


def _cobro(
    empresa_id: EmpresaId,
    cliente_id: uuid.UUID,
    *,
    monto: str = "1210.00",
    vence_en_dias: int = 30,
    preferencia: str = "pref-1",
) -> Cobro:
    cobro = Cobro(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        monto=Decimal(monto),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=vence_en_dias),
        created_at=AHORA,
        updated_at=AHORA,
    )
    cobro.asignar_link(
        LinkDePago(preference_id=preferencia, url=f"https://mp.com/{preferencia}"), AHORA
    )
    return cobro


async def _guardar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, *cobros: Cobro
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioCobroPostgres(sesion)
        for cobro in cobros:
            await repo.agregar(cobro)


# ------------------------------------------------------------------ ida y vuelta


async def test_un_cobro_sobrevive_entero_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Los montos vuelven como `Decimal` con dos decimales, no como `float`.

    Es el test que ata `CLAUDE.md` §3.5 al esquema: si alguien cambiara la columna a `FLOAT`,
    esto se caería con un total que difiere en el cuarto decimal.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    await _guardar(sesiones, empresa_id, cobro)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioCobroPostgres(sesion).buscar_por_id(cobro.id)

    assert leido is not None
    assert leido.monto == Decimal("1210.00")
    assert isinstance(leido.monto, Decimal)
    assert leido.estado is EstadoCobro.APROBADO
    assert leido.mp_payment_id == "pago-1"
    # La preferencia sobrevive a la aprobación: es lo que ata una notificación tardía.
    assert leido.link is not None
    assert leido.link.preference_id == "pref-1"
    assert not leido.tiene_link_activo


# ------------------------------------------------------------------ idempotencia · D20


async def test_dos_cobros_no_pueden_registrar_el_mismo_pago(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**La decisión D20, hecha esquema.**

    Se prueba intentando el duplicado y no confiando en que el código no lo intente: es la
    misma forma con la que el épico 5 probó D14, y acá lo que está en juego es una deuda dada
    por saldada dos veces.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    uno = _cobro(empresa_id, cliente_id, preferencia="pref-1")
    otro = _cobro(empresa_id, cliente_id, preferencia="pref-2")
    uno.aprobar(payment_id="pago-1", ahora=AHORA)
    otro.aprobar(payment_id="pago-1", ahora=AHORA)

    await _guardar(sesiones, empresa_id, uno)

    with pytest.raises(IntegrityError):
        await _guardar(sesiones, empresa_id, otro)


async def test_dos_cobros_sin_pagar_no_son_un_duplicado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El índice es parcial: `WHERE mp_payment_id IS NOT NULL`.

    Sin eso, el segundo cobro pendiente chocaría contra el primero por tener los dos el campo
    en `NULL` — y una pantalla que no deja generar un segundo cobro es difícil de diagnosticar
    como «índice mal declarado».
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)

    await _guardar(
        sesiones,
        empresa_id,
        _cobro(empresa_id, cliente_id, preferencia="pref-1"),
        _cobro(empresa_id, cliente_id, preferencia="pref-2"),
    )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        todos = await RepositorioCobroPostgres(sesion).listar(FiltrosDeCobro())
    assert len(todos) == 2


async def test_el_mismo_payment_id_en_dos_empresas_convive(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El índice es por `(empresa_id, mp_payment_id)`: dos cuentas de MercadoPago distintas
    pueden repetir un id, y eso no es un duplicado nuestro."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente_a = await _cliente(engine_dueno, empresa_a)
    cliente_b = await _cliente(engine_dueno, empresa_b)

    for empresa, cliente in ((empresa_a, cliente_a), (empresa_b, cliente_b)):
        cobro = _cobro(empresa, cliente)
        cobro.aprobar(payment_id="pago-1", ahora=AHORA)
        await _guardar(sesiones, empresa, cobro)

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        assert len(await RepositorioCobroPostgres(sesion).listar(FiltrosDeCobro())) == 1


async def test_buscar_por_payment_id_encuentra_el_cobro(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La primera línea de la idempotencia: una consulta antes de hablar con MercadoPago."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    await _guardar(sesiones, empresa_id, cobro)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioCobroPostgres(sesion)
        assert (await repo.buscar_por_payment_id("pago-1")) is not None
        assert (await repo.buscar_por_preference_id("pref-1")) is not None
        assert (await repo.buscar_por_payment_id("pago-ajeno")) is None


# ------------------------------------------------------------------ el paso · D25


async def test_un_cobro_no_recibe_dos_veces_el_mismo_paso(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**La decisión D25, hecha esquema** (HS-T3 RN-05).

    El dominio calcula cuál falta; esto atrapa a dos barridos solapados que calcularon lo
    mismo a la vez. Sin la segunda capa, dos workers concurrentes mandan el mismo mensaje.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    await _guardar(sesiones, empresa_id, cobro)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioRecordatoriosPostgres(sesion).agregar(
            Recordatorio(id=uuid.uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
        )

    with pytest.raises(RecordatorioDuplicado):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioRecordatoriosPostgres(sesion).agregar(
                Recordatorio(id=uuid.uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
            )


async def test_los_pasos_distintos_conviven_y_vuelven_ordenados(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    await _guardar(sesiones, empresa_id, cobro)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioRecordatoriosPostgres(sesion)
        for paso in (3, 1, 2):
            uno = Recordatorio(id=uuid.uuid4(), cobro_id=cobro.id, paso=paso, canal="WHATSAPP")
            uno.marcar_enviado(AHORA)
            uno.marcar_entrega(EstadoEntrega.ENTREGADO)
            await repo.agregar(uno)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leidos = await RepositorioRecordatoriosPostgres(sesion).de_cobro(cobro.id)

    assert [uno.paso for uno in leidos] == [1, 2, 3]
    assert leidos[0].estado_entrega is EstadoEntrega.ENTREGADO


# ------------------------------------------------------------------ el aislamiento


async def test_una_empresa_no_ve_los_cobros_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Un cobro lleva el monto y el concepto de una deuda de un tercero."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente_a = await _cliente(engine_dueno, empresa_a)
    cobro = _cobro(empresa_a, cliente_a)
    await _guardar(sesiones, empresa_a, cobro)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        repo = RepositorioCobroPostgres(sesion)
        assert await repo.buscar_por_id(cobro.id) is None
        assert await repo.listar(FiltrosDeCobro()) == []
        assert await repo.buscar_por_payment_id("pago-1") is None


async def test_los_recordatorios_tampoco_cruzan_la_frontera(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`recordatorio` no tiene `empresa_id` propio: su política pasa por el padre.

    Es la parte de la migración más fácil de equivocar, porque una tabla sin `empresa_id`
    *parece* global.
    """
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente_a = await _cliente(engine_dueno, empresa_a)
    cobro = _cobro(empresa_a, cliente_a)
    await _guardar(sesiones, empresa_a, cobro)
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        await RepositorioRecordatoriosPostgres(sesion).agregar(
            Recordatorio(id=uuid.uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
        )

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        filas = await sesion.execute(text("SELECT count(*) FROM recordatorio"))
    assert filas.scalar_one() == 0


async def test_no_se_puede_borrar_un_cobro(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Un cobro aprobado es plata que entró: se reembolsa, no se borra."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    await _guardar(sesiones, empresa_id, cobro)

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(text("DELETE FROM cobro WHERE id = :id"), {"id": cobro.id})


# ------------------------------------------------------------------ los CHECK


async def test_un_reembolso_mayor_al_monto_lo_rechaza_el_esquema(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E6-05 RN-02 en el esquema. El agregado ya lo impone; esto es lo que un bug futuro
    no puede saltear, y devolver de más es plata que sale de otra cuenta."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    await _guardar(sesiones, empresa_id, cobro)

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("UPDATE cobro SET monto_reembolsado = 99999 WHERE id = :id"),
                {"id": cobro.id},
            )


# ------------------------------------------------------------------ los barridos


async def test_el_barrido_ve_las_empresas_con_algo_abierto_y_nada_mas(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La séptima función `SECURITY DEFINER`. Corre **sin empresa declarada** —tiene que, o
    vería una sola— y por eso importa tanto lo que devuelve: ids y nada más."""
    con_deuda = await _empresa(engine_dueno)
    sin_deuda = await _empresa(engine_dueno)
    cliente_uno = await _cliente(engine_dueno, con_deuda)
    cliente_dos = await _cliente(engine_dueno, sin_deuda)

    await _guardar(sesiones, con_deuda, _cobro(con_deuda, cliente_uno))
    pagado = _cobro(sin_deuda, cliente_dos)
    pagado.aprobar(payment_id="pago-9", ahora=AHORA)
    await _guardar(sesiones, sin_deuda, pagado)

    async with sesion_sin_empresa(sesiones) as sesion:
        empresas = await empresas_con_cobros_abiertos(sesion)

    assert con_deuda in empresas
    assert sin_deuda not in empresas


async def test_los_vencidos_se_encuentran_por_fecha_y_estado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    vencido = _cobro(empresa_id, cliente_id, vence_en_dias=1, preferencia="pref-1")
    vigente = _cobro(empresa_id, cliente_id, vence_en_dias=60, preferencia="pref-2")
    await _guardar(sesiones, empresa_id, vencido, vigente)
    despues = AHORA + timedelta(days=2)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        candidatos = await RepositorioCobroPostgres(sesion).abiertos_vencidos_a(despues)

    assert [uno.id for uno in candidatos] == [vencido.id]


# ------------------------------------------------------------------ las métricas


async def test_las_metricas_se_suman_en_la_base(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-01. Sumarlas en Python sobre el listado mostraría un total que cambia al paginar."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)

    pagado = _cobro(empresa_id, cliente_id, monto="1000.00", preferencia="pref-1")
    pagado.aprobar(payment_id="pago-1", ahora=AHORA)
    pendiente = _cobro(empresa_id, cliente_id, monto="500.00", preferencia="pref-2")
    moroso = _cobro(empresa_id, cliente_id, monto="250.00", preferencia="pref-3")
    moroso.vencer(AHORA)
    await _guardar(sesiones, empresa_id, pagado, pendiente, moroso)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        metricas = await RepositorioCobroPostgres(sesion).metricas(FiltrosDeCobro())

    assert metricas.cobrado == Decimal("1000.00")
    assert metricas.pendiente == Decimal("500.00")
    assert metricas.en_mora == Decimal("250.00")
    # 1000 sobre 1750.
    assert metricas.tasa_de_cobro == Decimal("57.14")


async def test_sin_cobros_la_tasa_es_cero_y_no_rompe(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Un período sin cobros tiene tasa cero, no tasa indefinida.

    Una pantalla que muestra «—» donde debería ir un número lleva a alguien a pensar que el
    sistema falló.
    """
    empresa_id = await _empresa(engine_dueno)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        metricas = await RepositorioCobroPostgres(sesion).metricas(FiltrosDeCobro())

    assert metricas.tasa_de_cobro == Decimal("0.00")


# ------------------------------------------------------------------ las reglas


async def test_una_regla_sobrevive_a_la_ida_y_vuelta_con_su_jsonb(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El JSONB reasignado y no mutado en el lugar: SQLAlchemy no rastrea lo segundo, y una
    configuración que falla en guardarse es una cadena que sigue con la parametrización
    vieja."""
    empresa_id = await _empresa(engine_dueno)
    cadena = ConfiguracionDeEscalamiento(
        pasos=(
            PasoDeEscalamiento(dias=5, canal=CanalNotificacion.WHATSAPP),
            PasoDeEscalamiento(dias=12, canal=CanalNotificacion.EMAIL),
        )
    )
    regla = ReglaDeNegocio(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        tipo=TipoRegla.ESCALAMIENTO_DE_COBRO,
        configuracion=cadena.como_json(),
        created_at=AHORA,
    )
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioReglasPostgres(sesion).agregar(regla)

    regla.reconfigurar(
        ConfiguracionDeEscalamiento(
            pasos=(PasoDeEscalamiento(dias=1, canal=CanalNotificacion.PANEL),)
        ).como_json(),
        AHORA,
    )
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioReglasPostgres(sesion).guardar(regla)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leida = await RepositorioReglasPostgres(sesion).buscar_por_id(regla.id)

    assert leida is not None
    pasos = leida.interpretada_como_escalamiento().pasos
    assert [(paso.dias, paso.canal) for paso in pasos] == [(1, CanalNotificacion.PANEL)]


async def test_una_empresa_no_ve_las_reglas_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    regla = ReglaDeNegocio(
        id=uuid.uuid4(),
        empresa_id=empresa_a,
        tipo=TipoRegla.ESCALAMIENTO_DE_COBRO,
        configuracion={"pasos": [{"dias": 3, "canal": "WHATSAPP"}]},
        created_at=AHORA,
    )
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        await RepositorioReglasPostgres(sesion).agregar(regla)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        assert await RepositorioReglasPostgres(sesion).listar() == []


async def test_no_se_puede_borrar_una_regla(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-04 pide desactivar. Una regla borrada deja la bitácora apuntando a la nada."""
    empresa_id = await _empresa(engine_dueno)
    regla = ReglaDeNegocio(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        tipo=TipoRegla.ESCALAMIENTO_DE_COBRO,
        configuracion={"pasos": [{"dias": 3, "canal": "WHATSAPP"}]},
        created_at=AHORA,
    )
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioReglasPostgres(sesion).agregar(regla)

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("DELETE FROM regla_de_negocio WHERE id = :id"), {"id": regla.id}
            )
