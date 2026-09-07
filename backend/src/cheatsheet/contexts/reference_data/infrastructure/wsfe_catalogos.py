"""WSFEv1's `FEParamGet*` operations, behind an ACL (ADR-0008, HS-T4).

**This is the first WSFEv1 client in the system**, and it is deliberately the small one.
Reading catalogues is the only part of that service where being wrong costs nothing: the
worst outcome is a stale list. `billing` writes the part where being wrong costs a document,
and it inherits the envelope shape and the response reading from here.

Four calls, one per catalogue the six stories need. `FEParamGetTiposIva` and
`FEParamGetTiposCbte` are the two that matter — the rates that multiply amounts and the
document types the issuing code validates against. `FEParamGetTiposDoc` and
`FEParamGetTiposMonedas` come along because they cost one envelope each and the DER's enum
names them.

**The ticket comes from `integrations`** (ADR-0004), which owns the certificate and the
private key. This module never sees either.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

from cheatsheet.contexts.reference_data.application.errors import CatalogoNoDisponible
from cheatsheet.contexts.reference_data.application.ports import EntradaDeCatalogo
from cheatsheet.contexts.reference_data.domain.parametro import TipoCatalogoFiscal
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.soap import (
    ClienteSoap,
    ConfiguracionSoap,
    FallaRecibida,
    ServicioSoapNoDisponible,
    raiz,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

#: The four operations, and the catalogue each one fills. Written as data rather than four
#: methods because the envelope is identical and only the operation name changes -- which
#: is the one thing WSFEv1 makes easy.
OPERACIONES: tuple[tuple[str, TipoCatalogoFiscal, str], ...] = (
    ("FEParamGetTiposCbte", TipoCatalogoFiscal.TIPO_COMPROBANTE, "CbteTipo"),
    ("FEParamGetTiposIva", TipoCatalogoFiscal.ALICUOTA_IVA, "IvaTipo"),
    ("FEParamGetTiposDoc", TipoCatalogoFiscal.TIPO_DOCUMENTO, "DocTipo"),
    ("FEParamGetTiposMonedas", TipoCatalogoFiscal.MONEDA, "Moneda"),
)

_ESPACIO_WSFE = "http://ar.gov.afip.dif.FEV1/"

#: The envelope. Built by formatting rather than with `ElementTree` because it is fixed
#: except for three values, and none of them comes from a user: the CUIT and the two ticket
#: fields are ours. Writing is not parsing -- the guard that matters is on the way back.
_SOBRE = """<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soapenv:Body>
    <ar:{operacion}>
      <ar:Auth>
        <ar:Token>{token}</ar:Token>
        <ar:Sign>{sign}</ar:Sign>
        <ar:Cuit>{cuit}</ar:Cuit>
      </ar:Auth>
    </ar:{operacion}>
  </soapenv:Body>
</soapenv:Envelope>"""


@dataclass(frozen=True, slots=True)
class CredencialDeWsfe:
    """What one company's ticket looks like once `integrations` has handed it over."""

    token: str
    sign: str
    cuit: str


class CatalogosDeWsfe:
    """`PortCatalogosFiscales` against the real WSFEv1."""

    def __init__(self, *, url: str, credenciales: dict[EmpresaId, CredencialDeWsfe]) -> None:
        self._cliente = ClienteSoap(ConfiguracionSoap(url=url))
        # Resolved by the composition root, which is allowed to talk to `integrations`.
        # Passing the ticket in rather than fetching it keeps rule R3 intact and this class
        # testable without a database.
        self._credenciales = credenciales

    async def obtener(self, *, empresa_id: EmpresaId) -> tuple[EntradaDeCatalogo, ...]:
        credencial = self._credenciales.get(empresa_id)
        if credencial is None:
            raise CatalogoNoDisponible(
                "La empresa no tiene un ticket de ARCA para consultar los catalogos"
            )

        entradas: list[EntradaDeCatalogo] = []
        for operacion, tipo, etiqueta in OPERACIONES:
            entradas.extend(await self._una(operacion, tipo, etiqueta, credencial))
        return tuple(entradas)

    async def _una(
        self,
        operacion: str,
        tipo: TipoCatalogoFiscal,
        etiqueta: str,
        credencial: CredencialDeWsfe,
    ) -> list[EntradaDeCatalogo]:
        cuerpo = _SOBRE.format(
            operacion=operacion,
            token=credencial.token,
            sign=credencial.sign,
            cuit=credencial.cuit,
        )
        try:
            respuesta = await self._cliente.enviar(cuerpo, accion=f"{_ESPACIO_WSFE}{operacion}")
        except FallaRecibida as exc:
            # A fault here is ARCA saying no, not an outage. One catalogue failing must not
            # lose the three that answered, so it is logged and skipped -- HS-T4 RN-04's
            # «keep the last one» applies per entry, and the use case sees fewer entries
            # rather than an exception.
            logger.warning("wsfe_catalogo_rechazado", operacion=operacion, falla=exc.falla.codigo)
            return []
        except ServicioSoapNoDisponible as exc:
            raise CatalogoNoDisponible(f"ARCA no respondio a {operacion}") from exc

        return _leer(raiz(respuesta), tipo, etiqueta)


def _leer(
    documento: ElementTree.Element, tipo: TipoCatalogoFiscal, etiqueta: str
) -> list[EntradaDeCatalogo]:
    """Pull `Id` and `Desc` out of every entry of one catalogue.

    Namespace-agnostic (`{*}`) on purpose: ARCA has moved the namespace of these responses
    before, and a parser pinned to one of them fails with «no entries» rather than with an
    error somebody would notice.
    """
    entradas: list[EntradaDeCatalogo] = []
    for nodo in documento.iter():
        if not nodo.tag.endswith(etiqueta):
            continue
        codigo = (nodo.findtext("{*}Id") or "").strip()
        valor = (nodo.findtext("{*}Desc") or "").strip()
        if codigo and valor:
            entradas.append(EntradaDeCatalogo(tipo=tipo, codigo=codigo, valor=valor))
    return entradas


class CatalogosSimulados:
    """The stand-in: ARCA's real codes, hard-coded, no socket.

    The values are the actual ones — `1` is Factura A, `5` is the 21 % rate — because a
    simulator with invented codes would let the issuing code pass tests it would fail
    against ARCA, which is the one thing a fiscal simulator must not do.

    **Rejected in production**: a company invoicing against a hard-coded catalogue would be
    validating its documents against a snapshot of what ARCA said the day this was written.
    """

    #: `(tipo, codigo, valor)`, from ARCA's published tables.
    CATALOGO: tuple[tuple[TipoCatalogoFiscal, str, str], ...] = (
        (TipoCatalogoFiscal.TIPO_COMPROBANTE, "1", "Factura A"),
        (TipoCatalogoFiscal.TIPO_COMPROBANTE, "3", "Nota de Credito A"),
        (TipoCatalogoFiscal.TIPO_COMPROBANTE, "6", "Factura B"),
        (TipoCatalogoFiscal.TIPO_COMPROBANTE, "8", "Nota de Credito B"),
        (TipoCatalogoFiscal.TIPO_COMPROBANTE, "11", "Factura C"),
        (TipoCatalogoFiscal.TIPO_COMPROBANTE, "13", "Nota de Credito C"),
        # The rate is the *value*, as a string, so it becomes a `Decimal` without ever
        # being a float. `3` is 0 %, `4` is 10,5 %, `5` is 21 % in ARCA's table.
        (TipoCatalogoFiscal.ALICUOTA_IVA, "3", "0.00"),
        (TipoCatalogoFiscal.ALICUOTA_IVA, "4", "0.105"),
        (TipoCatalogoFiscal.ALICUOTA_IVA, "5", "0.21"),
        (TipoCatalogoFiscal.TIPO_DOCUMENTO, "80", "CUIT"),
        (TipoCatalogoFiscal.TIPO_DOCUMENTO, "96", "DNI"),
        (TipoCatalogoFiscal.TIPO_DOCUMENTO, "99", "Consumidor Final"),
        (TipoCatalogoFiscal.MONEDA, "PES", "Pesos Argentinos"),
    )

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El catalogo fiscal simulado no es valido en produccion: "
                "los comprobantes se validarian contra una foto y no contra ARCA."
            )

    async def obtener(self, *, empresa_id: EmpresaId) -> tuple[EntradaDeCatalogo, ...]:
        del empresa_id  # The catalogue is ARCA's, not the company's.
        return tuple(
            EntradaDeCatalogo(tipo=tipo, codigo=codigo, valor=valor)
            for tipo, codigo, valor in self.CATALOGO
        )
