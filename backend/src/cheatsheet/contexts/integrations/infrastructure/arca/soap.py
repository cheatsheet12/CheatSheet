"""ARCA's flavour of the shared SOAP transport.

**The transport moved to `platform/soap.py` when epic 5 arrived.** This module used to hold
it, which was right while `integrations` was the only caller; then `reference_data` and
`billing` needed the same thing over WSFEv1 (ADR-0008) and rule R3 forbids them importing
this package. The alternative was a third copy of the entity-expansion guard, and this
file's previous docstring already argued against a second one.

What stayed here is what is genuinely ARCA's: **the translation**. `ProveedorNoDisponible`
is this context's word for «could not reach them», and `FallaDeArca` is what
`interpretar_falla` knows how to read. Neither belongs in `platform/`, which must not
decide what an outage means to a business rule.

The public surface is unchanged on purpose — `ClienteSoap`, `raiz`, `leer_falla` and
`FallaRecibida` behave exactly as before, so `wsaa.py` and `padron.py` did not change.
"""

from __future__ import annotations

from xml.etree import ElementTree

import httpx

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import FallaDeArca
from cheatsheet.platform.soap import (
    ESPERA_BASE,
    MAX_INTENTOS,
    TIMEOUT_POR_DEFECTO,
    ServicioSoapNoDisponible,
)
from cheatsheet.platform.soap import (
    ClienteSoap as ClienteSoapCompartido,
)
from cheatsheet.platform.soap import ConfiguracionSoap as ConfiguracionSoap
from cheatsheet.platform.soap import FallaRecibida as FallaCompartida
from cheatsheet.platform.soap import leer_falla as leer_falla_compartida
from cheatsheet.platform.soap import raiz as raiz_compartida

__all__ = [
    "ESPERA_BASE",
    "MAX_INTENTOS",
    "TIMEOUT_POR_DEFECTO",
    "ClienteSoap",
    "ConfiguracionSoap",
    "FallaRecibida",
    "leer_falla",
    "raiz",
]


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


class ClienteSoap(ClienteSoapCompartido):
    """The shared transport, speaking this context's error vocabulary."""

    def __init__(
        self, config: ConfiguracionSoap, transporte: httpx.AsyncBaseTransport | None = None
    ) -> None:
        super().__init__(config, transporte)

    async def enviar(self, cuerpo: str, *, accion: str = "") -> str:
        try:
            return await super().enviar(cuerpo, accion=accion)
        except FallaCompartida as exc:
            raise FallaRecibida(
                FallaDeArca(codigo=exc.falla.codigo, detalle=exc.falla.detalle)
            ) from exc
        except ServicioSoapNoDisponible as exc:
            raise ProveedorNoDisponible(str(exc).replace("El servicio", "ARCA")) from exc


def raiz(texto: str) -> ElementTree.Element:
    """The shared parser, raising this context's error. See `platform/soap.py` on why."""
    try:
        return raiz_compartida(texto)
    except ServicioSoapNoDisponible as exc:
        raise ProveedorNoDisponible(str(exc).replace("El servicio", "ARCA")) from exc


def leer_falla(texto: str) -> FallaDeArca | None:
    """Pull `faultcode` and `faultstring` out of a SOAP fault, if that is what this is."""
    falla = leer_falla_compartida(texto)
    if falla is None:
        return None
    return FallaDeArca(codigo=falla.codigo, detalle=falla.detalle)
