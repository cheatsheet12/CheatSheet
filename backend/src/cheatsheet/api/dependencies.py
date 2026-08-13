"""Composition root — where interfaces meet their implementations.

Everything the application layer depends on is a `Protocol`; this is the one module
allowed to know which concrete class satisfies each one. That is what lets a test
swap the database for a fake without a mocking framework, and what will let ARCA be
swapped for a stub in epic 2.

**Scope matters here.** The engine and the Redis client live as long as the process.
The session, the repository, the use case and the publisher live as long as one
request — because the audit record must land in the same transaction as the operation
it describes. Building the publisher once at startup would silently give every
request a subscriber writing to somebody else's session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from cheatsheet.contexts.observability.application.registrar_operacion import RegistrarOperacion
from cheatsheet.contexts.observability.infrastructure.repository import (
    RepositorioDeAuditoriaPostgres,
)
from cheatsheet.contexts.observability.infrastructure.subscriber import SuscriptorDeAuditoria
from cheatsheet.platform.cache import (
    RegistroDeIdempotenciaRedis,
    crear_redis,
)
from cheatsheet.platform.database import crear_engine, crear_sessionmaker, sesion_de_empresa
from cheatsheet.platform.events import PublicadorEnProceso
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.clock import Reloj, RelojDelSistema
from cheatsheet.shared.empresa import EmpresaId


@dataclass(frozen=True, slots=True)
class Recursos:
    """Process-lifetime resources, created at startup and closed at shutdown."""

    settings: Settings
    engine: AsyncEngine
    sesiones: async_sessionmaker[AsyncSession]
    redis: Redis
    reloj: Reloj

    @classmethod
    def crear(cls, settings: Settings) -> Recursos:
        engine = crear_engine(settings)
        return cls(
            settings=settings,
            engine=engine,
            sesiones=crear_sessionmaker(engine),
            redis=crear_redis(settings),
            reloj=RelojDelSistema(),
        )

    async def cerrar(self) -> None:
        await self.redis.aclose()
        await self.engine.dispose()

    def idempotencia(self) -> RegistroDeIdempotenciaRedis:
        return RegistroDeIdempotenciaRedis(self.redis)


def construir_publicador(sesion: AsyncSession) -> PublicadorEnProceso:
    """Wire the audit sink onto one session.

    This is the single point where `all → observability` (Context Map §4) becomes
    executable code. No emitting context appears in this function, and no emitting
    context imports `observability` — that is rule R3 holding.
    """
    publicador = PublicadorEnProceso()
    repositorio = RepositorioDeAuditoriaPostgres(sesion)
    publicador.suscribir(SuscriptorDeAuditoria(RegistrarOperacion(repositorio)))
    return publicador


@dataclass(frozen=True, slots=True)
class UnidadDeTrabajo:
    """One request or one task: a transaction, and everything scoped to it."""

    sesion: AsyncSession
    publicador: PublicadorEnProceso
    reloj: Reloj


async def unidad_de_trabajo(
    recursos: Recursos, empresa_id: EmpresaId
) -> AsyncIterator[UnidadDeTrabajo]:
    """Open a company-scoped transaction with its event publisher attached."""
    async with sesion_de_empresa(recursos.sesiones, empresa_id) as sesion:
        yield UnidadDeTrabajo(
            sesion=sesion,
            publicador=construir_publicador(sesion),
            reloj=recursos.reloj,
        )
