"""Alembic environment.

Two decisions worth knowing before editing this file:

**Migrations connect as the table owner, the application does not.** The URL comes
from `DATABASE_URL_MIGRATIONS`, never from `DATABASE_URL`. PostgreSQL exempts a
table's owner from its own RLS policies, so if migrations and the application shared a
role, every policy in the system would be decorative. See migration 0001.

**Every persistence model must be imported here.** `Base.metadata` only knows about
the classes that have been imported, and a model missing from this list is a table
that autogenerate silently proposes to DROP.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context

# Imported for their side effect: registering their tables on Base.metadata.
from cheatsheet.contexts.identity.infrastructure import (
    models as _identity_models,  # noqa: F401
)
from cheatsheet.contexts.master_data.infrastructure import (
    models as _master_data_models,  # noqa: F401
)
from cheatsheet.contexts.observability.infrastructure import (
    models as _observability_models,  # noqa: F401
)
from cheatsheet.contexts.reference_data.infrastructure import (  # noqa: F401
    models as _reference_data_models,
)
from cheatsheet.platform.database import Base, argumentos_de_conexion
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    url = os.environ.get("DATABASE_URL_MIGRATIONS", "").strip()
    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL_MIGRATIONS. Las migraciones corren con el rol dueño "
            "de las tablas, distinto del rol de la aplicación (ver 0001)."
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting — used to review a migration."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _aplicar(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    seccion = config.get_section(config.config_ini_section, {})
    url = _url()
    seccion["sqlalchemy.url"] = url
    # The same TLS decision the application makes, from the same function: migrations
    # reach the managed database over the same network, with the owner's credential.
    engine = async_engine_from_config(
        seccion,
        prefix="sqlalchemy.",
        poolclass=NullPool,
        connect_args=argumentos_de_conexion(url),
    )
    async with engine.connect() as connection:
        await connection.run_sync(_aplicar)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
