"""`HorarioFijo` — el doble de `PortHorarioDeAtencion` (aparte, fuera de los `dobles_*.py`).

**No calcula nada del horario**: eso es de `business_config` y se prueba allá. Se le dicen los
**períodos de cierre** como pares `(cerrado_desde, proxima_apertura)` y responde «cerrado» dentro de
cualquiera de ellos y «abierto» fuera. Es lo que permite escribir, en el vocabulario de este
contexto, una noche, el hueco de un horario cortado o un fin de semana largo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from cheatsheet.contexts.conversational.domain.fuera_de_horario import (
    AtencionDelNegocio,
    PoliticaFueraDeHorario,
)


@dataclass(frozen=True, slots=True)
class Cierre:
    """Un período de cierre: `[cerrado_desde, proxima_apertura)`. Sin apertura: no hay regreso."""

    cerrado_desde: datetime
    proxima_apertura: datetime | None


class HorarioFijo:
    def __init__(
        self,
        politica: PoliticaFueraDeHorario = PoliticaFueraDeHorario.AGENTE_RESPONDE,
        cierres: Sequence[Cierre] = (),
    ) -> None:
        self.politica = politica
        self.cierres = list(cierres)
        #: Cuántas veces se preguntó, y para qué instante: el agente consulta una vez por mensaje.
        self.consultas: list[datetime] = []

    async def consultar(self, ahora: datetime) -> AtencionDelNegocio:
        self.consultas.append(ahora)
        for cierre in self.cierres:
            termina = cierre.proxima_apertura
            if cierre.cerrado_desde <= ahora and (termina is None or ahora < termina):
                return AtencionDelNegocio(
                    abierto=False,
                    politica=self.politica,
                    proxima_apertura=cierre.proxima_apertura,
                    cerrado_desde=cierre.cerrado_desde,
                )
        return AtencionDelNegocio(
            abierto=True, politica=self.politica, proxima_apertura=None, cerrado_desde=None
        )


#: Siempre abierto: lo que pasa sin horario configurado. Es el valor por defecto de la escena.
def siempre_abierto() -> HorarioFijo:
    return HorarioFijo()


__all__ = ["Cierre", "HorarioFijo", "siempre_abierto"]
