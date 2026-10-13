"""Where `billing` and `reference_data` are handed their access to WSFEv1.

The same shape as `padron.py`, above, and for the same reason: two contexts meet, and
neither one's `infrastructure/` may reach into the other's (R3). So the assembly happens
here, in the composition root, above both of them.

**This module is the piece the two previous units of epic 5 left open.** `parametros-fiscales`
and `puntos-de-venta` both shipped their ARCA client with an empty credentials map and a
note saying `emision-de-comprobantes` would build this once instead of twice. This is it.

The clients are built **per request** rather than cached per process, and the reason is
worth recording because the comment it replaces said the opposite: `ClienteSoap` opens a
fresh `httpx.AsyncClient` for every envelope it sends, so there is no connection pool to
preserve, and caching one would only serve to freeze a credentials resolver that has to be
bound to the current transaction.
"""

from __future__ import annotations

from uuid import UUID

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.billing.application.errors import ArcaNoDisponible
from cheatsheet.contexts.billing.application.ports import (
    PortAutorizacionDeArca,
    PortHabilitacionDeArca,
)
from cheatsheet.contexts.billing.infrastructure.habilitacion import (
    HabilitacionEnArca,
    HabilitacionSimulada,
)
from cheatsheet.contexts.billing.infrastructure.repositories import (
    RepositorioPuntoDeVentaPostgres,
)
from cheatsheet.contexts.billing.infrastructure.wsfe_emision import (
    AutorizacionEnArca,
    AutorizacionSimulada,
)
from cheatsheet.contexts.integrations.application.errors import (
    ProveedorNoDisponible,
    TicketNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import PortRepositorioIntegraciones
from cheatsheet.contexts.integrations.application.ticket import desempaquetar
from cheatsheet.contexts.integrations.application.tickets_de_plataforma import (
    ObtenerTicketDePlataforma,
)
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.contexts.reference_data.application.ports import PortCatalogosFiscales
from cheatsheet.contexts.reference_data.infrastructure.wsfe_catalogos import (
    CatalogosDeWsfe,
    CatalogosSimulados,
)
from cheatsheet.platform.settings import AdaptadorDeCatalogos, Settings
from cheatsheet.platform.wsfe import CredencialDeWsfe, PortCredencialesDeWsfe
from cheatsheet.shared.empresa import EmpresaId

#: The key under which the ARCA integration stores the company's CUIT, recorded when its
#: delegation was verified (ADR-0014). It goes in `<Auth><Cuit>`: on whose behalf the
#: platform certificate speaks.
CLAVE_CUIT = "cuit"


class CredencialesDesdeIntegraciones:
    """Resolves a WSFEv1 credential through `integrations`' Open Host Service.

    It lives in the composition root rather than in either consuming context because it
    *is* the wiring of two contexts, which is the one thing this layer exists for (R3,
    ADR-0003) -- the same reason `_consultar_padron` sits next door in `padron.py`.

    Everything that can go wrong becomes `ArcaNoDisponible`, and that flattening is
    deliberate: to a caller trying to invoice, «the certificate is not loaded», «the ticket
    expired» and «WSAA is down» are one actionable fact -- we cannot ask ARCA right now --
    and none of them says anything about the document being issued.
    """

    def __init__(
        self,
        *,
        tickets: ObtenerTicketDePlataforma,
        integraciones: PortRepositorioIntegraciones,
        puntos: RepositorioPuntoDeVentaPostgres,
    ) -> None:
        self._tickets = tickets
        self._integraciones = integraciones
        self._puntos = puntos

    async def para(self, empresa_id: EmpresaId) -> CredencialDeWsfe:
        configuracion = await self._integraciones.buscar(empresa_id, SistemaExterno.ARCA)
        if configuracion is None:
            # The ordinary case straight out of onboarding, not an anomaly: the company has
            # not verified its delegation yet.
            raise ArcaNoDisponible("La empresa no tiene conectada la integracion con ARCA")

        cuit = str(configuracion.parametros.get(CLAVE_CUIT, "")).strip()
        if not cuit:
            raise ArcaNoDisponible("La integracion con ARCA no tiene el CUIT de la empresa")

        try:
            ticket = await self._tickets.ejecutar(ServicioDeArca.WSFE)
            token, sign = desempaquetar(ticket.contenido)
        except (TicketNoDisponible, ProveedorNoDisponible) as exc:
            raise ArcaNoDisponible(f"No se pudo obtener el ticket de ARCA: {exc}") from exc

        return CredencialDeWsfe(token=token, sign=sign, cuit=cuit)

    async def numero_de_punto(self, empresa_id: EmpresaId, punto_id: UUID) -> int | None:
        del empresa_id  # RLS already scopes the repository to the company.
        punto = await self._puntos.buscar_por_id(punto_id)
        return punto.numero if punto is not None else None


def armar_credenciales(unidad: UnidadDeTrabajo, settings: Settings) -> PortCredencialesDeWsfe:
    """The platform's WSFEv1 token and sign, and the company's CUIT (ADR-0014).

    Obtaining a ticket may mint one, and a minted ticket is committed **apart from** this
    request: ARCA refuses a second ticket while the first is alive (ADR-0004), so losing it to
    this request's rollback — a rejected emission, say — would leave every company without
    WSFE for twelve hours. The ticket repository holds its own transaction for that reason.
    """
    piezas = Integraciones.armar(unidad.sesion, settings)
    return CredencialesDesdeIntegraciones(
        tickets=piezas.tickets_de_plataforma,
        integraciones=piezas.integraciones,
        puntos=RepositorioPuntoDeVentaPostgres(unidad.sesion),
    )


def _es_real(settings: Settings) -> bool:
    """One switch for all three WSFEv1 clients.

    They are the same service with the same credential, and having the catalogue real while
    issuance is simulated would be a configuration nobody meant to make -- documents
    validated against ARCA's own parameters and then authorised by a stand-in.
    """
    return settings.catalogos_fiscales_adaptador is AdaptadorDeCatalogos.WSFE


def armar_autorizacion(unidad: UnidadDeTrabajo, settings: Settings) -> PortAutorizacionDeArca:
    """`FECAESolicitar`, `FECompConsultar` and `FECompUltimoAutorizado` (HU-E5-03)."""
    if _es_real(settings):
        return AutorizacionEnArca(
            url=settings.arca_wsfe_url, credenciales=armar_credenciales(unidad, settings)
        )
    return AutorizacionSimulada(settings.entorno)


def armar_habilitacion(unidad: UnidadDeTrabajo, settings: Settings) -> PortHabilitacionDeArca:
    """`FEParamGetPtosVenta` (HU-E5-05 RN-03). **Real only against production ARCA.**

    Homologación keeps no registry of points of sale: asked on 2026-10-10 for a company it
    then gave a CAE on point 1, it answered `602 Sin Resultados`. Asking it would block
    every alta in `staging` for a reason production does not have, so outside production
    the stand-in's points stand in for the list ARCA does not keep.
    """
    if _es_real(settings) and settings.es_produccion:
        return HabilitacionEnArca(
            url=settings.arca_wsfe_url, credenciales=armar_credenciales(unidad, settings)
        )
    return HabilitacionSimulada(settings.entorno)


def armar_catalogos(unidad: UnidadDeTrabajo, settings: Settings) -> PortCatalogosFiscales:
    """The `FEParamGet*` catalogue client (HS-T4)."""
    if _es_real(settings):
        return CatalogosDeWsfe(
            url=settings.arca_wsfe_url, credenciales=armar_credenciales(unidad, settings)
        )
    return CatalogosSimulados(settings.entorno)


__all__ = [
    "armar_autorizacion",
    "armar_catalogos",
    "armar_credenciales",
    "armar_habilitacion",
]
