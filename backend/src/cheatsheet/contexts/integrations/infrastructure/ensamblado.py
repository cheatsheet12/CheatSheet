"""Where the ports of this context meet their adapters.

Same shape as `identity`'s `ensamblado.py`: one place that knows which concrete class
satisfies each port, so the routers stay free of that knowledge and a test can swap any
piece without touching the use cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.integrations.application.ports import (
    PortAvisoDeIntegracion,
    PortCifradoDeCredenciales,
    PortMemoriaDeAutorizacion,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
    PortRepositorioTickets,
)
from cheatsheet.contexts.integrations.infrastructure.autorizaciones import (
    MemoriaDeAutorizacionRedis,
)
from cheatsheet.contexts.integrations.infrastructure.cifrado import CifradoAesGcm
from cheatsheet.contexts.integrations.infrastructure.email_integracion import AvisoPorEmail
from cheatsheet.contexts.integrations.infrastructure.registro import RegistroDeAdaptadores
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    RepositorioIntegracionesSQL,
    RepositorioTicketsSQL,
)
from cheatsheet.platform.email import crear_transporte
from cheatsheet.platform.settings import Settings


@dataclass(frozen=True, slots=True)
class Integraciones:
    """The pieces one request needs."""

    integraciones: PortRepositorioIntegraciones
    tickets: PortRepositorioTickets
    cifrado: PortCifradoDeCredenciales
    adaptadores: PortRegistroDeAdaptadores

    @classmethod
    def armar(cls, sesion: AsyncSession, settings: Settings) -> Integraciones:
        return cls(
            integraciones=RepositorioIntegracionesSQL(sesion),
            tickets=RepositorioTicketsSQL(sesion),
            cifrado=CifradoAesGcm(settings.secrets_encryption_key),
            adaptadores=registro_de_adaptadores(settings),
        )


def registro_de_adaptadores(settings: Settings) -> PortRegistroDeAdaptadores:
    """Every system real, or its own simulator, according to its `*_ADAPTADOR` variable.

    Every stand-in raises when built in production, so none of this can quietly become how
    a real company connects.
    """
    return RegistroDeAdaptadores.desde_settings(settings)


def crear_memoria_de_autorizacion(redis: Redis) -> PortMemoriaDeAutorizacion:
    """Where an OAuth2 authorization waits out the round trip to the provider.

    Takes the Redis client rather than `Settings` because it is process-lifetime, like
    `crear_aviso`: it holds no transaction, and the connection is opened once at startup.
    """
    return MemoriaDeAutorizacionRedis(redis)


def crear_aviso(settings: Settings) -> PortAvisoDeIntegracion:
    """The notice that reaches an Administrator who is not looking at the screen.

    Process-lifetime, like `crear_enviador` in identity: it holds no transaction.
    """
    return AvisoPorEmail(crear_transporte(settings), settings.app_base_url)
