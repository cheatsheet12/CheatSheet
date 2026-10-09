"""Las plantillas aprobadas, vistas desde quien manda el mensaje (U6, ADR-0011).

`payments` y `scheduling` no importan `business_config` (R3): cada uno declara un `Protocol` local,
`PlantillasAprobadas`, y esta raíz de composición lo respalda con `ConsultarPlantillaParaEnviar`,
el caso de uso que `business_config` publica. Es la misma pieza para los dos: la plantilla
aprobada de un código, o `None` — y entonces el adaptador manda su texto de fábrica.
"""

from __future__ import annotations

from collections.abc import Mapping

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.business_config.application.plantillas import (
    ConsultarPlantillaParaEnviar,
    PlantillaParaEnviar,
)
from cheatsheet.contexts.business_config.infrastructure.ensamblado import ConfiguracionDeNegocio


class PlantillasViaConfiguracion:
    """`PlantillasAprobadas` de `payments` y de `scheduling`, sobre `business_config`."""

    def __init__(self, caso: ConsultarPlantillaParaEnviar) -> None:
        self._caso = caso

    async def para(self, codigo: str, variables: Mapping[str, str]) -> PlantillaParaEnviar | None:
        return await self._caso.ejecutar(codigo, dict(variables))


def armar_plantillas_aprobadas(unidad: UnidadDeTrabajo) -> PlantillasViaConfiguracion:
    """Las plantillas aprobadas de la empresa de esta unidad de trabajo."""
    piezas = ConfiguracionDeNegocio.armar(unidad)
    return PlantillasViaConfiguracion(ConsultarPlantillaParaEnviar(piezas.plantillas))


__all__ = ["PlantillasViaConfiguracion", "armar_plantillas_aprobadas"]
