"""Which adapter answers for which external system.

This is the seam of the epic. `conexion-arca` replaces one entry here with the real WSAA
pair, `conexion-mercadopago` another, `conexion-whatsapp` the third — and nothing else in
`integrations` changes, because everything else depends on the ports rather than on the
providers.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.contexts.integrations.application.ports import (
    PortConectorDeIntegracion,
    PortVerificadorDeConexion,
)
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.simulados import (
    ConectorSimulado,
    VerificadorSimulado,
)
from cheatsheet.platform.settings import Entorno

#: The systems this epic can connect. `GOOGLE_SHEETS` and `EXCEL_ONLINE` are on the screen
#: and in the DER enum, but their connection is HU-E2-04, which the roadmap put in epic 4.
#: Asking to connect one answers `SistemaNoConfigurable` instead of failing obscurely.
SISTEMAS_DEL_EPICO: tuple[SistemaExterno, ...] = (
    SistemaExterno.ARCA,
    SistemaExterno.MERCADOPAGO,
    SistemaExterno.WHATSAPP,
)


@dataclass(frozen=True, slots=True)
class ParDeAdaptadores:
    conector: PortConectorDeIntegracion
    verificador: PortVerificadorDeConexion


class RegistroDeAdaptadores:
    """Implements `PortRegistroDeAdaptadores`."""

    def __init__(self, pares: dict[SistemaExterno, ParDeAdaptadores]) -> None:
        self._pares = pares

    @classmethod
    def simulado(cls, entorno: Entorno) -> RegistroDeAdaptadores:
        """Every system answered by a stand-in. Refuses to build in production."""
        return cls(
            {
                sistema: ParDeAdaptadores(
                    conector=ConectorSimulado(sistema=sistema, entorno=entorno),
                    verificador=VerificadorSimulado(sistema=sistema, entorno=entorno),
                )
                for sistema in SISTEMAS_DEL_EPICO
            }
        )

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None:
        par = self._pares.get(sistema)
        return par.conector if par is not None else None

    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None:
        par = self._pares.get(sistema)
        return par.verificador if par is not None else None
