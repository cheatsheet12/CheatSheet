"""ARCA's taxpayer registry: `getPersona` on the padrón A5 service.

The Anti-Corruption Layer of the padrón unit. ARCA answers in its own vocabulary —
`datosMonotributo`, `idImpuesto`, `estadoClave` — and what leaves this module is
`DatosDePadron`: a name, a `CondicionIVA` and whether the tax id is in force.

**Two things this module refuses to do**, and both are why it exists:

1. **It never guesses a `CondicionIVA`.** When the answer does not clearly say what the
   taxpayer is, it returns `None` and the person filling in the form chooses — HU-E1-02
   RN-02 allows correcting it by hand, so a wrong autocomplete is worse than none. What
   is decided here ends up deciding which kind of `Comprobante` epic 5 may issue.
2. **It never logs what it read.** A padrón answer is somebody's real name and tax id. The
   log records that a lookup happened; the content stays in memory.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from xml.etree import ElementTree

import httpx

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.application.ports import DatosDePadron
from cheatsheet.contexts.integrations.application.ticket import desempaquetar
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import CLAVE_CUIT, interpretar_falla
from cheatsheet.contexts.integrations.infrastructure.arca.soap import (
    ClienteSoap,
    ConfiguracionSoap,
    FallaRecibida,
    raiz,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.fiscal import CondicionIVA

logger = obtener_logger(__name__)

URL_HOMOLOGACION = "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5"
URL_PRODUCCION = "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5"

#: The padrón needs nothing the shared transport does not already offer.
ConfiguracionPadron = ConfiguracionSoap

#: ARCA's tax identifiers. Only the two that decide a `CondicionIVA` are listed: the
#: registry returns a dozen more — ganancias, bienes personales — and none of them answers
#: the question this module asks.
IMPUESTO_IVA = "30"
IMPUESTO_IVA_EXENTO = "32"

#: `estadoClave` when the tax id is in force. Anything else — «INACTIVO», a cancellation —
#: is reported rather than hidden: the CUIT exists, so it does not block, but invoicing a
#: deregistered taxpayer is something the Administrator should hear about first.
ESTADO_ACTIVO = "ACTIVO"

#: The padrón says «this CUIT does not exist» through a `soapenv:Server` fault, which for
#: WSAA means «ARCA is having a moment». Same code, opposite meanings — which is exactly
#: why `soap.py` hands the fault back untranslated instead of deciding for both services.
#: Matched on the message, because that is the only thing that tells them apart.
_NO_ENCONTRADO = re.compile(r"no existe persona|persona no encontrada|id no encontrado", re.I)

_SOLO_DIGITOS = re.compile(r"[^0-9]")

_SOBRE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:a5="http://a5.soap.ws.server.puc.sr/">'
    "<soapenv:Header/><soapenv:Body><a5:getPersona>"
    "<token>{token}</token><sign>{sign}</sign>"
    "<cuitRepresentada>{representada}</cuitRepresentada>"
    "<idPersona>{persona}</idPersona>"
    "</a5:getPersona></soapenv:Body></soapenv:Envelope>"
)


class ClientePadronA5:
    """Implements `PortConsultaDePadron`."""

    def __init__(
        self, config: ConfiguracionSoap, transporte: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._soap = ClienteSoap(config, transporte)

    async def consultar(
        self, *, ticket: bytes, parametros: Mapping[str, Any], cuit: str
    ) -> DatosDePadron | None:
        """`None` means ARCA does not know that tax id. Anything else raises."""
        token, sign = desempaquetar(ticket)
        consultado = _normalizar(cuit)
        cuerpo = _SOBRE.format(
            token=token,
            sign=sign,
            representada=_cuit_representada(parametros),
            persona=consultado,
        )
        logger.info("padron_consulta")
        try:
            respuesta = await self._soap.enviar(cuerpo)
        except FallaRecibida as recibida:
            if _NO_ENCONTRADO.search(recibida.falla.detalle):
                return None
            raise interpretar_falla(recibida.falla) from recibida
        return leer_persona(respuesta, consultado)


def _cuit_representada(parametros: Mapping[str, Any]) -> str:
    """Whose certificate is asking. ARCA refuses a lookup that does not say.

    It comes from the subject of the stored certificate, which `conexion-arca` already
    extracted. When it is missing the credential is still usable for WSFE — the connection
    was never blocked on it — but it cannot query the registry, and saying so beats
    sending ARCA a request it will reject for a reason that reads like something else.
    """
    valor = _normalizar(str(parametros.get(CLAVE_CUIT, "")))
    if not valor:
        raise ProveedorNoDisponible(
            "El certificado guardado no declara un CUIT, asi que no puede consultar el padron"
        )
    return valor


def _normalizar(cuit: str) -> str:
    return _SOLO_DIGITOS.sub("", cuit)


def leer_persona(texto: str, cuit: str) -> DatosDePadron | None:
    """Public because the stand-in feeds its fabricated answers through it.

    Same rule the WSAA stand-in follows: only the socket is replaced, so a laptop
    exercises the parsing and the fiscal translation that production runs.
    """
    documento = raiz(texto)
    generales = _buscar(documento, "datosGenerales")
    if generales is None:
        # A well-formed answer with no `datosGenerales` is how the registry reports an
        # unknown tax id when it does not raise a fault. Same meaning, same answer.
        return None
    return DatosDePadron(
        cuit=cuit,
        razon_social=_razon_social(generales),
        condicion_iva=_condicion_iva(documento),
        activo=(_texto(generales, "estadoClave") or "").upper() == ESTADO_ACTIVO,
    )


def _razon_social(generales: ElementTree.Element) -> str | None:
    """`razonSocial` for a company; surname and given name for a person.

    ARCA fills one pair or the other, never both, and the joined form is what the padrón
    itself shows on screen.
    """
    razon = _texto(generales, "razonSocial")
    if razon:
        return razon
    apellido = _texto(generales, "apellido") or ""
    nombre = _texto(generales, "nombre") or ""
    return f"{apellido} {nombre}".strip() or None


def _condicion_iva(documento: ElementTree.Element) -> CondicionIVA | None:
    """The one translation with fiscal consequences. Silence beats a guess."""
    if _buscar(documento, "datosMonotributo") is not None:
        return CondicionIVA.MONOTRIBUTO
    impuestos = _impuestos(documento)
    if IMPUESTO_IVA in impuestos:
        return CondicionIVA.RESPONSABLE_INSCRIPTO
    if IMPUESTO_IVA_EXENTO in impuestos:
        return CondicionIVA.EXENTO
    return None


def _impuestos(documento: ElementTree.Element) -> set[str]:
    """Every `idImpuesto` in the answer, whatever it is nested under.

    Walked rather than addressed by path because the registry nests the list differently
    for a monotributista and for the general regime, and a path that assumes one shape
    silently finds nothing in the other.
    """
    valores = {
        (elemento.text or "").strip()
        for elemento in documento.iter()
        if _local(elemento.tag) == "idImpuesto"
    }
    return {valor for valor in valores if valor}


def _buscar(documento: ElementTree.Element, etiqueta: str) -> ElementTree.Element | None:
    """Find a child by name whether or not the answer is namespaced."""
    encontrado = documento.find(f".//{etiqueta}")
    return encontrado if encontrado is not None else documento.find(f".//{{*}}{etiqueta}")


def _texto(elemento: ElementTree.Element, etiqueta: str) -> str | None:
    valor = elemento.findtext(etiqueta) or elemento.findtext(f"{{*}}{etiqueta}")
    return valor.strip() if valor and valor.strip() else None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
