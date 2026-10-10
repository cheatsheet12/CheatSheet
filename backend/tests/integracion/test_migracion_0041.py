"""Migration 0041 over existing data: the backfill of the terms and the up/down/up cycle.

A backfill proved only on an empty table proves nothing, so the schema goes down to `0040`,
companies are seeded the way they existed **before** the table (accepted terms in `empresa`
and a registration event in the audit log), the schema goes up to `0041` and each company is
looked at:

| Company at `0040`                                    | `aceptacion_legal` row after            |
| terms + `registrar_empresa` event by its user         | `TERMINOS`, attributed to that user     |
| terms + `registrar_empresa_con_google` event          | `TERMINOS`, attributed to that user     |
| terms, no registration event                          | `TERMINOS`, `usuario_id` NULL           |
| terms, event with no user (the system acted)          | `TERMINOS`, `usuario_id` NULL           |
| terms, event of an unrelated action on the company    | `TERMINOS`, `usuario_id` NULL           |
| no accepted terms                                     | none                                    |

No `PRIVACIDAD` row is ever created and `empresa` is not touched.

The tests are synchronous on purpose: `alembic.command` starts its own asyncio loop, and an
`async` test would already have one running. They need PostgreSQL and are skipped without it.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base
from tests.integracion.guarda import argumentos_de_conexion_de_prueba

pytestmark = [requiere_base, pytest.mark.integration]

ACEPTADO = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
EVENTO = datetime(2026, 8, 1, 11, 59, tzinfo=UTC)


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


@pytest.fixture
def esquema_en_0040(esquema_migrado: None) -> Iterator[None]:
    """Go down to `0040` and, whatever happens, leave the schema at `head` for the rest."""
    config = _config()
    command.downgrade(config, "0040")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def _motor() -> AsyncEngine:
    """The owner role: it sees every company (`BYPASSRLS`, ADR-0005) and can seed."""
    return create_async_engine(
        os.environ["DATABASE_URL_MIGRATIONS"],
        connect_args=argumentos_de_conexion_de_prueba(os.environ["DATABASE_URL_MIGRATIONS"]),
    )


CREAR_EMPRESA = text(
    "INSERT INTO empresa (id, activa, terminos_version, terminos_fecha_aceptacion) "
    "VALUES (:id, true, :version, :fecha)"
)
CREAR_USUARIO = text(
    "INSERT INTO usuario (id, empresa_id, email, nombre, rol, estado, pref_idioma, "
    "pref_zona_horaria, pref_suscripciones) VALUES (:id, :empresa_id, :email, 'Ana', "
    "'ADMINISTRADOR', 'ACTIVO', 'es', 'America/Argentina/Buenos_Aires', '{}'::jsonb)"
)
CREAR_EVENTO = text(
    "INSERT INTO registro_de_auditoria (id, evento_id, empresa_id, usuario_id, modulo, accion, "
    "entidad_afectada, resultado, timestamp) VALUES (gen_random_uuid(), gen_random_uuid(), "
    ":empresa_id, :usuario_id, 'IDENTITY', :accion, :entidad, 'COMPLETADO', :cuando)"
)


async def _empresa(
    conexion: Any,
    *,
    version: str | None = "1.0",
    accion: str | None = "registrar_empresa",
    evento_con_usuario: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    """One company in the shape it had before the table, and the user the event names (if any)."""
    empresa_id, usuario_id = uuid.uuid4(), uuid.uuid4()
    await conexion.execute(
        CREAR_EMPRESA,
        {
            "id": empresa_id,
            "version": version,
            "fecha": ACEPTADO if version is not None else None,
        },
    )
    await conexion.execute(
        CREAR_USUARIO,
        {"id": usuario_id, "empresa_id": empresa_id, "email": f"{usuario_id}@empresa.com"},
    )
    if accion is not None:
        await conexion.execute(
            CREAR_EVENTO,
            {
                "empresa_id": empresa_id,
                "usuario_id": usuario_id if evento_con_usuario else None,
                "accion": accion,
                "entidad": f"Empresa:{empresa_id}",
                "cuando": EVENTO,
            },
        )
    return empresa_id, usuario_id


async def _sembrar() -> dict[str, tuple[uuid.UUID, uuid.UUID]]:
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            return {
                "email": await _empresa(conexion),
                "google": await _empresa(conexion, accion="registrar_empresa_con_google"),
                "sin_evento": await _empresa(conexion, accion=None),
                "evento_del_sistema": await _empresa(conexion, evento_con_usuario=False),
                "otra_accion": await _empresa(conexion, accion="invitar_usuario"),
                "sin_terminos": await _empresa(conexion, version=None),
            }
    finally:
        await motor.dispose()


LEER_FILAS = text(
    "SELECT empresa_id, usuario_id, documento, version, fecha_aceptacion FROM aceptacion_legal"
)
LEER_EMPRESAS = text(
    "SELECT id, terminos_version, terminos_fecha_aceptacion FROM empresa ORDER BY id"
)
EXISTE_LA_TABLA = text("SELECT to_regclass('public.aceptacion_legal') IS NOT NULL")


async def _leer(consulta: TextClause) -> list[dict[str, Any]]:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            return [dict(f) for f in (await conexion.execute(consulta)).mappings().all()]
    finally:
        await motor.dispose()


def _por_empresa(filas: list[dict[str, Any]]) -> dict[uuid.UUID, dict[str, Any]]:
    return {f["empresa_id"]: f for f in filas}


def test_el_backfill_crea_una_fila_de_terminos_por_empresa_atribuida_por_la_bitacora(
    esquema_en_0040: None,
) -> None:
    sembradas = asyncio.run(_sembrar())

    command.upgrade(_config(), "0041")

    filas = asyncio.run(_leer(LEER_FILAS))
    por_empresa = _por_empresa(filas)
    assert len(filas) == 5, "one per company with accepted terms, none for the sixth"
    for clave in ("email", "google"):
        empresa_id, usuario_id = sembradas[clave]
        assert por_empresa[empresa_id]["usuario_id"] == usuario_id, clave
    for clave in ("sin_evento", "evento_del_sistema", "otra_accion"):
        empresa_id, _ = sembradas[clave]
        assert por_empresa[empresa_id]["usuario_id"] is None, clave
    assert sembradas["sin_terminos"][0] not in por_empresa
    for fila in filas:
        assert fila["documento"] == "TERMINOS"
        assert fila["version"] == "1.0"
        assert fila["fecha_aceptacion"] == ACEPTADO


def test_el_backfill_no_toca_empresa_ni_inventa_privacidad(esquema_en_0040: None) -> None:
    sembradas = asyncio.run(_sembrar())
    antes = asyncio.run(_leer(LEER_EMPRESAS))

    command.upgrade(_config(), "0041")

    assert asyncio.run(_leer(LEER_EMPRESAS)) == antes
    assert all(f["documento"] != "PRIVACIDAD" for f in asyncio.run(_leer(LEER_FILAS)))
    assert len(sembradas) == 6


def test_la_migracion_sube_baja_y_vuelve_a_subir(esquema_en_0040: None) -> None:
    asyncio.run(_sembrar())
    config = _config()

    command.upgrade(config, "0041")
    command.downgrade(config, "0040")

    # Declared loss: the history goes with the table; `empresa` keeps the last acceptance.
    motor_vacio = asyncio.run(_leer(EXISTE_LA_TABLA))
    assert list(motor_vacio[0].values()) == [False]
    assert all(e["terminos_version"] in ("1.0", None) for e in asyncio.run(_leer(LEER_EMPRESAS)))

    command.upgrade(config, "0041")

    assert len(asyncio.run(_leer(LEER_FILAS))) == 5
