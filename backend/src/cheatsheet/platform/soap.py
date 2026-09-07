"""SOAP transport: send an envelope, read the answer safely.

**Why this is in `platform/` and not in a context.** It was written by `conexion-arca` in
epic 2 and lived in `integrations/infrastructure/arca/soap.py`, which was right while
`integrations` was the only caller. Epic 5 adds two more — `reference_data` syncs ARCA's
catalogues and `billing` issues documents, both over WSFEv1 (ADR-0008) — and rule R3
forbids either of them from importing another context's `infrastructure/`.

That left duplicating it, and **the module's own docstring already argued against that**:
«the piece worth copying least is the entity-expansion guard: a defence that exists in one
of two parsers is a defence that does not exist». Three copies would be worse than two.

So the transport moved here, where `CLAUDE.md` §2 puts the plumbing every layer stands on,
and each context keeps what is genuinely its own: **what a fault means**. `soapenv:Server`
is a transient hiccup from WSAA and the ordinary way the padrón says «no existe persona con
ese Id» — the same code, opposite meanings. That knowledge stays in each service's adapter,
which is why `FallaSoap` is data and never an interpretation.

Nothing about ARCA is in this file. It is SOAP 1.1 over `POST`, with a timeout, a bounded
retry and a parser that refuses a hostile document.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from xml.etree import ElementTree

import httpx
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError as ParseErrorSeguro
from defusedxml.ElementTree import fromstring as parsear_xml

from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Longer than a browser-facing call. These providers are slow, and a request that times
#: out at 10 s on a busy morning looks exactly like a rejected credential.
TIMEOUT_POR_DEFECTO = 15.0
MAX_INTENTOS = 3
ESPERA_BASE = 1.0

_ESPACIOS = {"soap": "http://schemas.xmlsoap.org/soap/envelope/"}


class ServicioSoapNoDisponible(Exception):
    """The provider could not be reached, or answered something unusable.

    Deliberately not a `ErrorDeDominio`: this is transport, and turning it into a domain
    error here would decide, in `platform/`, what an outage means to a business rule. Each
    adapter catches it and raises its own.
    """


@dataclass(frozen=True, slots=True)
class FallaSoap:
    """A SOAP fault, as data. **Never as an interpretation** — see the module docstring."""

    codigo: str
    detalle: str


class FallaRecibida(Exception):
    """Carries a fault up to the service adapter, which decides what it means."""

    def __init__(self, falla: FallaSoap) -> None:
        super().__init__(f"{falla.codigo}: {falla.detalle}")
        self.falla = falla


@dataclass(frozen=True, slots=True)
class ConfiguracionSoap:
    """Where one service lives and how patient we are with it.

    `url` has no default on purpose. ARCA separates homologación from producción at the DNS
    level, so a default here would be a silent choice between practising and acting for
    real — the one decision in an adapter like this that must always be made out loud, by
    `APP_ENV`.
    """

    url: str
    timeout_segundos: float = TIMEOUT_POR_DEFECTO
    max_intentos: int = MAX_INTENTOS
    espera_base: float = ESPERA_BASE


class ClienteSoap:
    """Sends one envelope and returns the body as text."""

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
                # and not the taxpayer being looked up.
                logger.warning("soap_reintento", intento=intento, motivo=str(exc))
                await self._esperar(intento)
                continue

            if respuesta.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                falla = leer_falla(respuesta.text)
                if falla is not None:
                    # A SOAP fault arrives with HTTP 500. It is an answer, not an outage,
                    # so it goes back to the caller, which knows what its codes mean.
                    raise FallaRecibida(falla)
                ultimo = ServicioSoapNoDisponible(f"El servicio respondio {respuesta.status_code}")
                logger.warning("soap_reintento", intento=intento, estado=respuesta.status_code)
                await self._esperar(intento)
                continue
            if respuesta.status_code >= httpx.codes.BAD_REQUEST:
                raise ServicioSoapNoDisponible(f"El servicio respondio {respuesta.status_code}")
            return respuesta.text

        raise ServicioSoapNoDisponible(
            f"El servicio no respondio tras {self._config.max_intentos} intentos: {ultimo}"
        )

    async def _esperar(self, intento: int) -> None:
        await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))

    def _cliente(self) -> httpx.AsyncClient:
        if self._transporte is not None:
            return httpx.AsyncClient(
                timeout=self._config.timeout_segundos, transport=self._transporte
            )
        return httpx.AsyncClient(timeout=self._config.timeout_segundos)


def raiz(texto: str) -> ElementTree.Element:
    """Parsed with `defusedxml`, and the reason is measurable rather than ceremonial.

    `xml.etree` on 3.11 expands internal entities — verified before adding the dependency:
    a 300-byte document expanded to 3 000 characters, ten times per nesting level. A
    response from an external service is untrusted input by definition, and this parses
    one. `defusedxml` refuses the document instead — raising `DefusedXmlException`, which
    is **not** a `ParseError` and therefore needs its own clause. A test caught that:
    without the first branch below, the refusal escaped untranslated and would have taken
    down a Beat task with an exception nobody catches.

    Building XML with `ElementTree` is unaffected: writing is not parsing.
    """
    try:
        return parsear_xml(texto)
    except DefusedXmlException as exc:
        raise ServicioSoapNoDisponible(
            "El servicio respondio un XML que no es seguro procesar"
        ) from exc
    except ParseErrorSeguro as exc:
        raise ServicioSoapNoDisponible("El servicio respondio algo que no es XML") from exc


def leer_falla(texto: str) -> FallaSoap | None:
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
    return FallaSoap(codigo=codigo.strip(), detalle=detalle.strip())
