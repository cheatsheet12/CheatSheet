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

from cheatsheet.contexts.identity.infrastructure.repositories import RepositorioUsuarioPostgres
from cheatsheet.contexts.observability.application.notificaciones import NotificarPorEventos
from cheatsheet.contexts.observability.application.registrar_operacion import RegistrarOperacion
from cheatsheet.contexts.observability.infrastructure.destinatarios import DestinatariosViaIdentity
from cheatsheet.contexts.observability.infrastructure.notificaciones_repository import (
    RepositorioNotificacionesPostgres,
)
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


def construir_publicador(sesion: AsyncSession, empresa_id: EmpresaId) -> PublicadorEnProceso:
    """Wire the two sinks onto one session: the audit log and the notification centre.

    This is the single point where `all → observability` (Context Map §4) becomes
    executable code. No emitting context appears in this function, and no emitting
    context imports `observability` — that is rule R3 holding.

    **The order matters and the second one cannot break the first.** Auditing is the record
    that the operation happened; notifying is a courtesy about it. `NotificarPorEventos`
    swallows its own failures for that reason (see its docstring), so a panel notice that
    could not be written never undoes the work it was describing.
    """
    publicador = PublicadorEnProceso()
    repositorio = RepositorioDeAuditoriaPostgres(sesion)
    publicador.suscribir(SuscriptorDeAuditoria(RegistrarOperacion(repositorio)))
    publicador.suscribir(
        NotificarPorEventos(
            notificaciones=RepositorioNotificacionesPostgres(sesion),
            destinatarios=DestinatariosViaIdentity(
                RepositorioUsuarioPostgres(sesion), empresa_id=empresa_id
            ),
        )
    )
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
    """Open a company-scoped transaction with its event publisher attached.

    **Trap: an exception in the `async for` body discards the transaction.** The commit sits
    after the `yield`, and a body that raises never resumes this generator, so everything
    written before the raise is rolled back. That is what a use case that writes and then
    fails on purpose needs to avoid (e.g. token-reuse detection, which revokes a family and
    then raises). To commit a write and still fail, catch the error inside the body, let the
    loop end, and re-raise after it: see `refresh` in `routers/auth.py`.
    """
    async with sesion_de_empresa(recursos.sesiones, empresa_id) as sesion:
        yield UnidadDeTrabajo(
            sesion=sesion,
            publicador=construir_publicador(sesion, empresa_id),
            reloj=recursos.reloj,
        )
