"""The SOAP half of the ARCA adapter: one operation, `LoginCms`.

Written against the wire format rather than generated from the WSDL. `LoginCms` takes one
base64 string and returns one XML document, so a SOAP toolkit would add a dependency and a
code-generation step to save building an envelope with two `format` calls — and it would
still need the hand-written part, which is reading a `loginTicketResponse` out of an
escaped string.

**Two hosts, and here that matters more than anywhere else.** Unlike Meta, ARCA separates
homologación from producción at the DNS level. The environment comes from `APP_ENV` (the
decision `mecanismo-de-integraciones` recorded), so it decides which ARCA a company talks
to — the difference between practising and issuing an irreversible tax document.

The transport, the retries and the safe parsing live in `soap.py`, shared with the padrón
client. What stays here is what only WSAA knows: its envelope, and the fact that its
answer nests a second XML document inside a string.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime

import httpx

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import interpretar_falla
from cheatsheet.contexts.integrations.infrastructure.arca.soap import (
    ClienteSoap,
    ConfiguracionSoap,
    FallaRecibida,
    leer_falla,
    raiz,
)

URL_HOMOLOGACION = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
URL_PRODUCCION = "https://wsaa.afip.gov.ar/ws/services/LoginCms"

#: WSAA needs nothing the shared transport does not already offer.
ConfiguracionWsaa = ConfiguracionSoap

_SOBRE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">'
    "<soapenv:Header/><soapenv:Body><wsaa:loginCms>"
    "<wsaa:in0>{cms}</wsaa:in0>"
    "</wsaa:loginCms></soapenv:Body></soapenv:Envelope>"
)

#: How the token and the sign travel once they leave this module: one blob, two lines.
#: Defined here, next to the code that produces them, and read back by `empaquetar`'s
#: counterpart — a format agreed by two modules in one place instead of two.
_SEPARADOR = "\n"


@dataclass(frozen=True, slots=True)
class TicketDeArca:
    """What `loginTicketResponse` carries: the two values every later call needs."""

    token: str
    sign: str
    expira_en: datetime


def empaquetar(ticket: TicketDeArca) -> bytes:
    """The token and the sign together, because every later call needs both.

    A pair split across two columns is a pair that eventually disagrees.
    """
    return f"{ticket.token}{_SEPARADOR}{ticket.sign}".encode()


def desempaquetar(contenido: bytes) -> tuple[str, str]:
    """Read back what `empaquetar` wrote. Raises when the stored blob is not a pair."""
    partes = contenido.decode("utf-8", errors="replace").split(_SEPARADOR)
    if len(partes) != 2 or not partes[0] or not partes[1]:
        raise ProveedorNoDisponible("El ticket de acceso guardado no tiene token y firma")
    return partes[0], partes[1]


class ClienteWsaa:
    """Talks to WSAA. Raises this context's errors, never httpx's."""

    def __init__(
        self, config: ConfiguracionSoap, transporte: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._soap = ClienteSoap(config, transporte)

    async def login(self, cms: bytes) -> TicketDeArca:
        """Exchange a signed request for an access ticket."""
        cuerpo = _SOBRE.format(cms=base64.b64encode(cms).decode())
        try:
            respuesta = await self._soap.enviar(cuerpo)
        except FallaRecibida as recibida:
            raise interpretar_falla(recibida.falla) from recibida
        return _leer_ticket(respuesta)


def _leer_ticket(texto: str) -> TicketDeArca:
    """Read the response, which nests an escaped XML document inside the SOAP body.

    That double encoding is ARCA's, not ours: `loginCmsReturn` is a *string* that happens
    to contain a `loginTicketResponse`.
    """
    documento = raiz(texto)
    interior = documento.findtext(".//loginCmsReturn") or documento.findtext(".//{*}loginCmsReturn")
    if not interior:
        falla = leer_falla(texto)
        if falla is not None:
            raise interpretar_falla(falla)
        raise ProveedorNoDisponible("ARCA respondio sin ticket y sin error")

    ticket = raiz(interior)
    token = ticket.findtext(".//token")
    sign = ticket.findtext(".//sign")
    expira = ticket.findtext(".//expirationTime")
    if not token or not sign or not expira:
        raise ProveedorNoDisponible("El ticket de ARCA llego incompleto")
    try:
        expira_en = datetime.fromisoformat(expira)
    except ValueError as exc:
        raise ProveedorNoDisponible(f"ARCA informo un vencimiento ilegible: {expira}") from exc
    return TicketDeArca(token=token.strip(), sign=sign.strip(), expira_en=expira_en)
