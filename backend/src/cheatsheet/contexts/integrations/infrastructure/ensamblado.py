"""Where the ports of this context meet their adapters.

Same shape as `identity`'s `ensamblado.py`: one place that knows which concrete class
satisfies each port, so the routers stay free of that knowledge and a test can swap any
piece without touching the use cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.integrations.application.padron import PortTicketDePadron
from cheatsheet.contexts.integrations.application.ports import (
    PortAvisoDeIntegracion,
    PortCifradoDeCredenciales,
    PortMemoriaDeAutorizacion,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
    PortRepositorioTickets,
)
from cheatsheet.contexts.integrations.application.tickets_de_plataforma import (
    ObtenerTicketDePlataforma,
)
from cheatsheet.contexts.integrations.infrastructure.arca.firma import leer_credencial
from cheatsheet.contexts.integrations.infrastructure.arca.simulado import TicketDePadronSimulado
from cheatsheet.contexts.integrations.infrastructure.autorizaciones import (
    MemoriaDeAutorizacionRedis,
)
from cheatsheet.contexts.integrations.infrastructure.cifrado import CifradoAesGcm
from cheatsheet.contexts.integrations.infrastructure.email_integracion import AvisoPorEmail
from cheatsheet.contexts.integrations.infrastructure.registro import (
    RegistroDeAdaptadores,
    emisor_de_arca,
)
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    RepositorioIntegracionesSQL,
    RepositorioTicketsDePlataformaSQL,
    RepositorioTicketsSQL,
)
from cheatsheet.platform.email import crear_transporte
from cheatsheet.platform.settings import AdaptadorDeArca, Settings
from cheatsheet.shared.clock import RelojDelSistema


@dataclass(frozen=True, slots=True)
class Integraciones:
    """The pieces one request needs."""

    integraciones: PortRepositorioIntegraciones
    tickets: PortRepositorioTickets
    cifrado: PortCifradoDeCredenciales
    adaptadores: PortRegistroDeAdaptadores
    #: ADR-0014: the platform certificate's ticket, bound to this request's transaction.
    tickets_de_plataforma: ObtenerTicketDePlataforma
    #: The padrón's ticket: the platform's, or a fabricated one when the padrón is simulated.
    tickets_de_padron: PortTicketDePadron

    @classmethod
    def armar(cls, sesion: AsyncSession, settings: Settings) -> Integraciones:
        cifrado = CifradoAesGcm(settings.secrets_encryption_key)
        reloj = RelojDelSistema()
        tickets_de_plataforma = ObtenerTicketDePlataforma(
            tickets=RepositorioTicketsDePlataformaSQL(sesion),
            cifrado=cifrado,
            emisor=emisor_de_arca(settings, reloj),
            credencial=settings.arca_credencial_plataforma,
            reloj=reloj,
            margen=timedelta(minutes=settings.arca_margen_renovacion_minutos),
        )
        return cls(
            integraciones=RepositorioIntegracionesSQL(sesion),
            tickets=RepositorioTicketsSQL(sesion),
            cifrado=cifrado,
            adaptadores=RegistroDeAdaptadores.desde_settings(settings, tickets_de_plataforma),
            tickets_de_plataforma=tickets_de_plataforma,
            tickets_de_padron=(
                TicketDePadronSimulado(entorno=settings.entorno, reloj=reloj)
                if settings.arca_padron_adaptador is AdaptadorDeArca.SIMULADO
                else tickets_de_plataforma
            ),
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


def cuit_de_plataforma(settings: Settings) -> str:
    """The CUIT of the platform certificate (ADR-0014): who asks ARCA's registry.

    Empty with the simulator, which has no certificate and authenticates nothing.
    """
    if not settings.arca_credencial_plataforma:
        return ""
    return leer_credencial(settings.arca_credencial_plataforma).cuit
