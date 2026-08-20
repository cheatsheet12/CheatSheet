"""The transport the two ARCA services share: send an envelope, read an answer safely.

ARCA speaks SOAP 1.1 over plain `POST` in both of the services this system uses — WSAA to
mint an access ticket, the padrón A5 to look a taxpayer up. Nothing else about them is
alike: different hosts, different WSDLs, different meanings for the same fault code. What
*is* alike is everything below — the retry policy, the distinction between a fault and an
outage, and the parsing.

**Extracted when the second service arrived, not in anticipation of it.** `wsaa.py` carried
all of this alone while it was the only caller. The padrón unit would have had to copy it,
and the piece worth copying least is the entity-expansion guard: a defence that exists in
one of two parsers is a defence that does not exist.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from xml.etree import ElementTree

import httpx
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError as ParseErrorSeguro
from defusedxml.ElementTree import fromstring as parsear_xml

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import FallaDeArca
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Longer than Meta's. ARCA is slower, and a login that times out at 10 s on a busy
#: morning looks to the Administrator exactly like a rejected certificate.
TIMEOUT_POR_DEFECTO = 15.0
MAX_INTENTOS = 3
ESPERA_BASE = 1.0

_ESPACIOS = {"soap": "http://schemas.xmlsoap.org/soap/envelope/"}


@dataclass(frozen=True, slots=True)
class ConfiguracionSoap:
    """Where one ARCA service lives and how patient we are with it.

    `url` has no default on purpose. ARCA separates homologación from producción at the
    DNS level, so a default here would be a silent choice between practising and acting
    for real — the one decision in this adapter that must always be made out loud, by
    `APP_ENV`.
    """

    url: str
    timeout_segundos: float = TIMEOUT_POR_DEFECTO
    max_intentos: int = MAX_INTENTOS
    espera_base: float = ESPERA_BASE


class ClienteSoap:
    """Sends one envelope and returns the body as text. Raises this context's errors."""

    def __init__(
        self, config: ConfiguracionSoap, transporte: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._transporte = transporte

    @property
    def url(self) -> str:
        return self._config.url

    async def enviar(self, cuerpo: str, *, accion: str = "") -> str:
        cabeceras = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": accion}
        ultimo: Exception | None = None

        for intento in range(1, self._config.max_intentos + 1):
            try:
                async with self._cliente() as cliente:
                    respuesta = await cliente.post(
                        self._config.url, content=cuerpo.encode("utf-8"), headers=cabeceras
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                ultimo = exc
                # Nothing about the credential is logged: not the CMS, not the subject,
                # and — in the padrón's case — not the taxpayer being looked up.
                logger.warning("arca_soap_reintento", intento=intento, motivo=str(exc))
                await self._esperar(intento)
                continue

            if respuesta.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                falla = leer_falla(respuesta.text)
                if falla is not None:
                    # A SOAP fault arrives with HTTP 500. It is an answer, not an outage,
                    # so it goes back to the caller, which knows what its codes mean.
                    raise FallaRecibida(falla)
                ultimo = ProveedorNoDisponible(f"ARCA respondio {respuesta.status_code}")
                logger.warning("arca_soap_reintento", intento=intento, estado=respuesta.status_code)
                await self._esperar(intento)
                continue
            if respuesta.status_code >= httpx.codes.BAD_REQUEST:
                raise ProveedorNoDisponible(f"ARCA respondio {respuesta.status_code}")
            return respuesta.text

        raise ProveedorNoDisponible(
            f"ARCA no respondio tras {self._config.max_intentos} intentos: {ultimo}"
        )

    async def _esperar(self, intento: int) -> None:
        await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))

    def _cliente(self) -> httpx.AsyncClient:
        if self._transporte is not None:
            return httpx.AsyncClient(
                timeout=self._config.timeout_segundos, transport=self._transporte
            )
        return httpx.AsyncClient(timeout=self._config.timeout_segundos)


class FallaRecibida(Exception):
    """Carries a SOAP fault up to the service adapter, which decides what it means.

    Deliberately not translated here. `soapenv:Server` is a transient hiccup coming from
    WSAA and the ordinary way the padrón says «no existe persona con ese Id» — the same
    code, opposite meanings. A translation in the shared layer would have to know both,
    which is precisely the knowledge that belongs in each service's own module.
    """

    def __init__(self, falla: FallaDeArca) -> None:
        super().__init__(f"{falla.codigo}: {falla.detalle}")
        self.falla = falla


def raiz(texto: str) -> ElementTree.Element:
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


def leer_falla(texto: str) -> FallaDeArca | None:
    """Pull `faultcode` and `faultstring` out of a SOAP fault, if that is what this is."""
    try:
        documento = parsear_xml(texto)
    except (DefusedXmlException, ParseErrorSeguro):
        return None
    falla = documento.find(".//soap:Fault", _ESPACIOS)
    if falla is None:
        falla = documento.find(".//Fault")
    if falla is None:
        return None
    codigo = falla.findtext("faultcode") or falla.findtext("{*}faultcode") or ""
    detalle = falla.findtext("faultstring") or falla.findtext("{*}faultstring") or ""
    return FallaDeArca(codigo=codigo.strip(), detalle=detalle.strip())
