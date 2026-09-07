"""WSFEv1's three issuing operations, behind an ACL (ADR-0008).

`FECAESolicitar` asks for a CAE, `FECompConsultar` asks what happened to a document already
sent, and `FECompUltimoAutorizado` asks where the numbering is. The second and third exist
because of decisions D17 and D18, and they are what make the first safe: **`FECAESolicitar`
is not idempotent**, so a client that offered only it would force its callers to choose
between losing a document and issuing it twice.

Two things about the envelope are worth stating rather than leaving to be discovered:

- **The amounts are written from the aggregate's already-rounded values** (D15). Nothing
  here multiplies anything. A second implementation of the arithmetic is a second chance to
  disagree with the document ARCA authorised, and ARCA rejects the disagreement with a code
  that does not mention the centavo.
- **The VAT breakdown is grouped by rate**, which is what `FECAESolicitar` wants: one `<Iva>`
  entry per rate present, with the base and the amount summed over the items at that rate.
  Sending one entry per item is a rejection.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from xml.etree import ElementTree

import httpx

from cheatsheet.contexts.billing.application.errors import ArcaNoDisponible
from cheatsheet.contexts.billing.application.ports import RespuestaDeArca
from cheatsheet.contexts.billing.domain.comprobante import CAE, AlicuotaIVA, Comprobante
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.soap import (
    ClienteSoap,
    ConfiguracionSoap,
    FallaRecibida,
    ServicioSoapNoDisponible,
    raiz,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.platform.wsfe import CredencialDeWsfe, PortCredencialesDeWsfe
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

_ESPACIO_WSFE = "http://ar.gov.afip.dif.FEV1/"

#: ARCA's document-type code for the receptor's identifier. 80 is CUIT; 99 is "consumidor
#: final sin identificar", which this system never issues because HU-E5-03 RN-02 requires a
#: CUIT validated against the padrón before the form is even enabled.
DOC_TIPO_CUIT = 80

#: `Concepto` 1 = productos. The system invoices services and products alike and ARCA only
#: demands the service date range for concepts 2 and 3, which this never sends.
CONCEPTO_PRODUCTOS = 1

#: ARCA wants dates as `yyyymmdd`, with no separators.
_FORMATO_FECHA = "%Y%m%d"

_AUTH = """      <ar:Auth>
        <ar:Token>{token}</ar:Token>
        <ar:Sign>{sign}</ar:Sign>
        <ar:Cuit>{cuit}</ar:Cuit>
      </ar:Auth>"""

_SOBRE = """<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soapenv:Body>
    <ar:{operacion}>
{auth}
{cuerpo}
    </ar:{operacion}>
  </soapenv:Body>
</soapenv:Envelope>"""


def _fecha(momento: datetime | date) -> str:
    valor = momento.date() if isinstance(momento, datetime) else momento
    return valor.strftime(_FORMATO_FECHA)


def _monto(valor: Decimal) -> str:
    """Two decimals as text. Never a float on the way out, for the obvious reason."""
    return f"{valor:.2f}"


def _iva_agrupado(comprobante: Comprobante) -> list[tuple[AlicuotaIVA, Decimal, Decimal]]:
    """One entry per rate present: `(alicuota, base imponible, importe)`.

    Grouped, not per item -- WSFEv1 rejects an `<Iva>` array with repeated `Id`. The sums
    are of already-rounded item values, so the total here equals the document's total by
    construction and not by a second calculation.
    """
    bases: dict[AlicuotaIVA, Decimal] = defaultdict(lambda: Decimal("0.00"))
    importes: dict[AlicuotaIVA, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for item in comprobante.items:
        bases[item.alicuota_iva] += item.subtotal
        importes[item.alicuota_iva] += item.iva
    return [
        (alicuota, bases[alicuota], importes[alicuota])
        for alicuota in sorted(bases, key=lambda a: a.codigo_arca)
    ]


def _cuerpo_de_solicitud(comprobante: Comprobante, punto_numero: int, emitido: date) -> str:
    """The `FECAESolicitar` request for exactly one document.

    One at a time, although WSFEv1 accepts batches. A batch that partially fails answers
    per-document and the caller has to unpick which of ten got a CAE -- which is the same
    ambiguity D17 exists to avoid, multiplied by ten.
    """
    if comprobante.numero is None:  # pragma: no cover - guarded by the use case
        raise ArcaNoDisponible("El comprobante no tiene numero asignado")

    iva = "".join(
        f"<ar:AlicIva><ar:Id>{alicuota.codigo_arca}</ar:Id>"
        f"<ar:BaseImp>{_monto(base)}</ar:BaseImp>"
        f"<ar:Importe>{_monto(importe)}</ar:Importe></ar:AlicIva>"
        for alicuota, base, importe in _iva_agrupado(comprobante)
    )
    return f"""      <ar:FeCAEReq>
        <ar:FeCabReq>
          <ar:CantReg>1</ar:CantReg>
          <ar:PtoVta>{punto_numero}</ar:PtoVta>
          <ar:CbteTipo>{comprobante.tipo.codigo_arca}</ar:CbteTipo>
        </ar:FeCabReq>
        <ar:FeDetReq>
          <ar:FECAEDetRequest>
            <ar:Concepto>{CONCEPTO_PRODUCTOS}</ar:Concepto>
            <ar:DocTipo>{DOC_TIPO_CUIT}</ar:DocTipo>
            <ar:DocNro>{comprobante.receptor.cuit}</ar:DocNro>
            <ar:CbteDesde>{comprobante.numero}</ar:CbteDesde>
            <ar:CbteHasta>{comprobante.numero}</ar:CbteHasta>
            <ar:CbteFch>{_fecha(emitido)}</ar:CbteFch>
            <ar:ImpTotal>{_monto(comprobante.total)}</ar:ImpTotal>
            <ar:ImpTotConc>0.00</ar:ImpTotConc>
            <ar:ImpNeto>{_monto(comprobante.subtotal)}</ar:ImpNeto>
            <ar:ImpOpEx>0.00</ar:ImpOpEx>
            <ar:ImpTrib>0.00</ar:ImpTrib>
            <ar:ImpIVA>{_monto(comprobante.total_iva)}</ar:ImpIVA>
            <ar:MonId>PES</ar:MonId>
            <ar:MonCotiz>1</ar:MonCotiz>
            <ar:Iva>{iva}</ar:Iva>
          </ar:FECAEDetRequest>
        </ar:FeDetReq>
      </ar:FeCAEReq>"""


class AutorizacionEnArca:
    """`PortAutorizacionDeArca` against the real WSFEv1."""

    def __init__(
        self,
        *,
        url: str,
        credenciales: PortCredencialesDeWsfe,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._cliente = ClienteSoap(ConfiguracionSoap(url=url), transporte)
        self._credenciales = credenciales

    async def solicitar(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante
    ) -> RespuestaDeArca:
        credencial = await self._credenciales.para(empresa_id)
        punto = await self._numero_de_punto(empresa_id, comprobante)
        emitido = (comprobante.fecha_emision or comprobante.created_at).date()
        respuesta = await self._enviar(
            "FECAESolicitar",
            credencial,
            _cuerpo_de_solicitud(comprobante, punto, emitido),
        )
        return _leer_resultado(raiz(respuesta))

    async def consultar(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante
    ) -> RespuestaDeArca | None:
        """`FECompConsultar`. `None` when ARCA has no record of that number (D17)."""
        if comprobante.numero is None:  # pragma: no cover - guarded by the use case
            return None
        credencial = await self._credenciales.para(empresa_id)
        punto = await self._numero_de_punto(empresa_id, comprobante)
        cuerpo = f"""      <ar:FeCompConsReq>
        <ar:CbteTipo>{comprobante.tipo.codigo_arca}</ar:CbteTipo>
        <ar:CbteNro>{comprobante.numero}</ar:CbteNro>
        <ar:PtoVta>{punto}</ar:PtoVta>
      </ar:FeCompConsReq>"""
        try:
            respuesta = await self._enviar("FECompConsultar", credencial, cuerpo)
        except FallaRecibida as exc:
            # ARCA answers a fault for "no existe el comprobante solicitado" as well as for
            # real problems. Reading it as "no record" is the safe direction **only**
            # because the caller then retries the issue -- which is what happens when the
            # document was never authorised anyway.
            logger.warning("wsfe_consulta_rechazada", falla=exc.falla.codigo)
            return None
        return _leer_consulta(raiz(respuesta))

    async def ultimo_autorizado(
        self, *, empresa_id: EmpresaId, punto: PuntoDeVenta, tipo: TipoComprobante
    ) -> int:
        """`FECompUltimoAutorizado` (D18). Zero when nothing has been authorised yet."""
        credencial = await self._credenciales.para(empresa_id)
        cuerpo = (
            f"      <ar:PtoVta>{punto.numero}</ar:PtoVta>\n"
            f"      <ar:CbteTipo>{tipo.codigo_arca}</ar:CbteTipo>"
        )
        respuesta = await self._enviar("FECompUltimoAutorizado", credencial, cuerpo)
        texto = (raiz(respuesta).findtext(".//{*}CbteNro") or "0").strip()
        return int(texto) if texto.isdigit() else 0

    async def _numero_de_punto(self, empresa_id: EmpresaId, comprobante: Comprobante) -> int:
        numero = await self._credenciales.numero_de_punto(empresa_id, comprobante.punto_de_venta_id)
        if numero is None:  # pragma: no cover - the use case loaded the point already
            raise ArcaNoDisponible("No se pudo resolver el numero del punto de venta")
        return numero

    async def _enviar(self, operacion: str, credencial: CredencialDeWsfe, cuerpo: str) -> str:
        sobre = _SOBRE.format(
            operacion=operacion,
            auth=_AUTH.format(token=credencial.token, sign=credencial.sign, cuit=credencial.cuit),
            cuerpo=cuerpo,
        )
        try:
            return await self._cliente.enviar(sobre, accion=f"{_ESPACIO_WSFE}{operacion}")
        except ServicioSoapNoDisponible as exc:
            # **The distinction the whole unit rests on.** Unreachable says nothing about
            # whether ARCA authorised the document, so it must never become a rejection.
            raise ArcaNoDisponible(f"ARCA no respondio a {operacion}") from exc


def _leer_resultado(documento: ElementTree.Element) -> RespuestaDeArca:
    """Read `FECAESolicitar`'s answer.

    Namespace-agnostic (`{*}`) for the reason `reference_data`'s reader gives: ARCA has
    moved the namespace before, and a pinned parser fails with a shape that reads like a
    rejection.
    """
    resultado = (documento.findtext(".//{*}Resultado") or "").strip().upper()
    if resultado == "A":
        cae = (documento.findtext(".//{*}CAE") or "").strip()
        vencimiento = (documento.findtext(".//{*}CAEFchVto") or "").strip()
        if cae and len(vencimiento) == 8:
            return RespuestaDeArca(
                autorizado=True, cae=CAE(codigo=cae, vence_el=_desde_yyyymmdd(vencimiento))
            )
        # "Approved" without a usable CAE is not an approval we can record. Treating it as
        # unreachable keeps the document in flight, where reconciliation can settle it --
        # far better than writing a document as authorised with no code on it.
        raise ArcaNoDisponible("ARCA aprobo el comprobante pero no devolvio un CAE utilizable")

    codigo, descripcion = _primer_error(documento)
    return RespuestaDeArca(autorizado=False, codigo=codigo, descripcion=descripcion)


def _leer_consulta(documento: ElementTree.Element) -> RespuestaDeArca | None:
    """Read `FECompConsultar`'s answer. `None` when ARCA has no record."""
    cae = (documento.findtext(".//{*}CodAutorizacion") or "").strip()
    vencimiento = (documento.findtext(".//{*}FchVto") or "").strip()
    if not cae or len(vencimiento) != 8:
        return None
    return RespuestaDeArca(
        autorizado=True, cae=CAE(codigo=cae, vence_el=_desde_yyyymmdd(vencimiento))
    )


def _primer_error(documento: ElementTree.Element) -> tuple[str, str]:
    """ARCA's own code and words, which HU-E5-03 shows verbatim.

    `Errors` carries the hard refusals and `Observaciones` the soft ones; a rejected
    document normally has the first. Falling back to the second is what stops the screen
    saying «SIN_CODIGO» when ARCA in fact explained itself.
    """
    for etiqueta in ("Err", "Obs"):
        for nodo in documento.iter():
            if not nodo.tag.endswith(etiqueta):
                continue
            codigo = (nodo.findtext("{*}Code") or "").strip()
            mensaje = (nodo.findtext("{*}Msg") or "").strip()
            if codigo or mensaje:
                return codigo or "SIN_CODIGO", mensaje or "ARCA rechazo el comprobante"
    return "SIN_CODIGO", "ARCA rechazo el comprobante sin indicar el motivo"


def _desde_yyyymmdd(texto: str) -> date:
    return date(int(texto[:4]), int(texto[4:6]), int(texto[6:8]))


class AutorizacionSimulada:
    """The stand-in: a CAE without a socket.

    **Rejected in production**, like every simulated adapter here, and with more at stake
    than any of them: a company invoicing against this would be handing customers documents
    with an invented CAE, which is not a bug — it is undeclared sales.

    It is deliberately not always-yes. A document whose total ends in `.99` is rejected with
    ARCA's real code 10016, so the rejection path of HU-E5-03 is walkable on a laptop
    without editing code.
    """

    #: The real error code the story quotes, so what a developer sees locally is what a
    #: user would see in production.
    CODIGO_DE_RECHAZO = "10016"
    DESCRIPCION_DE_RECHAZO = "el comprobante no cumple la resolucion general vigente"

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "La autorizacion simulada de ARCA no puede usarse en produccion: "
                "emitiria comprobantes con un CAE inventado"
            )
        self._autorizados: dict[tuple[str, int, int], RespuestaDeArca] = {}
        self._ultimos: dict[tuple[str, str, int], int] = {}

    async def solicitar(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante
    ) -> RespuestaDeArca:
        if comprobante.numero is None:  # pragma: no cover - guarded by the use case
            raise ArcaNoDisponible("El comprobante no tiene numero asignado")

        if str(comprobante.total).endswith(".99"):
            return RespuestaDeArca(
                autorizado=False,
                codigo=self.CODIGO_DE_RECHAZO,
                descripcion=self.DESCRIPCION_DE_RECHAZO,
            )

        # The issue date the use case already stamped. No clock here: an adapter that
        # invents its own "now" is an adapter whose tests need one too.
        vence = comprobante.fecha_emision or comprobante.created_at
        respuesta = RespuestaDeArca(
            autorizado=True,
            # Shaped like a real one: 14 digits. Code that only ever sees an 8-character
            # placeholder is code that breaks the day it meets ARCA.
            cae=CAE(codigo=f"7{comprobante.numero:013d}", vence_el=vence.date()),
        )
        # Recorded so `consultar` can answer honestly -- which is what makes the
        # reconciliation of D17 exercisable end to end without a network.
        self._autorizados[self._clave(empresa_id, comprobante)] = respuesta
        self._ultimos[
            (str(empresa_id), str(comprobante.punto_de_venta_id), comprobante.tipo.codigo_arca)
        ] = comprobante.numero
        return respuesta

    async def consultar(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante
    ) -> RespuestaDeArca | None:
        return self._autorizados.get(self._clave(empresa_id, comprobante))

    async def ultimo_autorizado(
        self, *, empresa_id: EmpresaId, punto: PuntoDeVenta, tipo: TipoComprobante
    ) -> int:
        return self._ultimos.get((str(empresa_id), str(punto.id), tipo.codigo_arca), 0)

    @staticmethod
    def _clave(empresa_id: EmpresaId, comprobante: Comprobante) -> tuple[str, int, int]:
        return (
            str(empresa_id),
            comprobante.tipo.codigo_arca,
            comprobante.numero or 0,
        )


__all__ = [
    "AutorizacionEnArca",
    "AutorizacionSimulada",
]
