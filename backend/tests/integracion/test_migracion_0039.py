"""La migración 0039: `turno.franja_asignada_en` y la tabla `recordatorio_de_turno`.

Fija lo que la migración promete y el código no puede garantizar solo:

- el backfill de `franja_asignada_en` con el instante de la migración, y que la columna quede `NOT NULL`;
- la tabla con RLS **forzada**, sin `DELETE` para la app (la fila es la prueba de idempotencia);
- el índice único de `(turno, anticipación, franja)` y los dos índices parciales;
- `empresas_con_turnos_por_recordar(hasta)`: `SECURITY DEFINER`, solo ids, respeta `hasta`,
  incluye las empresas con un recordatorio sin terminar y excluye los turnos cerrados;
- que sube y baja limpio.

Son síncronos a propósito, como `test_migracion_0038.py`: `alembic.command` arranca su propio
loop de asyncio. Necesitan PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Ana Diaz', 'PANEL', true, :ahora, :ahora)"
)
CREAR_SERVICIO = text(
    "INSERT INTO servicio (id, empresa_id, nombre, precio, alicuota_iva, agendable, "
    "duracion_estandar_min, origen, presente_en_planilla, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Corte', 1000.00, 0.2100, true, 30, 'PANEL', false, true, "
    ":ahora, :ahora)"
)
CREAR_RECURSO = text(
    "INSERT INTO recurso_reservable (id, empresa_id, tipo, nombre, activo, created_at, "
    "intervalo_entre_turnos_min) "
    "VALUES (:id, :empresa_id, 'ESPACIO', 'Consultorio', true, :ahora, 0)"
)
#: Sin `franja_asignada_en`: es el turno tal como lo insertaría el esquema de la 0038.
CREAR_TURNO_VIEJO = text(
    "INSERT INTO turno (id, empresa_id, cliente_id, servicio_id, recurso_id, franja_inicio, "
    "franja_duracion_min, estado, canal_reserva, created_at, updated_at) "
    "VALUES (:id, :empresa_id, :cliente_id, :servicio_id, :recurso_id, :inicio, 30, "
    ":estado, 'PANEL', :creado, :creado)"
)
CREAR_TURNO = text(
    "INSERT INTO turno (id, empresa_id, cliente_id, servicio_id, recurso_id, franja_inicio, "
    "franja_duracion_min, estado, canal_reserva, created_at, updated_at, franja_asignada_en) "
    "VALUES (:id, :empresa_id, :cliente_id, :servicio_id, :recurso_id, :inicio, 30, "
    ":estado, 'PANEL', :creado, :creado, :creado)"
)
CREAR_RECORDATORIO = text(
    "INSERT INTO recordatorio_de_turno (id, empresa_id, turno_id, anticipacion_min, "
    "franja_inicio, resultado, intentos, proximo_intento_en, created_at) "
    "VALUES (:id, :empresa_id, :turno_id, :anticipacion, :inicio, :resultado, 0, :proximo, "
    ":creado)"
)
LEER_FRANJA_ASIGNADA = text("SELECT franja_asignada_en FROM turno WHERE id = :id")
COLUMNA = text(
    "SELECT is_nullable FROM information_schema.columns "
    "WHERE table_name = 'turno' AND column_name = 'franja_asignada_en'"
)
TABLA = text("SELECT count(*) FROM pg_tables WHERE tablename = 'recordatorio_de_turno'")
INDICE = text("SELECT indexdef FROM pg_indexes WHERE indexname = :nombre")
RLS = text(
    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
    "WHERE relname = 'recordatorio_de_turno'"
)
PRIVILEGIO_DE_LA_APP = text(
    "SELECT has_table_privilege('cheatsheet_app', 'recordatorio_de_turno', :privilegio)"
)
FUNCION = text(
    "SELECT prosecdef, proconfig FROM pg_proc WHERE proname = 'empresas_con_turnos_por_recordar'"
)
PERMISO_DE_LA_APP = text(
    "SELECT has_function_privilege('cheatsheet_app', "
    "'empresas_con_turnos_por_recordar(timestamptz)', 'EXECUTE')"
)
PERMISO_DE_PUBLIC = text(
    "SELECT has_function_privilege('public', "
    "'empresas_con_turnos_por_recordar(timestamptz)', 'EXECUTE')"
)
EMPRESAS_POR_RECORDAR = text("SELECT empresa_id FROM empresas_con_turnos_por_recordar(:hasta)")


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _motor() -> AsyncEngine:
    """El rol dueño ve todas las empresas (`BYPASSRLS`, ADR-0005)."""
    return create_async_engine(os.environ["DATABASE_URL_MIGRATIONS"])


async def _ejecutar(sentencia: object, parametros: list[dict[str, object]]) -> None:
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            for fila in parametros:
                await conexion.execute(sentencia, fila)  # type: ignore[call-overload]
    finally:
        await motor.dispose()


async def _leer(
    sentencia: object, parametros: dict[str, object] | None = None
) -> list[tuple[object, ...]]:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            filas = (await conexion.execute(sentencia, parametros or {})).all()  # type: ignore[call-overload]
    finally:
        await motor.dispose()
    return [tuple(fila) for fila in filas]


class Empresa:
    """Una empresa con lo mínimo para tener turnos: un cliente y un servicio."""

    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.cliente_id = uuid.uuid4()
        self.servicio_id = uuid.uuid4()
        asyncio.run(_ejecutar(CREAR_EMPRESA, [{"id": self.id}]))
        asyncio.run(
            _ejecutar(
                CREAR_CLIENTE, [{"id": self.cliente_id, "empresa_id": self.id, "ahora": AHORA}]
            )
        )
        asyncio.run(
            _ejecutar(
                CREAR_SERVICIO, [{"id": self.servicio_id, "empresa_id": self.id, "ahora": AHORA}]
            )
        )

    def turno(
        self,
        inicio: datetime,
        estado: str = "RESERVADO",
        *,
        creado: datetime = AHORA,
        viejo: bool = False,
    ) -> uuid.UUID:
        """Un turno en su propio recurso (así dos turnos de la empresa nunca se pisan)."""
        turno_id, recurso_id = uuid.uuid4(), uuid.uuid4()
        asyncio.run(
            _ejecutar(CREAR_RECURSO, [{"id": recurso_id, "empresa_id": self.id, "ahora": AHORA}])
        )
        asyncio.run(
            _ejecutar(
                CREAR_TURNO_VIEJO if viejo else CREAR_TURNO,
                [
                    {
                        "id": turno_id,
                        "empresa_id": self.id,
                        "cliente_id": self.cliente_id,
                        "servicio_id": self.servicio_id,
                        "recurso_id": recurso_id,
                        "inicio": inicio,
                        "estado": estado,
                        "creado": creado,
                    }
                ],
            )
        )
        return turno_id

    def recordatorio(
        self,
        turno_id: uuid.UUID,
        inicio: datetime,
        *,
        anticipacion: int = 1440,
        resultado: str | None = None,
        proximo: datetime | None = None,
    ) -> uuid.UUID:
        recordatorio_id = uuid.uuid4()
        asyncio.run(
            _ejecutar(
                CREAR_RECORDATORIO,
                [
                    {
                        "id": recordatorio_id,
                        "empresa_id": self.id,
                        "turno_id": turno_id,
                        "anticipacion": anticipacion,
                        "inicio": inicio,
                        "resultado": resultado,
                        "proximo": proximo,
                        "creado": AHORA,
                    }
                ],
            )
        )
        return recordatorio_id


@pytest.fixture
def esquema_en_0038(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0038` y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0038")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def test_downgrade_deja_el_esquema_sin_la_columna_la_tabla_ni_la_funcion(
    esquema_en_0038: None,
) -> None:
    assert asyncio.run(_leer(COLUMNA)) == []
    assert asyncio.run(_leer(TABLA)) == [(0,)]
    assert asyncio.run(_leer(FUNCION)) == []
    assert asyncio.run(_leer(INDICE, {"nombre": "ix_turno_abierto_inicio"})) == []


def test_sube_con_backfill_de_la_franja_asignada_y_la_columna_queda_not_null(
    esquema_en_0038: None,
) -> None:
    """Caso 14. Un turno viejo toma el instante de la migración, **no** su `created_at`.

    Así (D-U8-4) toda anticipación cuyo momento ideal cae antes del deploy se omite y el primer
    barrido posterior no manda de golpe avisos atrasados.
    """
    empresa = Empresa()
    creado = AHORA - timedelta(days=30)
    turno_id = empresa.turno(AHORA + timedelta(days=3), creado=creado, viejo=True)

    antes = datetime.now(tz=UTC)
    command.upgrade(_config(), "head")
    despues = datetime.now(tz=UTC)

    [(valor,)] = asyncio.run(_leer(LEER_FRANJA_ASIGNADA, {"id": turno_id}))
    assert isinstance(valor, datetime)
    asignada: datetime = valor
    assert asignada != creado
    assert antes <= asignada <= despues
    assert asyncio.run(_leer(COLUMNA)) == [("NO",)]


def test_la_tabla_tiene_rls_forzada_y_la_app_no_puede_borrar(esquema_migrado: None) -> None:
    assert asyncio.run(_leer(RLS)) == [(True, True)]
    permisos = {
        privilegio: asyncio.run(_leer(PRIVILEGIO_DE_LA_APP, {"privilegio": privilegio}))
        for privilegio in ("SELECT", "INSERT", "UPDATE", "DELETE")
    }
    assert permisos == {
        "SELECT": [(True,)],
        "INSERT": [(True,)],
        "UPDATE": [(True,)],
        "DELETE": [(False,)],
    }


def test_el_indice_unico_y_los_dos_parciales(esquema_migrado: None) -> None:
    unico = str(asyncio.run(_leer(INDICE, {"nombre": "uq_recordatorio_de_turno"}))[0][0])
    pendiente = str(
        asyncio.run(_leer(INDICE, {"nombre": "ix_recordatorio_de_turno_pendiente"}))[0][0]
    )
    abierto = str(asyncio.run(_leer(INDICE, {"nombre": "ix_turno_abierto_inicio"}))[0][0])

    assert "UNIQUE" in unico
    assert "(turno_id, anticipacion_min, franja_inicio)" in unico
    # Parciales: sin la cláusula `WHERE` indexarían cada fila que alguna vez existió.
    assert "WHERE (resultado IS NULL)" in pendiente
    assert "RESERVADO" in abierto
    assert "CONFIRMADO" in abierto
    assert "COMPLETADO" not in abierto


def test_el_indice_unico_rechaza_la_misma_clave(esquema_migrado: None) -> None:
    empresa = Empresa()
    inicio = AHORA + timedelta(days=2)
    turno_id = empresa.turno(inicio)
    empresa.recordatorio(turno_id, inicio, resultado="ENVIADO")

    with pytest.raises(IntegrityError, match="uq_recordatorio_de_turno"):
        empresa.recordatorio(turno_id, inicio, resultado="ENVIADO")
    # Otra anticipación u otra franja del mismo turno es otra clave: entran.
    empresa.recordatorio(turno_id, inicio, anticipacion=2880, resultado="ENVIADO")
    empresa.recordatorio(turno_id, inicio + timedelta(days=1), resultado="ENVIADO")


@pytest.mark.parametrize(
    ("anticipacion", "resultado"),
    [(59, "ENVIADO"), (10081, "ENVIADO"), (1440, "PERDIDO")],
)
def test_los_check_rechazan_una_anticipacion_fuera_de_rango_y_un_resultado_invalido(
    esquema_migrado: None, anticipacion: int, resultado: str
) -> None:
    empresa = Empresa()
    inicio = AHORA + timedelta(days=2)
    turno_id = empresa.turno(inicio)

    with pytest.raises(IntegrityError):
        empresa.recordatorio(turno_id, inicio, anticipacion=anticipacion, resultado=resultado)


def test_borrar_el_turno_arrastra_sus_recordatorios(esquema_migrado: None) -> None:
    empresa = Empresa()
    inicio = AHORA + timedelta(days=2)
    turno_id = empresa.turno(inicio)
    recordatorio_id = empresa.recordatorio(turno_id, inicio, resultado="OMITIDO")

    asyncio.run(_ejecutar(text("DELETE FROM turno WHERE id = :id"), [{"id": turno_id}]))

    restantes = asyncio.run(
        _leer(
            text("SELECT count(*) FROM recordatorio_de_turno WHERE id = :id"),
            {"id": recordatorio_id},
        )
    )
    assert restantes == [(0,)]


def test_la_funcion_es_security_definer_con_search_path_y_solo_la_app_la_ejecuta(
    esquema_migrado: None,
) -> None:
    ((definer, configuracion),) = asyncio.run(_leer(FUNCION))

    assert definer is True
    assert configuracion is not None
    assert "search_path=public" in list(configuracion)  # type: ignore[call-overload]
    assert asyncio.run(_leer(PERMISO_DE_LA_APP)) == [(True,)]
    assert asyncio.run(_leer(PERMISO_DE_PUBLIC)) == [(False,)]


def test_las_empresas_a_recordar_respetan_hasta_incluyen_pendientes_y_excluyen_cerrados(
    esquema_migrado: None,
) -> None:
    """Caso 16."""
    ahora = datetime.now(UTC)
    hasta = ahora + timedelta(hours=24)

    con_turno_proximo = Empresa()
    con_turno_proximo.turno(ahora + timedelta(hours=10))

    con_turno_lejano = Empresa()
    con_turno_lejano.turno(ahora + timedelta(hours=200))

    con_turno_cerrado = Empresa()
    con_turno_cerrado.turno(ahora + timedelta(hours=5), estado="CANCELADO")

    con_turno_ya_empezado = Empresa()
    con_turno_ya_empezado.turno(ahora - timedelta(hours=1))

    # Un recordatorio sin terminar mantiene a la empresa en el fan-out aunque su turno se haya
    # cancelado: hay que visitarla para descartarlo.
    con_pendiente = Empresa()
    inicio = ahora + timedelta(hours=300)
    turno_cancelado = con_pendiente.turno(inicio, estado="CANCELADO")
    con_pendiente.recordatorio(turno_cancelado, inicio, proximo=ahora)

    con_todo_resuelto = Empresa()
    inicio_resuelto = ahora + timedelta(hours=300)
    turno_resuelto = con_todo_resuelto.turno(inicio_resuelto, estado="CANCELADO")
    con_todo_resuelto.recordatorio(turno_resuelto, inicio_resuelto, resultado="DESCARTADO")

    sembradas = {
        empresa.id
        for empresa in (
            con_turno_proximo,
            con_turno_lejano,
            con_turno_cerrado,
            con_turno_ya_empezado,
            con_pendiente,
            con_todo_resuelto,
        )
    }
    devueltas = {fila[0] for fila in asyncio.run(_leer(EMPRESAS_POR_RECORDAR, {"hasta": hasta}))}

    assert devueltas & sembradas == {con_turno_proximo.id, con_pendiente.id}
    # Solo ids: la función devuelve una columna.
    assert all(
        len(fila) == 1 for fila in asyncio.run(_leer(EMPRESAS_POR_RECORDAR, {"hasta": hasta}))
    )
