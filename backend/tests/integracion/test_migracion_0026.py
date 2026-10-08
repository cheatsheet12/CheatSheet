"""La migración 0026 sobre datos viejos: backfill exacto, sube/baja/sube y el informe (D91).

Se ejerce con filas que existían **antes** de la migración, porque un backfill probado solo
sobre una tabla vacía no prueba nada. El esquema se baja a `0025`, se siembran cobros con el
esquema viejo (`pagado_en`), se sube a `0026` y se mira qué recibió cada fila:

| Fila existente        | fecha_pago   | aproximada | medio              | operacion |
| APROBADO/REEMBOLSADO  | la de antes  | true       | LINK_MERCADOPAGO   | NULL      |
| PENDIENTE/VENCIDO     | NULL         | false      | LINK_MERCADOPAGO   | NULL      |
| CANCELADO (con o sin  | NULL         | false      | LINK_MERCADOPAGO   | NULL      |
| pago huerfano)        |              |            |                    |           |

Los tests son síncronos a propósito: `alembic.command` arranca su propio loop de asyncio, y un
test `async` lo tendría ya corriendo. Lo que necesita SQL propio lo hace con `asyncio.run`.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from types import ModuleType
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from cheatsheet.platform.database import argumentos_de_conexion
from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CREADO = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
PAGADO = datetime(2026, 8, 3, 15, 30, tzinfo=UTC)
VENCE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _la_migracion() -> ModuleType:
    """El módulo de la 0026 por su ruta: un nombre que empieza con dígito no se importa."""
    ruta = RAIZ_BACKEND / "migrations" / "versions" / "0026_fecha_medio_y_operacion_de_pago.py"
    spec = importlib.util.spec_from_file_location("migracion_0026", ruta)
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def esquema_en_0025(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0025` y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0025")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def _motor() -> AsyncEngine:
    """El rol dueño, que ve todas las empresas (`BYPASSRLS`, ADR-0005) y puede sembrar."""
    return create_async_engine(
        os.environ["DATABASE_URL_MIGRATIONS"],
        connect_args=argumentos_de_conexion(os.environ["DATABASE_URL_MIGRATIONS"]),
    )


CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
)
CREAR_COBRO_VIEJO = text(
    "INSERT INTO cobro (id, empresa_id, cliente_id, monto, descripcion, estado, vence_el, "
    "pagado_en, mp_payment_id, monto_reembolsado, created_at, updated_at) "
    "VALUES (:id, :empresa_id, :cliente_id, 1000.00, 'Consulta', :estado, :vence, :pagado_en, "
    ":mp_payment_id, :monto_reembolsado, :creado, :creado)"
)


async def _sembrar(cobros: list[dict[str, Any]]) -> uuid.UUID:
    """Una empresa, un cliente y los cobros dados, con el esquema **viejo** (`pagado_en`)."""
    empresa_id, cliente_id = uuid.uuid4(), uuid.uuid4()
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
            await conexion.execute(
                CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": CREADO}
            )
            for cobro in cobros:
                await conexion.execute(
                    CREAR_COBRO_VIEJO,
                    {
                        "id": uuid.uuid4(),
                        "empresa_id": empresa_id,
                        "cliente_id": cliente_id,
                        "estado": cobro["estado"],
                        "vence": VENCE,
                        "pagado_en": cobro.get("pagado_en"),
                        "mp_payment_id": cobro.get("mp_payment_id"),
                        "monto_reembolsado": cobro.get("monto_reembolsado"),
                        "creado": CREADO,
                    },
                )
    finally:
        await motor.dispose()
    return empresa_id


#: Consultas literales (no interpoladas), una por esquema. Ordenadas para que la comparación no
#: dependa del orden físico de las filas.
LEER_NUEVO = text(
    "SELECT estado, mp_payment_id, fecha_pago, fecha_pago_aproximada, medio_de_pago, "
    "numero_de_operacion FROM cobro WHERE empresa_id = :empresa_id "
    "ORDER BY mp_payment_id NULLS LAST, estado"
)
LEER_FECHAS = text(
    "SELECT estado, fecha_pago, fecha_pago_aproximada FROM cobro WHERE empresa_id = :empresa_id "
    "ORDER BY mp_payment_id NULLS LAST, estado"
)
LEER_VIEJO = text(
    "SELECT estado, pagado_en FROM cobro WHERE empresa_id = :empresa_id "
    "ORDER BY mp_payment_id NULLS LAST, estado"
)


async def _leer(consulta: TextClause, empresa_id: uuid.UUID) -> list[dict[str, Any]]:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            filas = (await conexion.execute(consulta, {"empresa_id": empresa_id})).mappings().all()
    finally:
        await motor.dispose()
    return [dict(fila) for fila in filas]


VIEJOS: list[dict[str, Any]] = [
    {"estado": "APROBADO", "pagado_en": PAGADO, "mp_payment_id": "pago-1"},
    {
        "estado": "REEMBOLSADO",
        "pagado_en": PAGADO,
        "mp_payment_id": "pago-2",
        "monto_reembolsado": Decimal("1000.00"),
    },
    {"estado": "PENDIENTE"},
    {"estado": "VENCIDO"},
    {"estado": "CANCELADO"},
    {"estado": "CANCELADO", "mp_payment_id": "pago-huerfano"},
]


def test_la_migracion_da_a_cada_fila_vieja_lo_que_dice_el_plan(esquema_en_0025: None) -> None:
    empresa_id = asyncio.run(_sembrar(VIEJOS))

    command.upgrade(_config(), "0026")

    filas = asyncio.run(_leer(LEER_NUEVO, empresa_id))
    assert len(filas) == len(VIEJOS)
    for fila in filas:
        assert fila["medio_de_pago"] == "LINK_MERCADOPAGO"
        assert fila["numero_de_operacion"] is None
        if fila["estado"] in ("APROBADO", "REEMBOLSADO"):
            # Conservan la fecha de antes y quedan marcados como aproximados.
            assert fila["fecha_pago"] == PAGADO
            assert fila["fecha_pago_aproximada"] is True
        else:
            # Ni siquiera el pago huérfano de un CANCELADO se convierte en fecha de pago.
            assert fila["fecha_pago"] is None
            assert fila["fecha_pago_aproximada"] is False


def test_la_migracion_sube_baja_y_vuelve_a_subir_sin_perder_las_fechas(
    esquema_en_0025: None,
) -> None:
    empresa_id = asyncio.run(_sembrar(VIEJOS))
    config = _config()

    command.upgrade(config, "0026")
    command.downgrade(config, "0025")

    # Al bajar, `fecha_pago` vuelve a llamarse `pagado_en` con sus valores.
    vueltas = asyncio.run(_leer(LEER_VIEJO, empresa_id))
    pagados = [
        fila["pagado_en"] for fila in vueltas if fila["estado"] in ("APROBADO", "REEMBOLSADO")
    ]
    assert pagados == [PAGADO, PAGADO]

    command.upgrade(config, "0026")
    de_nuevo = asyncio.run(_leer(LEER_FECHAS, empresa_id))
    assert [f["fecha_pago"] for f in de_nuevo if f["estado"] == "APROBADO"] == [PAGADO]


def test_un_aprobado_viejo_sin_fecha_se_informa_y_no_se_completa(esquema_en_0025: None) -> None:
    """No se inventa una fecha: la fila queda `NULL`, la migración no falla y se informa."""
    empresa_id = asyncio.run(_sembrar([{"estado": "APROBADO", "mp_payment_id": "pago-sin-fecha"}]))

    command.upgrade(_config(), "0026")

    filas = asyncio.run(_leer(LEER_FECHAS, empresa_id))
    assert filas == [{"estado": "APROBADO", "fecha_pago": None, "fecha_pago_aproximada": False}]
    asyncio.run(_restriccion_sin_validar())
    avisos = asyncio.run(_correr_el_informe())
    assert any(str(empresa_id) in aviso and "1 cobro(s)" in aviso for aviso in avisos), avisos


async def _restriccion_sin_validar() -> None:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            validada = (
                await conexion.execute(
                    text(
                        "SELECT convalidated FROM pg_constraint "
                        "WHERE conname = 'ck_cobro_fecha_de_pago'"
                    )
                )
            ).scalar_one()
    finally:
        await motor.dispose()
    assert validada is False, "Debe quedar NOT VALID hasta que el informe dé cero"


async def _correr_el_informe() -> list[str]:
    """Los `NOTICE` que emite el informe de la migración, capturados de la conexión."""
    avisos: list[str] = []
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            crudo = await conexion.get_raw_connection()
            # El log del servidor llega al driver, no a SQLAlchemy: se escucha en el driver.
            driver = crudo.driver_connection
            assert driver is not None
            driver.add_log_listener(lambda _con, mensaje: avisos.append(str(mensaje)))
            await conexion.execute(text(_la_migracion().INFORME))
    finally:
        await motor.dispose()
    return avisos
