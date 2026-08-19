"""Which adapter answers for which external system.

This is the seam of the epic, and `conexion-whatsapp` is the first unit to use it:
`WHATSAPP` no longer resolves to the generic stand-in, it resolves to a real Graph API
pair or to WhatsApp's own simulator, decided by configuration. **Nothing else in
`integrations` changed to make that true** — which is what the seam was for.

`conexion-arca` and `conexion-mercadopago` each replace one more entry, the same way.
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
from cheatsheet.contexts.integrations.infrastructure.whatsapp.cliente import (
    ClienteGraph,
    ConfiguracionWhatsApp,
)
from cheatsheet.contexts.integrations.infrastructure.whatsapp.conector import ConectorWhatsApp
from cheatsheet.contexts.integrations.infrastructure.whatsapp.simulado import WhatsAppSimulado
from cheatsheet.contexts.integrations.infrastructure.whatsapp.verificador import (
    VerificadorWhatsApp,
)
from cheatsheet.platform.settings import AdaptadorDeWhatsApp, Entorno, Settings

#: The systems this epic can connect. `GOOGLE_SHEETS` and `EXCEL_ONLINE` are on the screen
#: and in the DER enum, but their connection is HU-E2-04, which the roadmap put in epic 4.
#: Asking to connect one answers `SistemaNoConfigurable` instead of failing obscurely.
SISTEMAS_DEL_EPICO: tuple[SistemaExterno, ...] = (
    SistemaExterno.ARCA,
    SistemaExterno.MERCADOPAGO,
    SistemaExterno.WHATSAPP,
)

#: Still answered by the generic stand-in, until their own units land.
SISTEMAS_SIMULADOS: tuple[SistemaExterno, ...] = (
    SistemaExterno.ARCA,
    SistemaExterno.MERCADOPAGO,
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
    def desde_settings(cls, settings: Settings) -> RegistroDeAdaptadores:
        """The registry the running application uses.

        ARCA and MercadoPago are stand-ins until their units land; WhatsApp is real or
        simulated according to `WHATSAPP_ADAPTADOR`. Every stand-in refuses to be built in
        production, so none of this can quietly become how a real company connects.
        """
        pares = {
            sistema: ParDeAdaptadores(
                conector=ConectorSimulado(sistema=sistema, entorno=settings.entorno),
                verificador=VerificadorSimulado(sistema=sistema, entorno=settings.entorno),
            )
            for sistema in SISTEMAS_SIMULADOS
        }
        pares[SistemaExterno.WHATSAPP] = _par_de_whatsapp(settings)
        return cls(pares)

    @classmethod
    def simulado(cls, entorno: Entorno) -> RegistroDeAdaptadores:
        """Every system answered by a stand-in. For tests that do not care which."""
        simulado_whatsapp = WhatsAppSimulado(entorno)
        pares = {
            sistema: ParDeAdaptadores(
                conector=ConectorSimulado(sistema=sistema, entorno=entorno),
                verificador=VerificadorSimulado(sistema=sistema, entorno=entorno),
            )
            for sistema in SISTEMAS_SIMULADOS
        }
        pares[SistemaExterno.WHATSAPP] = ParDeAdaptadores(
            conector=simulado_whatsapp, verificador=simulado_whatsapp
        )
        return cls(pares)

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None:
        par = self._pares.get(sistema)
        return par.conector if par is not None else None

    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None:
        par = self._pares.get(sistema)
        return par.verificador if par is not None else None


def _par_de_whatsapp(settings: Settings) -> ParDeAdaptadores:
    if settings.whatsapp_adaptador is AdaptadorDeWhatsApp.SIMULADO:
        # Raises in production; `Settings` has already refused the combination anyway.
        simulado = WhatsAppSimulado(settings.entorno)
        return ParDeAdaptadores(conector=simulado, verificador=simulado)
    cliente = ClienteGraph(
        ConfiguracionWhatsApp(
            url_base=settings.whatsapp_graph_url,
            version=settings.whatsapp_graph_version,
            timeout_segundos=float(settings.whatsapp_timeout_segundos),
        )
    )
    return ParDeAdaptadores(
        conector=ConectorWhatsApp(cliente), verificador=VerificadorWhatsApp(cliente)
    )
