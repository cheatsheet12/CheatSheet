"""The migration must be reversible, and it must leave RLS actually switched on.

A `downgrade` nobody ever runs is a `downgrade` that does not work, and the moment it
matters is the moment a deploy has to be rolled back. So it is exercised here.

The second test checks the two flags that are easy to write and easy to get wrong:
`ENABLE` without `FORCE` produces a policy that never applies to the table's owner,
which is the failure mode where everything looks configured and nothing is protected.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


@pytest.mark.asyncio
async def test_la_tabla_tiene_rls_habilitada_y_forzada(engine_dueno: AsyncEngine):
    async with engine_dueno.connect() as conexion:
        fila = (
            await conexion.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = 'registro_de_auditoria'"
                )
            )
        ).one()

    habilitada, forzada = fila
    assert habilitada is True
    assert forzada is True, "Sin FORCE, el dueño de la tabla ignora la política"


@pytest.mark.asyncio
async def test_la_politica_de_aislamiento_existe(engine_dueno: AsyncEngine):
    async with engine_dueno.connect() as conexion:
        politicas = (
            await conexion.execute(
                text("SELECT policyname FROM pg_policies WHERE tablename = 'registro_de_auditoria'")
            )
        ).scalars()

    assert "aislamiento_por_empresa" in list(politicas)


@pytest.mark.asyncio
async def test_el_rol_de_aplicacion_no_tiene_update_ni_delete(engine_dueno: AsyncEngine):
    """HS-T5 RN-03 expressed as a grant, which is what actually stops a stray UPDATE."""
    async with engine_dueno.connect() as conexion:
        privilegios = (
            await conexion.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_name = 'registro_de_auditoria' AND grantee = 'cheatsheet_app'"
                )
            )
        ).scalars()

    otorgados = set(privilegios)
    assert otorgados == {"SELECT", "INSERT"}


def test_la_migracion_revierte_y_vuelve_a_aplicar(esquema_migrado: None):
    """`downgrade` is exercised, because the day it matters there is no time to fix it."""
    config = _config()

    command.downgrade(config, "base")
    command.upgrade(config, "head")
