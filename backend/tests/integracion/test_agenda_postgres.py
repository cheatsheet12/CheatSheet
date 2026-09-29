"""El doble booking contra el motor, que es lo único que lo hace imposible.

**El test que importa es el de concurrencia.** Decisión D28: dos reservas simultáneas sobre el
mismo recurso y la misma franja no pueden entrar las dos. Que entren es el error que el cliente
descubre en la puerta del local, y que se arregla llamando por teléfono a uno de los dos.

Eso **no se puede probar con un doble**: lo que decide es la restricción de exclusión de
PostgreSQL, y un doble sin motor aceptaría las dos —o rechazaría con su propia lógica, que es
la que no está en producción— y el test pasaría probando nada. Es el mismo argumento con el que
el épico 5 probó la numeración fiscal.

Este archivo también prueba **lo que la restricción deja pasar**, que es la otra mitad y la que
un `EXCLUDE` demasiado ancho rompería sin que nadie lo note: turnos contiguos, turnos en otro
recurso, y turnos sobre una franja que quedó libre porque el anterior se canceló.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from cheatsheet.contexts.scheduling.application.errors import FranjaOcupada
from cheatsheet.contexts.scheduling.domain.recurso import (
    RecursoReservable,
    TipoRecurso,
)
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno, Franja, Turno
from cheatsheet.contexts.scheduling.infrastructure.repositories import (
    RepositorioRecursoPostgres,
    RepositorioTurnoPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
#: Martes 8 de septiembre de 2026, 18:00 UTC — las 15 en la zona de la agenda.
INICIO = datetime(2026, 9, 8, 18, 0, tzinfo=UTC)

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
QUITAR_EXCLUSION = text("ALTER TABLE turno DROP CONSTRAINT excl_turno_recurso_franja")
PONER_EXCLUSION = text(
    "ALTER TABLE turno ADD CONSTRAINT excl_turno_recurso_franja "
    "EXCLUDE USING gist (recurso_id WITH =, "
    "franja_de_turno(franja_inicio, franja_duracion_min) WITH &&) "
    "WHERE (estado IN ('RESERVADO', 'CONFIRMADO', 'COMPLETADO'))"
)


class Escenario:
    """Una empresa con un cliente, un servicio y un recurso: lo mínimo para tener un turno."""

    def __init__(
        self, empresa_id: EmpresaId, cliente_id: uuid.UUID, servicio_id: uuid.UUID
    ) -> None:
        self.empresa_id = empresa_id
        self.cliente_id = cliente_id
        self.servicio_id = servicio_id
        self.recurso_id = uuid.uuid4()

    def turno(self, *, inicio: datetime = INICIO, duracion: int = 60, **cambios: object) -> Turno:
        base: dict[str, object] = {
            "id": uuid.uuid4(),
            "empresa_id": self.empresa_id,
            "cliente_id": self.cliente_id,
            "servicio_id": self.servicio_id,
            "recurso_id": self.recurso_id,
            "franja": Franja(inicio=inicio, duracion_min=duracion),
            "created_at": AHORA,
            "updated_at": AHORA,
        }
        base.update(cambios)
        return Turno(**base)  # type: ignore[arg-type]


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


async def _reservar(
    sesiones: async_sessionmaker[AsyncSession], escenario: Escenario, turno: Turno
) -> None:
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        await RepositorioTurnoPostgres(sesion).agregar(turno)


async def test_dos_reservas_simultaneas_de_la_misma_franja_no_entran_las_dos(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """**Decisión D28**, probada con dos transacciones de verdad.

    Las dos corrutinas insertan la misma franja al mismo tiempo. Sin la restricción, las dos
    entrarían: ninguna ve a la otra hasta que la primera hace commit.
    """
    escenario = await _escenario(engine_dueno, sesiones)

    async def reservar() -> str:
        try:
            await _reservar(sesiones, escenario, escenario.turno())
        except FranjaOcupada:
            return "ocupado"
        return "reservado"

    resultados = await asyncio.gather(reservar(), reservar())

    assert sorted(resultados) == ["ocupado", "reservado"]

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        cuantos = await sesion.execute(text("SELECT count(*) FROM turno"))
    assert cuantos.scalar_one() == 1


async def test_sin_la_restriccion_las_dos_entran(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La verificación al revés: **sin la restricción, el test de arriba no probaría nada**.

    Se saca la restricción, se corre lo mismo y se comprueba que quedan dos turnos pisados.
    Es la única forma de saber que el test anterior es evidencia y no una coincidencia — y es
    lo mismo que el épico 5 hizo sacando el `FOR UPDATE`.

    La restricción se repone al final, pase lo que pase: dejarla afuera haría que todos los
    tests siguientes de la sesión pasaran por el motivo equivocado.
    """
    escenario = await _escenario(engine_dueno, sesiones)

    async with engine_dueno.begin() as conexion:
        await conexion.execute(QUITAR_EXCLUSION)
    try:
        await _reservar(sesiones, escenario, escenario.turno())
        await _reservar(sesiones, escenario, escenario.turno())

        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            cuantos = await sesion.execute(text("SELECT count(*) FROM turno"))
        assert cuantos.scalar_one() == 2
    finally:
        async with engine_dueno.begin() as conexion:
            await conexion.execute(text("DELETE FROM turno"))
            await conexion.execute(PONER_EXCLUSION)


async def test_dos_turnos_contiguos_conviven(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El rango es `[)`: uno de 15 a 16 y otro de 16 a 17 no se pisan.

    Tiene que coincidir con `Franja.se_solapa_con` del dominio. Si el motor dijera otra cosa,
    la pantalla ofrecería un horario que el `INSERT` va a rechazar.
    """
    escenario = await _escenario(engine_dueno, sesiones)

    await _reservar(sesiones, escenario, escenario.turno(inicio=INICIO, duracion=60))
    await _reservar(
        sesiones, escenario, escenario.turno(inicio=INICIO + timedelta(hours=1), duracion=60)
    )

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        cuantos = await sesion.execute(text("SELECT count(*) FROM turno"))
    assert cuantos.scalar_one() == 2


async def test_la_misma_franja_en_otro_recurso_entra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La restricción es por recurso: dos profesionales atienden a la misma hora."""
    escenario = await _escenario(engine_dueno, sesiones)
    otro = uuid.uuid4()
    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        await RepositorioRecursoPostgres(sesion).agregar(
            RecursoReservable(
                id=otro,
                empresa_id=escenario.empresa_id,
                nombre="Consultorio 2",
                tipo=TipoRecurso.ESPACIO,
                created_at=AHORA,
            )
        )

    await _reservar(sesiones, escenario, escenario.turno())
    await _reservar(sesiones, escenario, escenario.turno(recurso_id=otro))

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        cuantos = await sesion.execute(text("SELECT count(*) FROM turno"))
    assert cuantos.scalar_one() == 2


async def test_un_turno_cancelado_libera_la_franja(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La restricción es **parcial**: sólo `RESERVADO`, `CONFIRMADO` y `COMPLETADO` ocupan.

    Sin la cláusula `WHERE`, cancelar un turno no liberaría su horario — y el negocio se
    quedaría sin poder revender una franja que quedó libre.
    """
    escenario = await _escenario(engine_dueno, sesiones)
    primero = escenario.turno()
    await _reservar(sesiones, escenario, primero)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        repositorio = RepositorioTurnoPostgres(sesion)
        guardado = await repositorio.buscar_por_id(primero.id)
        assert guardado is not None
        guardado.cancelar()
        await repositorio.guardar(guardado)

    await _reservar(sesiones, escenario, escenario.turno())

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        abiertos = await RepositorioTurnoPostgres(sesion).ocupados_en(
            escenario.recurso_id, INICIO.date()
        )
    assert len(abiertos) == 1


async def test_reprogramar_a_una_franja_ocupada_es_rechazado_por_el_motor(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E7-02, cuarto criterio. Mover una franja choca igual que crearla."""
    escenario = await _escenario(engine_dueno, sesiones)
    primero = escenario.turno(inicio=INICIO, duracion=60)
    segundo = escenario.turno(inicio=INICIO + timedelta(hours=2), duracion=60)
    await _reservar(sesiones, escenario, primero)
    await _reservar(sesiones, escenario, segundo)

    async def mover() -> None:
        # En su propia corrutina y no dentro del `with`: `pytest.raises` sobre un bloque
        # largo esconde de cuál de sus líneas salió la excepción, y ruff tiene razón en
        # pedirlo (PT012). Además deja explícito que la transacción entera es la que se
        # revierte, que es lo que hace que el turno quede en su franja original.
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioTurnoPostgres(sesion)
            movido = await repositorio.buscar_por_id(segundo.id)
            assert movido is not None
            movido.reprogramar(Franja(inicio=INICIO, duracion_min=60))
            await repositorio.guardar(movido)

    with pytest.raises(FranjaOcupada):
        await mover()

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        final = await RepositorioTurnoPostgres(sesion).buscar_por_id(segundo.id)
    assert final is not None
    # «Mantiene el turno en su franja original»: el rollback de la transacción lo garantiza.
    assert final.franja.inicio == INICIO + timedelta(hours=2)


async def test_una_empresa_no_ve_los_turnos_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RLS sobre `turno`. La agenda es dónde está cada cliente a cada hora: si se filtrara,
    se filtraría eso."""
    una = await _escenario(engine_dueno, sesiones)
    otra = await _escenario(engine_dueno, sesiones)
    await _reservar(sesiones, una, una.turno())

    async with sesion_de_empresa(sesiones, otra.empresa_id) as sesion:
        cuantos = await sesion.execute(text("SELECT count(*) FROM turno"))
    assert cuantos.scalar_one() == 0


async def test_una_segunda_excepcion_para_la_misma_fecha_la_rechaza_el_indice(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E7-05 RN-02, ganada por el índice y no por el `if` del agregado.

    Se escribe la segunda excepción **sin** pasar por `agregar_excepcion`, que es lo que haría
    una segunda pestaña: las dos leyeron el recurso sin excepciones y las dos agregan la suya.
    """
    from cheatsheet.contexts.scheduling.application.errors import ExcepcionDuplicada
    from cheatsheet.contexts.scheduling.domain.recurso import (
        ExcepcionDeDisponibilidad,
        TipoExcepcion,
    )

    escenario = await _escenario(engine_dueno, sesiones)
    fecha = INICIO.date()

    async def duplicar() -> None:
        # La excepción tiene que salir **del `async with`**: cuando el motor rechaza el
        # `flush`, la sesión queda muerta y su `commit` fallaría con otra excepción distinta.
        # Dejarla salir es lo que revierte la transacción, que es lo que pasa en producción.
        async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
            repositorio = RepositorioRecursoPostgres(sesion)
            recurso = await repositorio.buscar_por_id(escenario.recurso_id)
            assert recurso is not None
            # Dos excepciones para la misma fecha, puestas a mano sin pasar por el invariante:
            # es lo que hacen dos pestañas que leyeron el recurso sin excepciones.
            recurso.excepciones = (
                ExcepcionDeDisponibilidad(fecha=fecha, tipo=TipoExcepcion.BLOQUEO),
                ExcepcionDeDisponibilidad(fecha=fecha, tipo=TipoExcepcion.BLOQUEO),
            )
            await repositorio.guardar(recurso)

    with pytest.raises(ExcepcionDuplicada):
        await duplicar()


async def test_el_recurso_se_guarda_y_se_lee_entero(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El agregado va y vuelve completo: horario, excepciones y servicios."""
    from datetime import time

    from cheatsheet.contexts.scheduling.domain.recurso import (
        ExcepcionDeDisponibilidad,
        PatronDeDisponibilidad,
        TipoExcepcion,
    )

    escenario = await _escenario(engine_dueno, sesiones)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        repositorio = RepositorioRecursoPostgres(sesion)
        recurso = await repositorio.buscar_por_id(escenario.recurso_id)
        assert recurso is not None
        recurso.definir_disponibilidad(
            (
                PatronDeDisponibilidad(
                    dia_semana=1, hora_inicio=time(9), hora_fin=time(18), duracion_slot_min=30
                ),
            )
        )
        recurso.agregar_excepcion(
            ExcepcionDeDisponibilidad(fecha=INICIO.date(), tipo=TipoExcepcion.BLOQUEO)
        )
        await repositorio.guardar(recurso)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        leido = await RepositorioRecursoPostgres(sesion).buscar_por_id(escenario.recurso_id)

    assert leido is not None
    assert len(leido.patrones) == 1
    assert leido.patrones[0].hora_fin == time(18)
    assert len(leido.excepciones) == 1
    assert leido.servicios == frozenset({escenario.servicio_id})


async def test_el_estado_del_turno_sobrevive_al_viaje(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    escenario = await _escenario(engine_dueno, sesiones)
    turno = escenario.turno()
    await _reservar(sesiones, escenario, turno)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        repositorio = RepositorioTurnoPostgres(sesion)
        leido = await repositorio.buscar_por_id(turno.id)
        assert leido is not None
        leido.confirmar()
        await repositorio.guardar(leido)

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        final = await RepositorioTurnoPostgres(sesion).buscar_por_id(turno.id)

    assert final is not None
    assert final.estado is EstadoTurno.CONFIRMADO
    assert final.franja.duracion_min == 60


async def test_una_carga_a_posteriori_solapada_con_un_completado_la_rechaza_la_base(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """D95: la carga a posteriori nace `COMPLETADO` y la exclusión tiene que cubrirlo.

    Sin `COMPLETADO` en la condición de la restricción, esta segunda atención entraría encima
    de la primera y la historia (HU-E7-06 RN-07) exige rechazar ese solapamiento.
    """
    escenario = await _escenario(engine_dueno, sesiones)
    await _reservar(sesiones, escenario, escenario.turno(estado=EstadoTurno.COMPLETADO))

    with pytest.raises(FranjaOcupada):
        await _reservar(sesiones, escenario, escenario.turno(estado=EstadoTurno.COMPLETADO))


async def test_un_turno_nuevo_sobre_un_completado_se_rechaza_y_sobre_un_no_show_entra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`COMPLETADO` ocupa la franja; `NO_SHOW` no: el cliente no vino y el recurso quedó libre."""
    completado = await _escenario(engine_dueno, sesiones)
    await _reservar(sesiones, completado, completado.turno(estado=EstadoTurno.COMPLETADO))
    no_show = await _escenario(engine_dueno, sesiones)
    await _reservar(sesiones, no_show, no_show.turno(estado=EstadoTurno.NO_SHOW))

    with pytest.raises(FranjaOcupada):
        await _reservar(sesiones, completado, completado.turno())
    await _reservar(sesiones, no_show, no_show.turno())

    async with sesion_de_empresa(sesiones, no_show.empresa_id) as sesion:
        ocupan = await RepositorioTurnoPostgres(sesion).ocupados_en(
            no_show.recurso_id, INICIO.date()
        )
    # `ocupados_en` coincide con la restricción: el no-show no cuenta, el nuevo sí.
    assert len(ocupan) == 1


async def test_ocupados_en_cuenta_los_completados(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    escenario = await _escenario(engine_dueno, sesiones)
    await _reservar(sesiones, escenario, escenario.turno(estado=EstadoTurno.COMPLETADO))

    async with sesion_de_empresa(sesiones, escenario.empresa_id) as sesion:
        ocupan = await RepositorioTurnoPostgres(sesion).ocupados_en(
            escenario.recurso_id, INICIO.date()
        )

    assert [uno.estado for uno in ocupan] == [EstadoTurno.COMPLETADO]


async def test_la_migracion_aborta_y_lista_los_completados_solapados(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La migración 0024 no falla con un error críptico: lista los turnos que se pisan.

    Se baja a 0023, se cargan dos completados solapados (que la restricción vieja permitía) y
    se intenta subir. Al final se limpian y se vuelve a `head`, pase lo que pase: dejar el
    esquema a medias rompería todos los tests siguientes de la sesión.

    Alembic corre `asyncio.run` en su `env.py`, así que se llama desde otro hilo.
    """
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    await asyncio.to_thread(command.downgrade, config, "0023")
    try:
        escenario = await _escenario(engine_dueno, sesiones)
        uno = escenario.turno(estado=EstadoTurno.COMPLETADO)
        otro = escenario.turno(estado=EstadoTurno.COMPLETADO, inicio=INICIO + timedelta(minutes=30))
        await _reservar(sesiones, escenario, uno)
        await _reservar(sesiones, escenario, otro)

        with pytest.raises(RuntimeError, match=str(min(uno.id, otro.id))):
            await asyncio.to_thread(command.upgrade, config, "0024")
    finally:
        async with engine_dueno.begin() as conexion:
            await conexion.execute(text("DELETE FROM turno"))
        await asyncio.to_thread(command.upgrade, config, "head")
