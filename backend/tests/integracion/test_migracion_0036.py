"""La migración 0036: la tabla `pago_sin_imputar` (unidad `pagos-sin-cobro-asociado`, caso 15).

Sube y baja limpia sobre una base con cobros existentes, que no se tocan. Son síncronos a
propósito, como `test_migracion_0034.py`: `alembic.command` arranca su propio loop de asyncio.
Necesitan PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)

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
CONTAR_COBROS = text("SELECT count(*) FROM cobro WHERE id = :id")
TABLA = text("SELECT to_regclass('pago_sin_imputar') IS NOT NULL")
INDICE = text("SELECT to_regclass('uq_pago_sin_imputar_payment') IS NOT NULL")
POLITICA = text("SELECT count(*) FROM pg_policies WHERE tablename = 'pago_sin_imputar'")
PRIVILEGIOS = text(
    "SELECT privilege_type FROM information_schema.role_table_grants "
    "WHERE table_name = 'pago_sin_imputar' AND grantee = 'cheatsheet_app' "
    "ORDER BY privilege_type"
)
RLS_FORZADA = text(
    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'pago_sin_imputar'"
)
INSERTAR = text(
    "INSERT INTO pago_sin_imputar (id, empresa_id, mp_payment_id, motivo, monto, recibido_en) "
    "VALUES (:id, :empresa_id, 'pago-1', 'SIN_COBRO', 1210.50, :ahora)"
)
LEER_MONTO = text("SELECT monto FROM pago_sin_imputar WHERE id = :id")


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _motor() -> AsyncEngine:
    """El rol dueño: ve todas las empresas (`BYPASSRLS`, ADR-0005) y puede sembrar."""
    return create_async_engine(os.environ["DATABASE_URL_MIGRATIONS"])


async def _sembrar_cobro_viejo() -> tuple[uuid.UUID, uuid.UUID]:
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
    return empresa_id, cobro_id


async def _insertar_pago(empresa_id: uuid.UUID) -> uuid.UUID:
    pago_id = uuid.uuid4()
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            await conexion.execute(
                INSERTAR, {"id": pago_id, "empresa_id": empresa_id, "ahora": AHORA}
            )
    finally:
        await motor.dispose()
    return pago_id


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


@pytest.fixture
def esquema_en_0035(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0035` y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0035")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def test_downgrade_deja_la_base_sin_la_tabla_ni_el_indice(esquema_en_0035: None) -> None:
    assert asyncio.run(_leer(TABLA)) == [(False,)]
    assert asyncio.run(_leer(INDICE)) == [(False,)]


def test_upgrade_crea_la_tabla_solo_insercion_con_rls_forzada(esquema_en_0035: None) -> None:
    command.upgrade(_config(), "head")

    assert asyncio.run(_leer(TABLA)) == [(True,)]
    assert asyncio.run(_leer(INDICE)) == [(True,)]
    assert asyncio.run(_leer(RLS_FORZADA)) == [(True, True)]
    assert asyncio.run(_leer(POLITICA)) == [(1,)]
    # Solo `SELECT` e `INSERT`: sin `UPDATE` ni `DELETE`.
    assert asyncio.run(_leer(PRIVILEGIOS)) == [("INSERT",), ("SELECT",)]


def test_upgrade_no_toca_los_cobros_existentes_ni_inventa_pagos(esquema_en_0035: None) -> None:
    empresa_id, cobro_id = asyncio.run(_sembrar_cobro_viejo())

    command.upgrade(_config(), "head")

    assert asyncio.run(_leer(CONTAR_COBROS, {"id": cobro_id})) == [(1,)]
    cuenta = asyncio.run(
        _leer(
            text("SELECT count(*) FROM pago_sin_imputar WHERE empresa_id = :e"), {"e": empresa_id}
        )
    )
    assert cuenta == [(0,)]


def test_baja_y_sube_otra_vez_sin_perder_los_cobros(esquema_en_0035: None) -> None:
    empresa_id, cobro_id = asyncio.run(_sembrar_cobro_viejo())
    command.upgrade(_config(), "head")
    pago_id = asyncio.run(_insertar_pago(empresa_id))
    assert asyncio.run(_leer(LEER_MONTO, {"id": pago_id})) == [(Decimal("1210.50"),)]

    command.downgrade(_config(), "0035")
    command.upgrade(_config(), "head")

    # El `downgrade` borra los registros (pérdida declarada); los cobros quedan.
    assert asyncio.run(_leer(CONTAR_COBROS, {"id": cobro_id})) == [(1,)]
    assert asyncio.run(_leer(LEER_MONTO, {"id": pago_id})) == []
