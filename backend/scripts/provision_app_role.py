#!/usr/bin/env python3
"""Create the application role on a managed PostgreSQL, and refuse to leave it dangerous.

The multi-tenant barrier of this system is Row-Level Security (ADR-002), and RLS only
applies to a role that neither owns the tables nor holds `BYPASSRLS`. Migration 0001
creates `cheatsheet_app` owning nothing; this script is what gives it a login, and what
checks that the provider did not quietly hand it an exemption.

On Neon that is not hypothetical: every role created through the console, the API or the
CLI is granted membership in `neon_superuser`, which carries `BYPASSRLS`. A role created
that way looks identical from the application's side and silently disables every
`aislamiento_por_empresa` policy in the database. Hence the assertion at the end, which
fails the script rather than leaving a role that merely looks right.

    APP_ROLE_PASSWORD=... DATABASE_URL_MIGRATIONS=... python backend/scripts/provision_app_role.py

Run it as the owner, before `alembic upgrade head`. It is idempotent: running it again
rotates the password and re-checks everything. See docs/staging-database.md.

Both values are read from the environment and never from the command line: arguments are
visible in the process list and land in shell history, and one of these is a credential.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

from cheatsheet.platform.database import argumentos_de_conexion
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

ROL_APP = "cheatsheet_app"
GUC_NUEVA_CLAVE = "cheatsheet.clave_a_asignar"
LARGO_MINIMO = 16

# The alphabet of `secrets.token_urlsafe`. Narrow on purpose, and for a second reason
# beyond safety: this password ends up inside a connection URL, and a `@`, `/`, `:` or
# `#` there truncates the host and produces an error that looks like anything but a
# quoting problem.
PASSWORD_ACEPTABLE = re.compile(r"^[A-Za-z0-9_-]+$")

_log = logging.getLogger("provision_app_role")


def _motor(url: str) -> AsyncEngine:
    """One engine per run, no pool, and exactly the TLS the application would use."""
    return create_async_engine(url, poolclass=NullPool, connect_args=argumentos_de_conexion(url))


# SQL identifiers and passwords cannot be bound as parameters — they are part of utility
# statements, which PostgreSQL does not plan. Building the statement in Python would mean
# quoting a credential by hand, so instead the value is bound into a session setting and
# quoted server-side by `format(..., %L)`. Nothing is concatenated on this side.
# Transaction-local (`true`): the value dies with the transaction instead of
# lingering on the session, which is the right lifetime for a credential.
SQL_GUARDAR_PASSWORD = text("SELECT set_config(:clave, :valor, true)")

SQL_CREAR_ROL = text(
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cheatsheet_app') THEN
            CREATE ROLE cheatsheet_app NOLOGIN;
        END IF;
    END
    $$
    """
)

SQL_ASIGNAR_PASSWORD = text(
    """
    DO $$
    BEGIN
        EXECUTE format('ALTER ROLE cheatsheet_app WITH LOGIN PASSWORD %L',
                       current_setting('cheatsheet.clave_a_asignar'));
    END
    $$
    """
)

# CONNECT on the database and USAGE on the schema are the only privileges granted here.
# Table grants belong to the migrations, one table at a time — that is what keeps the
# audit log append-only (0001) instead of granting broadly and revoking later.
SQL_GRANTS = text(
    """
    DO $$
    BEGIN
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO cheatsheet_app', current_database());
        EXECUTE 'GRANT USAGE ON SCHEMA public TO cheatsheet_app';
    END
    $$
    """
)

SQL_EVASORES = text(
    """
    SELECT string_agg(r.rolname, ', ' ORDER BY r.rolname)
      FROM pg_roles r
     WHERE r.rolbypassrls
       AND pg_has_role(:rol, r.oid, 'USAGE')
    """
)

SQL_ES_SUPERUSUARIO = text("SELECT rolsuper FROM pg_roles WHERE rolname = :rol")


class ProvisionInvalida(RuntimeError):
    """The role exists but is not safe to use. Never swallowed, never downgraded."""


def _password() -> str:
    valor = os.environ.get("APP_ROLE_PASSWORD", "").strip()
    if not valor:
        raise ProvisionInvalida(
            "Falta APP_ROLE_PASSWORD. Genera una con:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(24))"'
        )
    if len(valor) < LARGO_MINIMO:
        raise ProvisionInvalida(
            f"APP_ROLE_PASSWORD tiene {len(valor)} caracteres; el minimo es {LARGO_MINIMO}."
        )
    if not PASSWORD_ACEPTABLE.match(valor):
        raise ProvisionInvalida(
            "APP_ROLE_PASSWORD solo puede tener letras, digitos, '-' y '_'. "
            "Va dentro de una URL de conexion, y otros caracteres la rompen en silencio."
        )
    return valor


def _url_del_dueno() -> str:
    valor = os.environ.get("DATABASE_URL_MIGRATIONS", "").strip()
    if not valor:
        raise ProvisionInvalida(
            "Falta DATABASE_URL_MIGRATIONS. Es la URL del rol DUENO, la misma que usa "
            "Alembic — no la de la aplicacion. Ver docs/staging-database.md."
        )
    return valor


async def _verificar(conexion: AsyncConnection) -> None:
    """Refuse to report success if the role can ignore the policies."""
    evasores = (await conexion.execute(SQL_EVASORES, {"rol": ROL_APP})).scalar_one_or_none()
    if evasores is not None:
        raise ProvisionInvalida(
            f"{ROL_APP} evade Row-Level Security (via: {evasores}).\n"
            "El rol fue creado desde la consola de Neon en lugar de por SQL: ahi se hereda\n"
            "neon_superuser, que trae BYPASSRLS, y ninguna politica de aislamiento se aplica.\n"
            f"Borralo (DROP ROLE {ROL_APP}) y volve a correr este script."
        )
    es_super = (await conexion.execute(SQL_ES_SUPERUSUARIO, {"rol": ROL_APP})).scalar_one_or_none()
    if bool(es_super):
        raise ProvisionInvalida(f"{ROL_APP} es superusuario: ninguna politica se le aplicaria.")


async def _provisionar() -> None:
    motor = _motor(_url_del_dueno())
    password = _password()
    try:
        async with motor.begin() as conexion:
            await conexion.execute(SQL_CREAR_ROL)
            await conexion.execute(
                SQL_GUARDAR_PASSWORD, {"clave": GUC_NUEVA_CLAVE, "valor": password}
            )
            await conexion.execute(SQL_ASIGNAR_PASSWORD)
            await conexion.execute(SQL_GRANTS)
            await _verificar(conexion)
    finally:
        await motor.dispose()


def main() -> int:
    # stdout, not stderr: PowerShell renders anything a native command writes to stderr
    # as a NativeCommandError, in red, so a successful run would read as a failure on
    # the platform this team uses. The report is this tool's output, not a diagnostic
    # aside, and the exit code is what carries pass or fail.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    try:
        asyncio.run(_provisionar())
    except ProvisionInvalida as error:
        _log.error("%s", error)
        return 1
    except SQLAlchemyError as error:
        _log.error("No se pudo provisionar el rol: %s", error)
        return 2
    _log.info(
        "Rol %s provisto: con LOGIN, sin BYPASSRLS, sin ser dueno de nada.\n"
        "Siguiente paso: alembic -c backend/alembic.ini upgrade head",
        ROL_APP,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
