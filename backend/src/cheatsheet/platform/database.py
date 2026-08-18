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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
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


class Base(DeclarativeBase):
    """Declarative base shared by every context's persistence models.

    One base, one `metadata`, one set of migrations — the contexts are modules inside
    one database (ADR-001/ADR-004), not separate schemas.
    """


def crear_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=False,
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
