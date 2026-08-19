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
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree

import httpx
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError as ParseErrorSeguro
from defusedxml.ElementTree import fromstring as parsear_xml

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import (
    FallaDeArca,
    interpretar_falla,
)
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

URL_HOMOLOGACION = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
URL_PRODUCCION = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
#: Longer than Meta's. ARCA is slower, and a login that times out at 10 s on a busy
#: morning looks to the Administrator exactly like a rejected certificate.
TIMEOUT_POR_DEFECTO = 15.0
MAX_INTENTOS = 3
ESPERA_BASE = 1.0

_ESPACIOS = {"soap": "http://schemas.xmlsoap.org/soap/envelope/"}

_SOBRE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">'
    "<soapenv:Header/><soapenv:Body><wsaa:loginCms>"
    "<wsaa:in0>{cms}</wsaa:in0>"
    "</wsaa:loginCms></soapenv:Body></soapenv:Envelope>"
)


@dataclass(frozen=True, slots=True)
class ConfiguracionWsaa:
    url: str = URL_HOMOLOGACION
    timeout_segundos: float = TIMEOUT_POR_DEFECTO
    max_intentos: int = MAX_INTENTOS
    espera_base: float = ESPERA_BASE


@dataclass(frozen=True, slots=True)
class TicketDeArca:
    """What `loginTicketResponse` carries: the two values every later call needs."""

    token: str
    sign: str
    expira_en: datetime


class ClienteWsaa:
    """Talks to WSAA. Raises this context's errors, never httpx's."""

    def __init__(
        self, config: ConfiguracionWsaa, transporte: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._transporte = transporte

    async def login(self, cms: bytes) -> TicketDeArca:
        """Exchange a signed request for an access ticket."""
        cuerpo = _SOBRE.format(cms=base64.b64encode(cms).decode())
        respuesta = await self._enviar(cuerpo)
        return _leer_ticket(respuesta)

    async def _enviar(self, cuerpo: str) -> str:
        cabeceras = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}
        ultimo: Exception | None = None

        for intento in range(1, self._config.max_intentos + 1):
            try:
                async with self._cliente() as cliente:
                    respuesta = await cliente.post(
                        self._config.url, content=cuerpo.encode("utf-8"), headers=cabeceras
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                ultimo = exc
                # Nothing about the credential is logged: not the CMS, not the subject.
                logger.warning("wsaa_reintento", intento=intento, motivo=str(exc))
                await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))
                continue

            if respuesta.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                falla = _leer_falla(respuesta.text)
                if falla is not None:
                    # A SOAP fault arrives with HTTP 500. It is an answer, not an outage.
                    raise interpretar_falla(falla)
                ultimo = ProveedorNoDisponible(f"ARCA respondio {respuesta.status_code}")
                logger.warning("wsaa_reintento", intento=intento, estado=respuesta.status_code)
                await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))
                continue
            if respuesta.status_code >= httpx.codes.BAD_REQUEST:
                raise ProveedorNoDisponible(f"ARCA respondio {respuesta.status_code}")
            return respuesta.text

        raise ProveedorNoDisponible(
            f"ARCA no respondio tras {self._config.max_intentos} intentos: {ultimo}"
        )

    def _cliente(self) -> httpx.AsyncClient:
        if self._transporte is not None:
            return httpx.AsyncClient(
                timeout=self._config.timeout_segundos, transport=self._transporte
            )
        return httpx.AsyncClient(timeout=self._config.timeout_segundos)


def _raiz(texto: str) -> ElementTree.Element:
    """Parsed with `defusedxml`, and the reason is measurable rather than ceremonial.

    `xml.etree` on 3.11 expands internal entities — verified before adding the dependency:
    a 300-byte document expanded to 3 000 characters, ten times per nesting level. A
    response from an external service is untrusted input by definition, and this parses
    one. `defusedxml` refuses the document instead — raising `DefusedXmlException`, which
    is **not** a `ParseError` and therefore needs its own clause. A test caught that:
    without the first branch below, the refusal escaped untranslated and would have taken
    down a Beat task with an exception nobody catches.

    Building XML with `ElementTree` (see `firma.py`) is unaffected: writing is not parsing.
    """
    try:
        return parsear_xml(texto)
    except DefusedXmlException as exc:
        raise ProveedorNoDisponible("ARCA respondio un XML que no es seguro procesar") from exc
    except ParseErrorSeguro as exc:
        raise ProveedorNoDisponible("ARCA respondio algo que no es XML") from exc


def _leer_falla(texto: str) -> FallaDeArca | None:
    """Pull `faultcode` and `faultstring` out of a SOAP fault, if that is what this is."""
    try:
        raiz = parsear_xml(texto)
    except (DefusedXmlException, ParseErrorSeguro):
        return None
    falla = raiz.find(".//soap:Fault", _ESPACIOS)
    if falla is None:
        falla = raiz.find(".//Fault")
    if falla is None:
        return None
    codigo = falla.findtext("faultcode") or falla.findtext("{*}faultcode") or ""
    detalle = falla.findtext("faultstring") or falla.findtext("{*}faultstring") or ""
    return FallaDeArca(codigo=codigo.strip(), detalle=detalle.strip())


def _leer_ticket(texto: str) -> TicketDeArca:
    """Read the response, which nests an escaped XML document inside the SOAP body.

    That double encoding is ARCA's, not ours: `loginCmsReturn` is a *string* that happens
    to contain a `loginTicketResponse`.
    """
    raiz = _raiz(texto)
    interior = raiz.findtext(".//loginCmsReturn") or raiz.findtext(".//{*}loginCmsReturn")
    if not interior:
        falla = _leer_falla(texto)
        if falla is not None:
            raise interpretar_falla(falla)
        raise ProveedorNoDisponible("ARCA respondio sin ticket y sin error")

    ticket = _raiz(interior)
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
