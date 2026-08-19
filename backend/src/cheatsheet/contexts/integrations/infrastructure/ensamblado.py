"""Where the ports of this context meet their adapters.

Same shape as `identity`'s `ensamblado.py`: one place that knows which concrete class
satisfies each port, so the routers stay free of that knowledge and a test can swap any
piece without touching the use cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.integrations.application.ports import (
    PortAvisoDeIntegracion,
    PortCifradoDeCredenciales,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
    PortRepositorioTickets,
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
    """WhatsApp is real (or its own simulator); ARCA and MercadoPago are still stand-ins.

    Every stand-in raises when built in production, so none of this can quietly become how
    a real company connects. `conexion-arca` and `conexion-mercadopago` each replace one
    more entry inside `RegistroDeAdaptadores` and touch nothing else.
    """
    return RegistroDeAdaptadores.desde_settings(settings)


def crear_aviso(settings: Settings) -> PortAvisoDeIntegracion:
    """The notice that reaches an Administrator who is not looking at the screen.

    Process-lifetime, like `crear_enviador` in identity: it holds no transaction.
    """
    return AvisoPorEmail(crear_transporte(settings), settings.app_base_url)
