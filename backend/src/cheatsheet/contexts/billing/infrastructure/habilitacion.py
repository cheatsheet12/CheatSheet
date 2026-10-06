"""`FEParamGetPtosVenta`: which points of sale ARCA knows about (HU-E5-05 RN-03).

The second WSFEv1 client, and the same envelope shape `reference_data` established. It
reads and nothing else, which is why it can be written before the one that issues: being
wrong here costs a rejected activation, not a wrong document.

**The two failure modes stay apart.** A fault means ARCA answered — «that point is not
yours» — and blocks the activation for good. An unreachable service means we could not ask,
and is worth trying again. Collapsing them would either block a legitimate point during an
outage or activate one ARCA never enabled.
"""

from __future__ import annotations

from xml.etree import ElementTree

import httpx

from cheatsheet.contexts.billing.application.errors import ArcaNoDisponible
from cheatsheet.contexts.billing.application.ports import PuntoHabilitado
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.soap import (
    ClienteSoap,
    ConfiguracionSoap,
    FallaRecibida,
    ServicioSoapNoDisponible,
    raiz,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.platform.wsfe import PortCredencialesDeWsfe
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

OPERACION = "FEParamGetPtosVenta"
_ESPACIO_WSFE = "http://ar.gov.afip.dif.FEV1/"

_SOBRE = """<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soapenv:Body>
    <ar:FEParamGetPtosVenta>
      <ar:Auth>
        <ar:Token>{token}</ar:Token>
        <ar:Sign>{sign}</ar:Sign>
        <ar:Cuit>{cuit}</ar:Cuit>
      </ar:Auth>
    </ar:FEParamGetPtosVenta>
  </soapenv:Body>
</soapenv:Envelope>"""


class HabilitacionEnArca:
    """`PortHabilitacionDeArca` against the real WSFEv1."""

    def __init__(
        self,
        *,
        url: str,
        credenciales: PortCredencialesDeWsfe,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # `transporte` is how every other SOAP client here is tested: `httpx.MockTransport`
        # goes where the socket would be. Without it the reader below is only exercisable
        # by reaching into a private attribute, which is a test that breaks on a rename.
        self._cliente = ClienteSoap(ConfiguracionSoap(url=url), transporte)
        # Resolved by the composition root, which is the one place allowed to wire two
        # contexts together (R3). See `api/arca.py`.
        self._credenciales = credenciales

    async def puntos_habilitados(self, *, empresa_id: EmpresaId) -> tuple[PuntoHabilitado, ...]:
        credencial = await self._credenciales.para(empresa_id)

        cuerpo = _SOBRE.format(token=credencial.token, sign=credencial.sign, cuit=credencial.cuit)
        try:
            respuesta = await self._cliente.enviar(cuerpo, accion=f"{_ESPACIO_WSFE}{OPERACION}")
        except FallaRecibida as exc:
            logger.warning("wsfe_puntos_rechazado", falla=exc.falla.codigo)
            # A fault is an answer. Reporting no points blocks the activation, which is
            # what «that point is not yours» should do.
            return ()
        except ServicioSoapNoDisponible as exc:
            raise ArcaNoDisponible("ARCA no respondio a la consulta de puntos de venta") from exc

        return _leer(raiz(respuesta))


def _leer(documento: ElementTree.Element) -> tuple[PuntoHabilitado, ...]:
    """Pull `Nro` and `Bloqueado` out of every point ARCA reports.

    Namespace-agnostic for the reason `reference_data`'s reader gives: ARCA has moved the
    namespace before, and a pinned parser fails with «no points» instead of an error.
    """
    puntos: list[PuntoHabilitado] = []
    for nodo in documento.iter():
        if not nodo.tag.endswith("PtoVenta"):
            continue
        numero = (nodo.findtext("{*}Nro") or "").strip()
        if not numero.isdigit():
            continue
        # ARCA answers "S"/"N". **Only an explicit "N" means usable**; anything else --
        # "S", an empty element, a missing one, a value we do not recognise -- is read as
        # blocked. That is the conservative direction: the cost of a false «blocked» is a
        # failed alta with a message somebody can report, and the cost of a false
        # «enabled» is a point activated here that rejects its first real invoice with a
        # code that talks about something else.
        #
        # Written as `or ""` and not `or "N"`, which is the bug this replaced: an empty
        # element is falsy, so the default fired and «ARCA did not tell us» was read as
        # «not blocked» -- the unsafe direction, in the one branch nobody would notice.
        bloqueado = (nodo.findtext("{*}Bloqueado") or "").strip().upper() != "N"
        puntos.append(PuntoHabilitado(numero=int(numero), bloqueado=bloqueado))
    return tuple(puntos)


class HabilitacionSimulada:
    """The stand-in: a fixed set of points, no socket.

    Points 1 to 5 are enabled and 99 is blocked, so both branches of RN-03 are walkable on
    a laptop. **Rejected in production**: a company activating a point against this would
    be activating one ARCA may never have enabled, and would find out when its first
    invoice is rejected with a code that talks about something else.
    """

    HABILITADOS = (1, 2, 3, 4, 5)
    BLOQUEADOS = (99,)

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "La habilitacion simulada no es valida en produccion: "
                "se activarian puntos de venta que ARCA no habilito."
            )

    async def puntos_habilitados(self, *, empresa_id: EmpresaId) -> tuple[PuntoHabilitado, ...]:
        del empresa_id
        return tuple(
            [PuntoHabilitado(numero=n) for n in self.HABILITADOS]
            + [PuntoHabilitado(numero=n, bloqueado=True) for n in self.BLOQUEADOS]
        )
