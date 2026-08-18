"""Where the ports of this context meet their adapters.

Same shape as `identity`'s `ensamblado.py`: one place that knows which concrete class
satisfies each port, so the routers stay free of that knowledge and a test can swap any
piece without touching the use cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.integrations.application.ports import (
    PortCifradoDeCredenciales,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
)
from cheatsheet.contexts.integrations.infrastructure.cifrado import CifradoAesGcm
from cheatsheet.contexts.integrations.infrastructure.registro import RegistroDeAdaptadores
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    RepositorioIntegracionesSQL,
)
from cheatsheet.platform.settings import Settings


@dataclass(frozen=True, slots=True)
class Integraciones:
    """The pieces one request needs."""

    integraciones: PortRepositorioIntegraciones
    cifrado: PortCifradoDeCredenciales
    adaptadores: PortRegistroDeAdaptadores

    @classmethod
    def armar(cls, sesion: AsyncSession, settings: Settings) -> Integraciones:
        return cls(
            integraciones=RepositorioIntegracionesSQL(sesion),
            cifrado=CifradoAesGcm(settings.secrets_encryption_key),
            adaptadores=registro_de_adaptadores(settings),
        )


def registro_de_adaptadores(settings: Settings) -> PortRegistroDeAdaptadores:
    """Every system answered by a stand-in, for now.

    `RegistroDeAdaptadores.simulado` raises in production, so this cannot quietly become
    how a real company connects. When `conexion-arca` lands it replaces one entry here
    with the real WSAA pair and this function stops being a one-liner — which is exactly
    the seam the unit was cut along.
    """
    return RegistroDeAdaptadores.simulado(settings.entorno)
