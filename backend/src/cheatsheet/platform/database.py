"""Database access, and the second barrier that keeps tenants apart (ADR-002).

Multi-tenancy here is shared schema plus PostgreSQL Row-Level Security. The
application also filters by `empresa_id`, but that filter is code, and code has bugs.
RLS is the barrier that holds when the code is wrong: the database itself refuses to
return another company's rows.

It only works if two things are true, and both are easy to get silently wrong:

- **The connection announces who it is.** Every transaction sets
  `app.current_empresa`; the policies read it. A session that never sets it sees
  nothing at all — the failure is closed, which is the only acceptable direction.
- **The application is not the owner of the tables.** PostgreSQL exempts a table's
  owner from its own policies. Migrations run as the owner, the application runs as
  `cheatsheet_app`, and the tables are additionally marked `FORCE ROW LEVEL
  SECURITY`. Without this split the policies exist and never fire, and every test
  that "proves" isolation proves nothing.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId

# The GUC the RLS policies read. Defined once: a typo in a policy and a typo here
# cancel each other out and open every tenant to every other.
GUC_EMPRESA = "app.current_empresa"

#: Hosts that are this machine. Everything else crosses a network we do not own.
HOSTS_LOCALES = frozenset({"localhost", "127.0.0.1", "::1", ""})

#: TLS settings that belong in code, and that a copied provider URL brings along.
PARAMETROS_TLS_EN_LA_URL = ("ssl", "sslmode", "sslrootcert", "channel_binding")

#: Seconds to wait for a connection before giving up (`CLAUDE.md` §5). A managed
#: database wakes suspended compute on the first connection, so this is not two.
TIMEOUT_DE_CONEXION_SEGUNDOS = 10


class ConfiguracionDeConexionInvalida(RuntimeError):
    """The database URL carries something that would fail later, and confusingly."""


class Base(DeclarativeBase):
    """Declarative base shared by every context's persistence models.

    One base, one `metadata`, one set of migrations — the contexts are modules inside
    one database (ADR-001/ADR-004), not separate schemas.
    """


def argumentos_de_conexion(url: str) -> dict[str, Any]:
    """Decide TLS here, from the host, instead of leaving it in the connection string.

    Anything that is not this machine is reached over a network we do not own, and the
    credential travels on it. So: a remote host gets a **verified** TLS context, and
    localhost — the disposable container of a laptop or a CI job — gets none.

    This is a decision and not a passthrough, because every way of expressing it in the
    URL is a trap with asyncpg, which follows libpq's semantics rather than Python's:

    - ``?ssl=verify-full`` does **not** use the system trust store. It looks for a CA at
      ``~/.postgresql/root.crt`` or ``PGSSLROOTCERT`` and raises if neither exists — so
      it works on the machine that was set up and nowhere else.
    - ``?ssl=require`` is worse: with no CA file it silently falls back to
      ``CERT_NONE``. The connection is encrypted and the server is never identified,
      which is the failure that looks exactly like success.

    ``ssl.create_default_context()`` loads the platform's own CA store with
    ``check_hostname`` on and ``CERT_REQUIRED``, which is what ``verify-full`` was meant
    to mean. Passing the context object is the only way to hand asyncpg that, and a
    context can only travel through ``connect_args`` — never through the URL.

    The consequence: **the URL carries no TLS parameter at all**, and one that does is
    rejected here rather than forwarded. SQLAlchemy passes every query parameter to
    ``asyncpg.connect()`` as a keyword argument, so leaving them in produces either a
    duplicate ``ssl`` or an unknown ``sslmode``/``channel_binding`` — a ``TypeError``
    raised deep inside the driver, about a string nobody typed on purpose. The managed
    provider hands out exactly such a URL to copy, so this is the expected mistake, not
    an exotic one.

    Every connection also carries an explicit timeout (``CLAUDE.md`` §5). Without one,
    asyncpg waits on its own default while the caller — a request, a Celery task, a
    migration — has no way to know the database is simply unreachable.
    """
    parseada = make_url(url)
    presentes = sorted(p for p in PARAMETROS_TLS_EN_LA_URL if p in parseada.query)
    if presentes:
        raise ConfiguracionDeConexionInvalida(
            f"La URL de la base declara {', '.join(presentes)}. El TLS se decide en "
            f"argumentos_de_conexion(), no en la cadena de conexion: borra esos "
            f"parametros de la URL. Ver docs/staging-database.md."
        )
    argumentos: dict[str, Any] = {"timeout": TIMEOUT_DE_CONEXION_SEGUNDOS}
    if (parseada.host or "").lower() not in HOSTS_LOCALES:
        argumentos["ssl"] = ssl.create_default_context()
    return argumentos


def crear_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=False,
        connect_args=argumentos_de_conexion(settings.database_url),
    )


def crear_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def sesion_de_empresa(
    fabrica: async_sessionmaker[AsyncSession],
    empresa_id: EmpresaId,
) -> AsyncIterator[AsyncSession]:
    """Open a transaction scoped to one company, and commit or roll it back as one.

    `set_config(..., true)` is the transaction-local form of `SET LOCAL`: the setting
    dies with the transaction, so a pooled connection handed to the next request never
    carries the previous tenant with it.

    The value is bound as a parameter, never interpolated. It arrives from a JWT and
    that is untrusted input like any other.
    """
    async with fabrica() as sesion:
        try:
            await sesion.execute(
                text("SELECT set_config(:clave, :valor, true)"),
                {"clave": GUC_EMPRESA, "valor": str(empresa_id)},
            )
            yield sesion
            await sesion.commit()
        except Exception:
            await sesion.rollback()
            raise


@asynccontextmanager
async def sesion_sin_empresa(
    fabrica: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A read-only session for the handful of lookups that happen before there is a tenant.

    Signing in, refreshing and accepting an invitation all have the same shape: the caller
    holds a credential and the company is what has to be *discovered* from it. Those
    lookups go through the `SECURITY DEFINER` functions, which are unaffected by
    Row-Level Security by design and return the bare minimum.

    **`app.current_empresa` is deliberately left unset**, so every ordinary query through
    this session sees nothing at all — `test_sin_empresa_declarada_no_se_ve_nada` is the
    proof. Announcing an invented UUID instead, which is what this code used to do, is
    strictly worse: it looks like a tenant, and any write attempted under it is rejected
    by the policy — silently, in the case of an `UPDATE`.

    Nothing is written here and nothing is committed. The caller opens a real unit of work
    with the company this returns.
    """
    async with fabrica() as sesion:
        try:
            yield sesion
        finally:
            await sesion.rollback()


async def verificar_conexion(engine: AsyncEngine) -> bool:
    """Cheapest possible liveness probe, for the healthcheck."""
    async with engine.connect() as conexion:
        await conexion.execute(text("SELECT 1"))
    return True
