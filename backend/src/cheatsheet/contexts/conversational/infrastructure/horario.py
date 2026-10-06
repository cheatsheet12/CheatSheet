"""ACL sobre `business_config`: el horario de atención, en el vocabulario de `conversational`.

La misma forma que `payments/infrastructure/cadena.py` y que ADR-0003 pide: el contexto que
publica ofrece un contrato (`ConsultarAtencion`) y no conoce a sus consumidores; cada consumidor
lo traduce a sus términos. Acá se importa **sólo `application/`** del otro contexto (R3), y la
política se traduce al enum propio (`PoliticaFueraDeHorario`) en vez de compartirlo.

**Una configuración ilegible no voltea el webhook** (T11). Si la regla guardada no se puede leer
(un JSON escrito a mano), se trata como «sin horario» y se registra: un 500 haría que Meta
reintente y el cliente no reciba nada. Es el criterio de `dialogo_ilegible`.
"""

from __future__ import annotations

from datetime import datetime

from cheatsheet.contexts.business_config.application.atencion import ConsultarAtencion
from cheatsheet.contexts.conversational.domain.fuera_de_horario import (
    AtencionDelNegocio,
    PoliticaFueraDeHorario,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

logger = obtener_logger(__name__)

_SIN_HORARIO = AtencionDelNegocio(
    abierto=True,
    politica=PoliticaFueraDeHorario.AGENTE_RESPONDE,
    proxima_apertura=None,
    cerrado_desde=None,
)


class HorarioViaConfiguracion:
    """`PortHorarioDeAtencion`, respaldado por el servicio de aplicación del otro contexto."""

    def __init__(self, consulta: ConsultarAtencion, *, empresa_id: EmpresaId) -> None:
        self._consulta = consulta
        self._empresa_id = empresa_id

    async def consultar(self, ahora: datetime) -> AtencionDelNegocio:
        try:
            estado = await self._consulta.ejecutar(empresa_id=self._empresa_id, ahora=ahora)
        except EntradaInvalida:
            logger.warning("horario_ilegible", empresa=str(self._empresa_id))
            return _SIN_HORARIO
        return AtencionDelNegocio(
            abierto=estado.abierto,
            politica=PoliticaFueraDeHorario(estado.politica.value),
            proxima_apertura=estado.proxima_apertura,
            cerrado_desde=estado.cerrado_desde,
        )


__all__ = ["HorarioViaConfiguracion"]
