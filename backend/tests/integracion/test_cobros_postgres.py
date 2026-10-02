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
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro, MetricasDeCobros
from cheatsheet.contexts.payments.domain.cobro import (
    Cobro,
    EstadoCobro,
    LinkDePago,
    MedioDePago,
)
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
    creado_el: datetime = AHORA,
) -> Cobro:
    cobro = Cobro(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        monto=Decimal(monto),
        descripcion="Consulta de septiembre",
        vence_el=creado_el + timedelta(days=vence_en_dias),
        created_at=creado_el,
        updated_at=creado_el,
    )
    cobro.asignar_link(
        LinkDePago(preference_id=preferencia, url=f"https://mp.com/{preferencia}"), creado_el
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
    assert metricas.cobrado_de_lo_creado == Decimal("1000.00")
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


async def _en(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, filtros: FiltrosDeCobro
) -> MetricasDeCobros:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        return await RepositorioCobroPostgres(sesion).metricas(filtros)


FEBRERO = datetime(2026, 2, 10, 12, 0, tzinfo=UTC)
MARZO = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
TODO_FEBRERO = FiltrosDeCobro(
    desde=datetime(2026, 2, 1, tzinfo=UTC), hasta=datetime(2026, 2, 28, 23, 59, tzinfo=UTC)
)
TODO_MARZO = FiltrosDeCobro(
    desde=datetime(2026, 3, 1, tzinfo=UTC), hasta=datetime(2026, 3, 31, 23, 59, tzinfo=UTC)
)


async def test_un_cobro_creado_en_febrero_y_pagado_en_marzo_suma_en_marzo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**D91.** «Cobrado» es por fecha de pago; la tasa, por lo creado en el período."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id, monto="1000.00", creado_el=FEBRERO)
    cobro.aprobar(payment_id="pago-1", ahora=MARZO, fecha_pago=MARZO)
    await _guardar(sesiones, empresa_id, cobro)

    en_marzo = await _en(sesiones, empresa_id, TODO_MARZO)
    en_febrero = await _en(sesiones, empresa_id, TODO_FEBRERO)

    assert en_marzo.cobrado == Decimal("1000.00")
    # En marzo no se creó nada: la tasa de marzo no puede contar un cobro de febrero.
    assert en_marzo.cobrado_de_lo_creado == Decimal("0.00")
    assert en_marzo.tasa_de_cobro == Decimal("0.00")
    assert en_febrero.cobrado == Decimal("0.00")
    # La tasa de febrero (cohorte) sí lo incluye, aunque se haya pagado después.
    assert en_febrero.cobrado_de_lo_creado == Decimal("1000.00")
    assert en_febrero.tasa_de_cobro == Decimal("100.00")


async def test_la_tasa_no_pasa_de_cien_aunque_se_cobre_mas_de_lo_creado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    viejo = _cobro(empresa_id, cliente_id, monto="9000.00", creado_el=FEBRERO, preferencia="p1")
    viejo.aprobar(payment_id="pago-1", ahora=MARZO, fecha_pago=MARZO)
    nuevo = _cobro(empresa_id, cliente_id, monto="100.00", creado_el=MARZO, preferencia="p2")
    nuevo.aprobar(payment_id="pago-2", ahora=MARZO + timedelta(hours=1))
    await _guardar(sesiones, empresa_id, viejo, nuevo)

    metricas = await _en(sesiones, empresa_id, TODO_MARZO)

    assert metricas.cobrado == Decimal("9100.00")
    assert metricas.tasa_de_cobro == Decimal("100.00")


async def test_un_reembolsado_no_suma_en_cobrado_de_ningun_periodo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Limitación conocida, fijada acá: la unidad de reembolsos lo resta por fecha de devolución."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id, monto="1000.00", creado_el=FEBRERO)
    cobro.aprobar(payment_id="pago-1", ahora=FEBRERO + timedelta(days=1))
    cobro.confirmar_reembolso(monto=Decimal("1000.00"), ahora=MARZO)
    await _guardar(sesiones, empresa_id, cobro)

    assert (await _en(sesiones, empresa_id, TODO_FEBRERO)).cobrado == Decimal("0.00")
    assert (await _en(sesiones, empresa_id, TODO_MARZO)).cobrado == Decimal("0.00")


async def test_pendiente_y_en_mora_siguen_por_creacion_y_el_estado_no_altera_las_metricas(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    pendiente = _cobro(empresa_id, cliente_id, monto="500.00", creado_el=FEBRERO, preferencia="a")
    moroso = _cobro(empresa_id, cliente_id, monto="250.00", creado_el=FEBRERO, preferencia="b")
    moroso.vencer(MARZO)
    pagado = _cobro(empresa_id, cliente_id, monto="100.00", creado_el=MARZO, preferencia="c")
    pagado.aprobar(payment_id="pago-1", ahora=MARZO + timedelta(hours=1))
    await _guardar(sesiones, empresa_id, pendiente, moroso, pagado)
    solo_pagados = FiltrosDeCobro(
        desde=TODO_FEBRERO.desde, hasta=TODO_FEBRERO.hasta, estados=(EstadoCobro.APROBADO,)
    )

    sin_estado = await _en(sesiones, empresa_id, TODO_FEBRERO)
    con_estado = await _en(sesiones, empresa_id, solo_pagados)

    assert sin_estado.pendiente == Decimal("500.00")
    assert sin_estado.en_mora == Decimal("250.00")
    assert con_estado == sin_estado


async def test_los_importes_de_las_metricas_son_decimal_sin_error_binario(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`0.10 + 0.20` da `0.30` y nunca `0.30000000000000004`: se suma en NUMERIC."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    uno = _cobro(empresa_id, cliente_id, monto="0.10", preferencia="a")
    otro = _cobro(empresa_id, cliente_id, monto="0.20", preferencia="b")
    uno.aprobar(payment_id="pago-1", ahora=AHORA)
    otro.aprobar(payment_id="pago-2", ahora=AHORA)
    await _guardar(sesiones, empresa_id, uno, otro)

    metricas = await _en(sesiones, empresa_id, FiltrosDeCobro())

    assert metricas.cobrado == Decimal("0.30")
    assert isinstance(metricas.cobrado, Decimal)
    assert isinstance(metricas.cobrado_de_lo_creado, Decimal)


async def test_el_cobrado_de_una_empresa_no_suma_los_pagos_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RLS también acota la agregación por fecha de pago."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente_a = await _cliente(engine_dueno, empresa_a)
    cliente_b = await _cliente(engine_dueno, empresa_b)
    de_a = _cobro(empresa_a, cliente_a, monto="1000.00")
    de_a.aprobar(payment_id="pago-a", ahora=AHORA)
    de_b = _cobro(empresa_b, cliente_b, monto="70.00")
    de_b.aprobar(payment_id="pago-b", ahora=AHORA)
    await _guardar(sesiones, empresa_a, de_a)
    await _guardar(sesiones, empresa_b, de_b)

    assert (await _en(sesiones, empresa_a, FiltrosDeCobro())).cobrado == Decimal("1000.00")
    assert (await _en(sesiones, empresa_b, FiltrosDeCobro())).cobrado == Decimal("70.00")


# ------------------------------------------------- la fecha, el medio y la operación · ADR-0010


async def test_la_fecha_el_medio_y_la_operacion_sobreviven_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    pagado_el = AHORA + timedelta(hours=1)
    exacto = _cobro(empresa_id, cliente_id, preferencia="a")
    exacto.aprobar(payment_id="pago-1", ahora=pagado_el + timedelta(days=1), fecha_pago=pagado_el)
    aproximado = _cobro(empresa_id, cliente_id, preferencia="b")
    aproximado.aprobar(payment_id="pago-2", ahora=pagado_el)
    transferido = _cobro(empresa_id, cliente_id, preferencia="c")
    transferido.aprobar(payment_id="pago-3", ahora=pagado_el)
    transferido.medio_de_pago = MedioDePago.TRANSFERENCIA
    transferido.numero_de_operacion = "0000123456"
    await _guardar(sesiones, empresa_id, exacto, aproximado, transferido)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioCobroPostgres(sesion)
        leido_exacto = await repo.buscar_por_id(exacto.id)
        leido_aproximado = await repo.buscar_por_id(aproximado.id)
        leido_transferido = await repo.buscar_por_id(transferido.id)

    assert leido_exacto is not None
    assert leido_exacto.fecha_pago == pagado_el
    assert leido_exacto.fecha_pago_aproximada is False
    assert leido_exacto.medio_de_pago is MedioDePago.LINK_MERCADOPAGO
    assert leido_exacto.numero_de_operacion is None
    assert leido_aproximado is not None
    assert leido_aproximado.fecha_pago_aproximada is True
    assert leido_transferido is not None
    assert leido_transferido.medio_de_pago is MedioDePago.TRANSFERENCIA
    assert leido_transferido.numero_de_operacion == "0000123456"


async def test_un_numero_de_operacion_no_puede_repetir_el_pago_de_otro_cobro(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E6-08 RN-03: la unicidad cubre también los pagos recibidos por link."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    por_link = _cobro(empresa_id, cliente_id, preferencia="a")
    por_link.aprobar(payment_id="123456", ahora=AHORA)
    await _guardar(sesiones, empresa_id, por_link)
    transferido = _cobro(empresa_id, cliente_id, preferencia="b")
    transferido.aprobar(payment_id="pago-2", ahora=AHORA)
    transferido.medio_de_pago = MedioDePago.TRANSFERENCIA
    transferido.numero_de_operacion = "123456"

    with pytest.raises(IntegrityError):
        await _guardar(sesiones, empresa_id, transferido)


async def test_el_mismo_numero_de_operacion_en_otra_empresa_convive(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente_a = await _cliente(engine_dueno, empresa_a)
    cliente_b = await _cliente(engine_dueno, empresa_b)
    por_link = _cobro(empresa_a, cliente_a)
    por_link.aprobar(payment_id="123456", ahora=AHORA)
    transferido = _cobro(empresa_b, cliente_b)
    transferido.aprobar(payment_id="pago-2", ahora=AHORA)
    transferido.medio_de_pago = MedioDePago.TRANSFERENCIA
    transferido.numero_de_operacion = "123456"

    await _guardar(sesiones, empresa_a, por_link)
    await _guardar(sesiones, empresa_b, transferido)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        assert await RepositorioCobroPostgres(sesion).buscar_por_id(transferido.id) is not None


async def test_un_medio_de_pago_fuera_del_conjunto_lo_rechaza_el_esquema(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    await _guardar(sesiones, empresa_id, cobro)

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("UPDATE cobro SET medio_de_pago = 'EFECTIVO' WHERE id = :id"),
                {"id": cobro.id},
            )


async def test_un_aprobado_sin_fecha_de_pago_lo_rechaza_el_esquema(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`ck_cobro_fecha_de_pago` es `NOT VALID` pero protege toda escritura nueva."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    await _guardar(sesiones, empresa_id, cobro)

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("UPDATE cobro SET estado = 'APROBADO' WHERE id = :id"), {"id": cobro.id}
            )


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


# ------------------------------------------------------- la cancelacion y el pago huerfano


async def test_una_cancelacion_que_falla_no_deja_rastro_en_la_base(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E6-04 RN-03, contra el motor.

    En memoria esto no se puede afirmar: los dobles guardan la referencia que el caso de uso
    ya muto. Lo que hace verdadera la promesa —«si MercadoPago no invalida, el cobro queda
    como estaba»— es que el repositorio **reconstituye** un objeto aparte de la fila, asi que
    mutar el agregado no escribe nada hasta `guardar`. Eso es lo que se prueba aca.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    await _guardar(sesiones, empresa_id, cobro)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioCobroPostgres(sesion)
        leido = await repo.buscar_por_id(cobro.id)
        assert leido is not None
        # Lo que hace `CancelarCobro` antes de hablar con MercadoPago. Si la invalidacion
        # levanta, `guardar` nunca llega a correr.
        leido.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        despues = await RepositorioCobroPostgres(sesion).buscar_por_id(cobro.id)

    assert despues is not None
    assert despues.estado is EstadoCobro.PENDIENTE
    assert despues.motivo_de_cancelacion is None
    assert despues.tiene_link_activo


async def test_un_pago_huerfano_sobrevive_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El cobro sigue CANCELADO y la plata queda atada a su fila."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id)
    cobro.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)
    cobro.registrar_pago_huerfano(payment_id="pago-huerfano", ahora=AHORA)
    await _guardar(sesiones, empresa_id, cobro)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioCobroPostgres(sesion).buscar_por_id(cobro.id)

    assert leido is not None
    assert leido.estado is EstadoCobro.CANCELADO
    assert leido.mp_payment_id == "pago-huerfano"
    assert leido.tiene_pago_huerfano
    # La preferencia se conserva: es el rastro que alguien sigue para encontrar la plata.
    assert leido.link is not None


async def test_el_pago_huerfano_usa_el_mismo_indice_unico_que_la_aprobacion(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """D20 cubre tambien este caso, y sin agregar nada: es la misma columna.

    Un `payment_id` no puede estar en dos cobros, sea porque uno lo aprobo o porque el otro
    lo recibio sobre un link cancelado.
    """
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    aprobado = _cobro(empresa_id, cliente_id, preferencia="pref-a")
    aprobado.aprobar(payment_id="pago-compartido", ahora=AHORA)
    cancelado = _cobro(empresa_id, cliente_id, preferencia="pref-b")
    cancelado.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)
    cancelado.registrar_pago_huerfano(payment_id="pago-compartido", ahora=AHORA)

    with pytest.raises(IntegrityError):
        await _guardar(sesiones, empresa_id, aprobado, cancelado)
