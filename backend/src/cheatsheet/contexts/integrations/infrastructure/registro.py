"""Which adapter answers for which external system.

This is the seam of the epic. `conexion-whatsapp` was the first unit to use it and
`conexion-arca` the second: only `MERCADOPAGO` still resolves to the generic stand-in.

ARCA is the first system that needs a **third** adapter — an issuer of access tickets
(ADR-0004) — so `ParDeAdaptadores` grew an optional slot rather than the registry growing
a special case. Every other system leaves it empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from cheatsheet.contexts.integrations.application.ports import (
    PortConectorDeIntegracion,
    PortEmisorDeTickets,
    PortVerificadorDeConexion,
)
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.arca.adaptadores import (
    ConectorArca,
    EmisorArcaDeTickets,
    VerificadorArca,
)
from cheatsheet.contexts.integrations.infrastructure.arca.simulado import ArcaSimulado
from cheatsheet.contexts.integrations.infrastructure.arca.wsaa import ClienteWsaa, ConfiguracionWsaa
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
from cheatsheet.platform.settings import (
    AdaptadorDeArca,
    AdaptadorDeWhatsApp,
    Entorno,
    Settings,
)
from cheatsheet.shared.clock import Reloj, RelojDelSistema

#: The systems this epic can connect. `GOOGLE_SHEETS` and `EXCEL_ONLINE` are on the screen
#: and in the DER enum, but their connection is HU-E2-04, which the roadmap put in epic 4.
#: Asking to connect one answers `SistemaNoConfigurable` instead of failing obscurely.
SISTEMAS_DEL_EPICO: tuple[SistemaExterno, ...] = (
    SistemaExterno.ARCA,
    SistemaExterno.MERCADOPAGO,
    SistemaExterno.WHATSAPP,
)

#: Still answered by the generic stand-in, until its own unit lands.
SISTEMAS_SIMULADOS: tuple[SistemaExterno, ...] = (SistemaExterno.MERCADOPAGO,)

#: Used by the registry built without `Settings` (tests, and the fully simulated path).
AVISO_POR_DEFECTO = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class ParDeAdaptadores:
    conector: PortConectorDeIntegracion
    verificador: PortVerificadorDeConexion
    #: Only ARCA mints access tickets (ADR-0004). Optional rather than a separate registry
    #: because it is resolved by the same key and replaced by the same unit.
    emisor: PortEmisorDeTickets | None = None


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
        pares[SistemaExterno.ARCA] = _par_de_arca(settings, RelojDelSistema())
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
        simulado_arca = ArcaSimulado(
            entorno=entorno, reloj=RelojDelSistema(), aviso=AVISO_POR_DEFECTO
        )
        pares[SistemaExterno.ARCA] = ParDeAdaptadores(
            conector=simulado_arca, verificador=simulado_arca, emisor=simulado_arca
        )
        return cls(pares)

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None:
        par = self._pares.get(sistema)
        return par.conector if par is not None else None

    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None:
        par = self._pares.get(sistema)
        return par.verificador if par is not None else None

    def emisor_de_tickets(self, sistema: SistemaExterno) -> PortEmisorDeTickets | None:
        par = self._pares.get(sistema)
        return par.emisor if par is not None else None


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


def _par_de_arca(settings: Settings, reloj: Reloj) -> ParDeAdaptadores:
    aviso = timedelta(days=settings.arca_aviso_vencimiento_dias)
    if settings.arca_adaptador is AdaptadorDeArca.SIMULADO:
        simulado = ArcaSimulado(entorno=settings.entorno, reloj=reloj, aviso=aviso)
        return ParDeAdaptadores(conector=simulado, verificador=simulado, emisor=simulado)

    # **Two hosts, and this is where the choice is made.** `Ambiente` comes from `APP_ENV`
    # and never from the request (the decision `mecanismo-de-integraciones` recorded), so
    # this line is the difference between practising and issuing an irreversible document.
    url = (
        settings.arca_wsaa_url_produccion
        if settings.es_produccion
        else settings.arca_wsaa_url_homologacion
    )
    cliente = ClienteWsaa(
        ConfiguracionWsaa(url=url, timeout_segundos=float(settings.arca_timeout_segundos))
    )
    emisor = EmisorArcaDeTickets(cliente, reloj)
    return ParDeAdaptadores(
        conector=ConectorArca(emisor, reloj),
        verificador=VerificadorArca(reloj, aviso),
        emisor=emisor,
    )
