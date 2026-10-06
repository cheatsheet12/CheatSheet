"""Which adapter answers for which external system.

This is the seam of the epic, and with `conexion-mercadopago` it is fully occupied: every
system this epic connects has an adapter of its own, and the generic stand-in that used to
answer for the ones without a unit is gone.

**No system implements every port, and none is expected to.** ARCA mints access tickets
(ADR-0004) and looks a CUIT up in the taxpayer registry; MercadoPago is connected over an
OAuth2 round trip and renews its own credential; WhatsApp does neither. `ParDeAdaptadores`
grew optional slots rather than the registry growing a special case per provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from cheatsheet.contexts.integrations.application.ports import (
    PortAutorizacionOAuth,
    PortConectorDeIntegracion,
    PortConsultaDePadron,
    PortEmisorDeTickets,
    PortRenovacionDeCredencial,
    PortVerificadorDeConexion,
)
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.arca.adaptadores import (
    ConectorArca,
    EmisorArcaDeTickets,
    VerificadorArca,
)
from cheatsheet.contexts.integrations.infrastructure.arca.padron import (
    ClientePadronA5,
    ConfiguracionPadron,
)
from cheatsheet.contexts.integrations.infrastructure.arca.simulado import ArcaSimulado
from cheatsheet.contexts.integrations.infrastructure.arca.wsaa import ClienteWsaa, ConfiguracionWsaa
from cheatsheet.contexts.integrations.infrastructure.mercadopago.autorizacion import (
    AutorizacionMercadoPago,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.cliente import (
    ClienteMercadoPago,
    ConfiguracionMercadoPago,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.conector import (
    ConectorMercadoPago,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.simulado import (
    MercadoPagoSimulado,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.verificador import (
    VerificadorMercadoPago,
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
    AdaptadorDeMercadoPago,
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

#: Used by the registry built without `Settings` (tests, and the fully simulated path).
AVISO_POR_DEFECTO = timedelta(days=30)

#: Where the simulated OAuth redirect lands when there is no `Settings` to read it from.
RETORNO_POR_DEFECTO = "http://localhost:3000/configuracion/integraciones"


@dataclass(frozen=True, slots=True)
class ParDeAdaptadores:
    conector: PortConectorDeIntegracion
    verificador: PortVerificadorDeConexion
    #: Only ARCA mints access tickets (ADR-0004). Optional rather than a separate registry
    #: because it is resolved by the same key and replaced by the same unit.
    emisor: PortEmisorDeTickets | None = None
    #: Only ARCA has a taxpayer registry to look a CUIT up in.
    padron: PortConsultaDePadron | None = None
    #: Only MercadoPago is connected through an OAuth2 round trip.
    autorizacion: PortAutorizacionOAuth | None = None
    #: Only MercadoPago hands back something that can be traded for a fresh credential.
    #: ARCA's certificate is renewed by the company at ARCA's own site.
    renovador: PortRenovacionDeCredencial | None = None


class RegistroDeAdaptadores:
    """Implements `PortRegistroDeAdaptadores`."""

    def __init__(self, pares: dict[SistemaExterno, ParDeAdaptadores]) -> None:
        self._pares = pares

    @classmethod
    def desde_settings(cls, settings: Settings) -> RegistroDeAdaptadores:
        """The registry the running application uses.

        Each of the three systems is either real or its own stand-in, according to its
        `*_ADAPTADOR` variable. Every stand-in refuses to be built in production, so none
        of this can quietly become how a real company connects.
        """
        reloj = RelojDelSistema()
        return cls(
            {
                SistemaExterno.WHATSAPP: _par_de_whatsapp(settings),
                SistemaExterno.ARCA: _par_de_arca(settings, reloj),
                SistemaExterno.MERCADOPAGO: _par_de_mercadopago(settings, reloj),
            }
        )

    @classmethod
    def simulado(cls, entorno: Entorno) -> RegistroDeAdaptadores:
        """Every system answered by a stand-in. For tests that do not care which."""
        reloj = RelojDelSistema()
        simulado_whatsapp = WhatsAppSimulado(entorno)
        simulado_arca = ArcaSimulado(entorno=entorno, reloj=reloj, aviso=AVISO_POR_DEFECTO)
        simulado_mp = MercadoPagoSimulado(
            entorno=entorno, reloj=reloj, redirect_uri=RETORNO_POR_DEFECTO
        )
        return cls(
            {
                SistemaExterno.WHATSAPP: ParDeAdaptadores(
                    conector=simulado_whatsapp, verificador=simulado_whatsapp
                ),
                SistemaExterno.ARCA: ParDeAdaptadores(
                    conector=simulado_arca,
                    verificador=simulado_arca,
                    emisor=simulado_arca,
                    padron=simulado_arca,
                ),
                SistemaExterno.MERCADOPAGO: ParDeAdaptadores(
                    conector=simulado_mp,
                    verificador=simulado_mp,
                    autorizacion=simulado_mp,
                    renovador=simulado_mp,
                ),
            }
        )

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None:
        par = self._pares.get(sistema)
        return par.conector if par is not None else None

    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None:
        par = self._pares.get(sistema)
        return par.verificador if par is not None else None

    def emisor_de_tickets(self, sistema: SistemaExterno) -> PortEmisorDeTickets | None:
        par = self._pares.get(sistema)
        return par.emisor if par is not None else None

    def consulta_de_padron(self, sistema: SistemaExterno) -> PortConsultaDePadron | None:
        par = self._pares.get(sistema)
        return par.padron if par is not None else None

    def autorizacion(self, sistema: SistemaExterno) -> PortAutorizacionOAuth | None:
        par = self._pares.get(sistema)
        return par.autorizacion if par is not None else None

    def renovador(self, sistema: SistemaExterno) -> PortRenovacionDeCredencial | None:
        par = self._pares.get(sistema)
        return par.renovador if par is not None else None


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
        return ParDeAdaptadores(
            conector=simulado, verificador=simulado, emisor=simulado, padron=simulado
        )

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
    # The padrón lives on a different host from WSAA and splits its environments the same
    # way, so the choice is made once, here, from the same flag.
    url_padron = (
        settings.arca_padron_url_produccion
        if settings.es_produccion
        else settings.arca_padron_url_homologacion
    )
    return ParDeAdaptadores(
        conector=ConectorArca(emisor, reloj),
        verificador=VerificadorArca(reloj, aviso),
        emisor=emisor,
        padron=ClientePadronA5(
            ConfiguracionPadron(
                url=url_padron, timeout_segundos=float(settings.arca_timeout_segundos)
            )
        ),
    )


def _par_de_mercadopago(settings: Settings, reloj: Reloj) -> ParDeAdaptadores:
    """Four ports for one provider: authorize, connect, verify and renew.

    **One host for every environment**, unlike ARCA. MercadoPago publishes no sandbox
    address: what separates a test account from a real one is `live_mode`, which the
    adapter cross-checks against `es_produccion` — see `mercadopago/mapeo.py`.
    """
    if settings.mercadopago_adaptador is AdaptadorDeMercadoPago.SIMULADO:
        simulado = MercadoPagoSimulado(
            entorno=settings.entorno,
            reloj=reloj,
            redirect_uri=settings.mercadopago_redirect_uri,
        )
        return ParDeAdaptadores(
            conector=simulado, verificador=simulado, autorizacion=simulado, renovador=simulado
        )

    config = ConfiguracionMercadoPago(
        client_id=settings.mercadopago_client_id,
        client_secret=settings.mercadopago_client_secret,
        redirect_uri=settings.mercadopago_redirect_uri,
        credenciales_de_prueba=not settings.es_produccion,
        auth_url=settings.mercadopago_auth_url,
        api_url=settings.mercadopago_api_url,
        timeout_segundos=float(settings.mercadopago_timeout_segundos),
    )
    cliente = ClienteMercadoPago(config)
    conector = ConectorMercadoPago(cliente, reloj, es_produccion=settings.es_produccion)
    return ParDeAdaptadores(
        conector=conector,
        verificador=VerificadorMercadoPago(cliente, es_produccion=settings.es_produccion),
        autorizacion=AutorizacionMercadoPago(config),
        renovador=conector,
    )
