"""Cableado de `business_config` sobre una unidad de trabajo.

Solo el repositorio: este contexto no habla con nadie de afuera.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.business_config.application.ports import PortRepositorioReglas
from cheatsheet.contexts.business_config.infrastructure.repositories import (
    RepositorioReglasPostgres,
)


@dataclass(frozen=True, slots=True)
class ConfiguracionDeNegocio:
    """Las piezas que necesita un request, atadas a una transaccion."""

    reglas: PortRepositorioReglas

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> ConfiguracionDeNegocio:
        return cls(reglas=RepositorioReglasPostgres(unidad.sesion))
