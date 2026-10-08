"""Los recordatorios de turno contra PostgreSQL: RLS, idempotencia y consultas del barrido.

Lo que ningún doble en memoria puede probar:

- **Aislamiento** (caso 15): la tabla tiene RLS por `empresa_id`; una empresa no ve las filas de
  otra y sin empresa declarada no se ve nada.
- **Idempotencia** (caso 17): el índice único rechaza la segunda fila de la misma clave, el
  repositorio lo traduce a `RecordatorioDeTurnoDuplicado` y la transacción sigue usable.
  También con dos transacciones concurrentes de verdad.
- **`franja_asignada_en`** viaja entre el dominio y la base al reservar y al reprogramar.
- **Las consultas del barrido**: los turnos abiertos de un rango y las filas pendientes.

Necesitan PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cheatsheet.contexts.scheduling.application.errors import RecordatorioDeTurnoDuplicado
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    RecordatorioDeTurno,
    ResultadoDeRecordatorio,
)
from cheatsheet.contexts.scheduling.domain.recurso import RecursoReservable, TipoRecurso
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno, Franja, Turno
from cheatsheet.contexts.scheduling.infrastructure.repositories import (
    RepositorioRecursoPostgres,
    RepositorioTurnoPostgres,
)
from cheatsheet.contexts.scheduling.infrastructure.repositorio_de_recordatorios import (
    RepositorioRecordatoriosDeTurnoPostgres,
    empresas_con_turnos_por_recordar,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
INICIO = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
H = 60

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
)
CREAR_SERVICIO = text(
    "INSERT INTO servicio (id, empresa_id, nombre, precio, alicuota_iva, agendable, "
    "duracion_estandar_min, origen, presente_en_planilla, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Corte', 1000.00, 0.2100, true, 30, 'PANEL', false, true, "
    ":ahora, :ahora)"
)


class Escenario:
    """Una empresa con un cliente, un servicio y un recurso."""

    def __init__(
        self, empresa_id: EmpresaId, cliente_id: uuid.UUID, servicio_id: uuid.UUID
    ) -> None:
        self.empresa_id = empresa_id
        self.cliente_id = cliente_id
        self.servicio_id = servicio_id
        self.recurso_id = uuid.uuid4()

    def turno(self, inicio: datetime = INICIO, **cambios: object) -> Turno:
        base: dict[str, object] = {
            "id": uuid.uuid4(),
            "empresa_id": self.empresa_id,
            "cliente_id": self.cliente_id,
            "servicio_id": self.servicio_id,
            "recurso_id": self.recurso_id,
            "franja": Franja(inicio=inicio, duracion_min=30),
            "created_at": AHORA,
            "updated_at": AHORA,
            "franja_asignada_en": AHORA,
        }
        base.update(cambios)
        return Turno(**base)  # type: ignore[arg-type]

    def recordatorio(self, turno: Turno, horas: int = 24, **cambios: object) -> RecordatorioDeTurno:
        base: dict[str, object] = {
            "id": uuid.uuid4(),
            "empresa_id": self.empresa_id,
            "turno_id": turno.id,
            "anticipacion_min": horas * H,
            "franja_inicio": turno.franja.inicio,
            "created_at": AHORA,
        }
        base.update(cambios)
        return RecordatorioDeTurno(**base)  # type: ignore[arg-type]


async def _escenario(
    engine_dueno: AsyncEngine, sesiones: async_sessionmaker[AsyncSession]
) -> Escenario:
    empresa_id = EmpresaId(uuid.uuid4())
    cliente_id, servicio_id = uuid.uuid4(), uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
        )
        await conexion.execute(
            CREAR_SERVICIO, {"id": servicio_id, "empresa_id": empresa_id, "ahora": AHORA}
        )
    escenario = Escenario(empresa_id, cliente_id, servicio_id)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioRecursoPostgres(sesion).agregar(
            RecursoReservable(
                id=escenario.recurso_id,
                empresa_id=empresa_id,
                nombre="Consultorio 1",
                tipo=TipoRecurso.ESPACIO,
                servicios=frozenset({servicio_id}),
                created_at=AHORA,
            )
        )
    return escenario


async def _guardar_turno(
    sesiones: async_sessionmaker[AsyncSession], escenario: Escenario, turno: Turno
) -> None:
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        await RepositorioTurnoPostgres(sesion).agregar(turno)


async def _agregar(
    sesiones: async_sessionmaker[AsyncSession],
    escenario: Escenario,
    recordatorio: RecordatorioDeTurno,
) -> None:
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        await RepositorioRecordatoriosDeTurnoPostgres(sesion).agregar(recordatorio)


async def test_ida_y_vuelta_de_una_fila_y_de_la_franja_asignada(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    escenario = await _escenario(engine_dueno, sesiones)
    turno = escenario.turno(franja_asignada_en=AHORA - timedelta(days=1))
    await _guardar_turno(sesiones, escenario, turno)
    fila = escenario.recordatorio(turno)
    fila.iniciar_intento(AHORA)
    await _agregar(sesiones, escenario, fila)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        leido = await RepositorioTurnoPostgres(sesion).buscar_por_id(turno.id)
        filas = await RepositorioRecordatoriosDeTurnoPostgres(sesion).de_turnos([turno.id])

    assert leido is not None
    assert leido.franja_asignada_en == AHORA - timedelta(days=1)
    assert filas == [fila]


async def test_reprogramar_persiste_cuando_se_fijo_la_franja_nueva(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    escenario = await _escenario(engine_dueno, sesiones)
    turno = escenario.turno()
    await _guardar_turno(sesiones, escenario, turno)
    movido_en = AHORA + timedelta(hours=3)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        repositorio = RepositorioTurnoPostgres(sesion)
        cargado = await repositorio.buscar_por_id(turno.id)
        assert cargado is not None
        cargado.reprogramar(
            Franja(inicio=INICIO + timedelta(days=1), duracion_min=30), 0, movido_en
        )
        await repositorio.guardar(cargado)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        leido = await RepositorioTurnoPostgres(sesion).buscar_por_id(turno.id)
    assert leido is not None
    assert leido.franja_asignada_en == movido_en


async def test_una_empresa_no_ve_los_recordatorios_de_otra_y_sin_empresa_no_se_ve_nada(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 15."""
    a = await _escenario(engine_dueno, sesiones)
    b = await _escenario(engine_dueno, sesiones)
    turno_a = a.turno()
    await _guardar_turno(sesiones, a, turno_a)
    await _agregar(sesiones, a, a.recordatorio(turno_a))

    async with sesion_de_empresa(sesiones, b.empresa_id) as sesion:
        vistas_por_b = await RepositorioRecordatoriosDeTurnoPostgres(sesion).de_turnos([turno_a.id])
    async with sesiones() as sin_empresa:
        cuantas = (
            await sin_empresa.execute(text("SELECT count(*) FROM recordatorio_de_turno"))
        ).scalar_one()

    assert vistas_por_b == []
    assert cuantas == 0


async def test_la_app_no_puede_insertar_un_recordatorio_de_otra_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El `WITH CHECK` de la política: declarar la empresa B y escribir en la A se rechaza."""
    a = await _escenario(engine_dueno, sesiones)
    b = await _escenario(engine_dueno, sesiones)
    turno_a = a.turno()
    await _guardar_turno(sesiones, a, turno_a)

    with pytest.raises(Exception, match="row-level security"):
        async with sesion_de_empresa(sesiones, b.empresa_id) as sesion:
            await RepositorioRecordatoriosDeTurnoPostgres(sesion).agregar(a.recordatorio(turno_a))


async def test_la_misma_clave_levanta_duplicado_y_la_transaccion_sigue_usable(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 17."""
    escenario = await _escenario(engine_dueno, sesiones)
    turno = escenario.turno()
    await _guardar_turno(sesiones, escenario, turno)
    await _agregar(sesiones, escenario, escenario.recordatorio(turno))

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        repositorio = RepositorioRecordatoriosDeTurnoPostgres(sesion)
        with pytest.raises(RecordatorioDeTurnoDuplicado):
            await repositorio.agregar(escenario.recordatorio(turno))
        # El rechazo corrió en un savepoint: la misma transacción puede seguir escribiendo.
        await repositorio.agregar(escenario.recordatorio(turno, horas=48))
        filas = await repositorio.de_turnos([turno.id])

    assert sorted(fila.anticipacion_min for fila in filas) == [24 * H, 48 * H]


async def test_dos_inserciones_concurrentes_de_la_misma_clave_dejan_una_sola_fila(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Dos transacciones de verdad: la segunda espera al commit de la primera y pierde."""
    escenario = await _escenario(engine_dueno, sesiones)
    turno = escenario.turno()
    await _guardar_turno(sesiones, escenario, turno)

    async def reservar() -> str:
        try:
            await _agregar(sesiones, escenario, escenario.recordatorio(turno))
        except RecordatorioDeTurnoDuplicado:
            return "duplicado"
        return "reservado"

    resultados = await asyncio.gather(reservar(), reservar())

    assert sorted(resultados) == ["duplicado", "reservado"]
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        cuantas = (
            await sesion.execute(text("SELECT count(*) FROM recordatorio_de_turno"))
        ).scalar_one()
    assert cuantas == 1


async def test_pendientes_trae_solo_las_filas_sin_terminar_cuya_fecha_llego(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    escenario = await _escenario(engine_dueno, sesiones)
    turno = escenario.turno()
    await _guardar_turno(sesiones, escenario, turno)

    en_curso = escenario.recordatorio(turno, horas=24)
    en_curso.iniciar_intento(AHORA)
    esperando = escenario.recordatorio(turno, horas=48)
    esperando.iniciar_intento(AHORA)
    esperando.registrar_falla(AHORA, codigo="131056", transitoria=True)
    futura = escenario.recordatorio(turno, horas=72)
    futura.iniciar_intento(AHORA + timedelta(days=1))
    enviada = escenario.recordatorio(turno, horas=96)
    enviada.iniciar_intento(AHORA)
    enviada.marcar_enviado(AHORA)
    for fila in (en_curso, esperando, futura, enviada):
        await _agregar(sesiones, escenario, fila)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        pendientes = await RepositorioRecordatoriosDeTurnoPostgres(sesion).pendientes(
            AHORA + timedelta(hours=1)
        )

    assert {fila.anticipacion_min for fila in pendientes} == {24 * H, 48 * H}
    assert all(fila.resultado is None for fila in pendientes)


async def test_guardar_actualiza_la_misma_fila_y_registra_el_resultado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    escenario = await _escenario(engine_dueno, sesiones)
    turno = escenario.turno()
    await _guardar_turno(sesiones, escenario, turno)
    fila = escenario.recordatorio(turno)
    fila.iniciar_intento(AHORA)
    await _agregar(sesiones, escenario, fila)

    fila.marcar_enviado(AHORA + timedelta(seconds=2))
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        await RepositorioRecordatoriosDeTurnoPostgres(sesion).guardar(fila)
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        (leida,) = await RepositorioRecordatoriosDeTurnoPostgres(sesion).de_turnos([turno.id])

    assert leida.resultado is ResultadoDeRecordatorio.ENVIADO
    assert leida.intentos == 1
    assert leida.procesado_en == AHORA + timedelta(seconds=2)
    assert leida.proximo_intento_en is None


async def test_abiertos_con_inicio_entre_respeta_el_rango_y_los_estados(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    escenario = await _escenario(engine_dueno, sesiones)
    desde = INICIO
    dentro = escenario.turno(desde + timedelta(hours=1))
    en_el_borde_de_arriba = escenario.turno(desde + timedelta(hours=3))
    en_el_borde_de_abajo = escenario.turno(desde, estado=EstadoTurno.CONFIRMADO)
    pasado_el_rango = escenario.turno(desde + timedelta(hours=5))
    cancelado = escenario.turno(desde + timedelta(hours=2), estado=EstadoTurno.CANCELADO)
    for turno in (dentro, en_el_borde_de_arriba, en_el_borde_de_abajo, pasado_el_rango, cancelado):
        await _guardar_turno(sesiones, escenario, turno)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        encontrados = await RepositorioTurnoPostgres(sesion).abiertos_con_inicio_entre(
            desde, desde + timedelta(hours=3)
        )

    # `desde` es exclusivo y `hasta` inclusivo; el cancelado no cuenta.
    assert [turno.id for turno in encontrados] == [dentro.id, en_el_borde_de_arriba.id]


async def test_el_fan_out_ve_las_empresas_y_el_barrido_de_una_no_lee_los_turnos_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    ahora = datetime.now(UTC)
    a = await _escenario(engine_dueno, sesiones)
    b = await _escenario(engine_dueno, sesiones)
    await _guardar_turno(sesiones, a, a.turno(ahora + timedelta(hours=10)))
    turno_b = b.turno(ahora + timedelta(hours=10))
    await _guardar_turno(sesiones, b, turno_b)

    async with sesiones() as sesion:
        empresas = await empresas_con_turnos_por_recordar(sesion, ahora + timedelta(hours=24))
    async with sesion_de_empresa(sesiones, a.empresa_id) as sesion:
        vistos_por_a = await RepositorioTurnoPostgres(sesion).abiertos_con_inicio_entre(
            ahora, ahora + timedelta(hours=24)
        )

    assert {a.empresa_id, b.empresa_id} <= set(empresas)
    assert turno_b.id not in {turno.id for turno in vistos_por_a}
    assert len(vistos_por_a) == 1
