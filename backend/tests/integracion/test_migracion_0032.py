"""La migración 0032: `conversacion.dialogo` sube y baja (decisión D99, caso 36 del plan).

La columna es `jsonb` **nullable** y sin backfill: lo que se prueba es que `upgrade` la agrega,
que `downgrade` la quita sin tocar el resto de la tabla, y que una conversación que ya existía
**antes** sigue ahí, sin diálogo, después de subir.

Son síncronos a propósito, como `test_migracion_0027.py`: `alembic.command` arranca su propio loop
de asyncio. Necesitan PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base
from tests.integracion.guarda import argumentos_de_conexion_de_prueba

pytestmark = [requiere_base, pytest.mark.integration]

AHORA = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)

COLUMNA = text(
    "SELECT data_type, is_nullable FROM information_schema.columns "
    "WHERE table_name = 'conversacion' AND column_name = 'dialogo'"
)
CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Ana Diaz', 'AGENTE', true, :ahora, :ahora)"
)
CREAR_CONVERSACION_VIEJA = text(
    "INSERT INTO conversacion (id, empresa_id, cliente_id, estado, contador, ventana_maximo, "
    "created_at) VALUES (:id, :empresa_id, :cliente_id, 'ACTIVA', 0, 3, :ahora)"
)
LEER_DIALOGO = text("SELECT dialogo FROM conversacion WHERE id = :id")


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _motor() -> AsyncEngine:
    """El rol dueño, que ve todas las empresas (`BYPASSRLS`, ADR-0005) y puede sembrar."""
    return create_async_engine(
        os.environ["DATABASE_URL_MIGRATIONS"],
        connect_args=argumentos_de_conexion_de_prueba(os.environ["DATABASE_URL_MIGRATIONS"]),
    )


async def _columna() -> tuple[str, str] | None:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            fila = (await conexion.execute(COLUMNA)).first()
    finally:
        await motor.dispose()
    return None if fila is None else (str(fila[0]), str(fila[1]))


async def _sembrar_conversacion_vieja() -> uuid.UUID:
    empresa_id, cliente_id, conversacion_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
            await conexion.execute(
                CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
            )
            await conexion.execute(
                CREAR_CONVERSACION_VIEJA,
                {
                    "id": conversacion_id,
                    "empresa_id": empresa_id,
                    "cliente_id": cliente_id,
                    "ahora": AHORA,
                },
            )
    finally:
        await motor.dispose()
    return conversacion_id


async def _dialogo_de(conversacion_id: uuid.UUID) -> object:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            return (await conexion.execute(LEER_DIALOGO, {"id": conversacion_id})).scalar_one()
    finally:
        await motor.dispose()


@pytest.fixture
def esquema_en_0030(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0030` y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0030")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def test_la_columna_existe_en_head_como_jsonb_nullable(esquema_migrado: None) -> None:
    assert asyncio.run(_columna()) == ("jsonb", "YES")


def test_downgrade_quita_la_columna_y_upgrade_la_devuelve(esquema_en_0030: None) -> None:
    assert asyncio.run(_columna()) is None

    command.upgrade(_config(), "head")

    assert asyncio.run(_columna()) == ("jsonb", "YES")


def test_una_conversacion_que_ya_existia_sube_sin_dialogo(esquema_en_0030: None) -> None:
    """Sin backfill: todas arrancan sin diálogo, y la fila vieja no se pierde."""
    conversacion_id = asyncio.run(_sembrar_conversacion_vieja())

    command.upgrade(_config(), "head")

    assert asyncio.run(_dialogo_de(conversacion_id)) is None
