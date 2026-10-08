"""La migración 0034: `cobro.clave_idempotencia` y su índice único parcial (ADR-0013, caso 15).

Sube y baja limpia sobre una base con cobros existentes, que quedan con `NULL`. Son síncronos a
propósito, como `test_migracion_0033.py`: `alembic.command` arranca su propio loop de asyncio.
Necesitan PostgreSQL: se saltean sin base y corren en CI.
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

AHORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Ana Diaz', 'PANEL', true, :ahora, :ahora)"
)
COBRO_VIEJO = text(
    "INSERT INTO cobro (id, empresa_id, cliente_id, monto, descripcion, estado, vence_el, "
    "created_at, updated_at) "
    "VALUES (:id, :empresa_id, :cliente_id, 100.00, 'Viejo', 'PENDIENTE', :ahora, :ahora, :ahora)"
)
COBRO_CON_CLAVE = text(
    "INSERT INTO cobro (id, empresa_id, cliente_id, monto, descripcion, estado, vence_el, "
    "created_at, updated_at, clave_idempotencia) "
    "VALUES (:id, :empresa_id, :cliente_id, 100.00, 'Nuevo', 'PENDIENTE', :ahora, :ahora, :ahora, "
    ":clave)"
)
LEER_CLAVE = text("SELECT clave_idempotencia FROM cobro WHERE id = :id")
COLUMNA = text(
    "SELECT count(*) FROM information_schema.columns "
    "WHERE table_name = 'cobro' AND column_name = 'clave_idempotencia'"
)
INDICE = text("SELECT to_regclass('uq_cobro_clave_idempotencia') IS NOT NULL")


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _motor() -> AsyncEngine:
    """El rol dueño: ve todas las empresas (`BYPASSRLS`, ADR-0005) y puede sembrar."""
    return create_async_engine(os.environ["DATABASE_URL_MIGRATIONS"])


async def _sembrar_cobro_viejo() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    empresa_id, cliente_id, cobro_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
            await conexion.execute(
                CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
            )
            await conexion.execute(
                COBRO_VIEJO,
                {
                    "id": cobro_id,
                    "empresa_id": empresa_id,
                    "cliente_id": cliente_id,
                    "ahora": AHORA,
                },
            )
    finally:
        await motor.dispose()
    return empresa_id, cliente_id, cobro_id


async def _insertar_con_clave(
    empresa_id: uuid.UUID, cliente_id: uuid.UUID, clave: uuid.UUID
) -> None:
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            await conexion.execute(
                COBRO_CON_CLAVE,
                {
                    "id": uuid.uuid4(),
                    "empresa_id": empresa_id,
                    "cliente_id": cliente_id,
                    "ahora": AHORA,
                    "clave": clave,
                },
            )
    finally:
        await motor.dispose()


async def _leer(
    sentencia: object, parametros: dict[str, object] | None = None
) -> tuple[object, ...]:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            fila = (await conexion.execute(sentencia, parametros or {})).one()  # type: ignore[call-overload]
    finally:
        await motor.dispose()
    return tuple(fila)


@pytest.fixture
def esquema_en_0033(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0033` y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0033")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def test_downgrade_deja_el_cobro_sin_la_columna_ni_el_indice(esquema_en_0033: None) -> None:
    assert asyncio.run(_leer(COLUMNA)) == (0,)
    assert asyncio.run(_leer(INDICE)) == (False,)


def test_upgrade_deja_los_cobros_existentes_con_null_y_sin_backfill(esquema_en_0033: None) -> None:
    _, _, cobro_id = asyncio.run(_sembrar_cobro_viejo())

    command.upgrade(_config(), "head")

    assert asyncio.run(_leer(LEER_CLAVE, {"id": cobro_id})) == (None,)
    assert asyncio.run(_leer(COLUMNA)) == (1,)
    assert asyncio.run(_leer(INDICE)) == (True,)


def test_el_indice_rechaza_la_misma_clave_en_la_misma_empresa(esquema_en_0033: None) -> None:
    empresa_id, cliente_id, _ = asyncio.run(_sembrar_cobro_viejo())
    command.upgrade(_config(), "head")
    clave = uuid.uuid4()
    asyncio.run(_insertar_con_clave(empresa_id, cliente_id, clave))

    with pytest.raises(IntegrityError):
        asyncio.run(_insertar_con_clave(empresa_id, cliente_id, clave))


def test_baja_y_sube_otra_vez_sin_perder_los_cobros(esquema_en_0033: None) -> None:
    _, _, cobro_id = asyncio.run(_sembrar_cobro_viejo())
    command.upgrade(_config(), "head")
    command.downgrade(_config(), "0033")
    command.upgrade(_config(), "head")

    assert asyncio.run(_leer(LEER_CLAVE, {"id": cobro_id})) == (None,)
