"""Connecting ARCA by **delegation** of the web service to CheatSheet (ADR-0014).

A company no longer uploads a certificate. It delegates «Facturación Electrónica» to
CheatSheet's CUIT at ARCA, and connecting is asking ARCA whether that delegation exists:
the platform certificate's ticket, the company's CUIT in `<Auth><Cuit>`, and the cheapest
read WSFEv1 has — `FECompUltimoAutorizado`. Nothing is issued.

ARCA answers a missing delegation with error **600** or **601** (*ValidacionDeToken*: the
CUIT is not among the certificate's relations). Any other answer — a number, or an error
about the point of sale or the voucher type — means ARCA accepted to speak for that CUIT,
which is the only thing being asked.

The status check asks the same question, so a delegation revoked at ARCA shows as not
connected on the next check, and the same reused ticket makes it cost one SOAP call.
"""

from __future__ import annotations

from typing import Any, Protocol

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
    TicketNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    ResultadoDeConexion,
    ResultadoDeVerificacion,
    TicketVigente,
)
from cheatsheet.contexts.integrations.application.ticket import desempaquetar
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_CUIT,
    CLAVE_ETIQUETA,
    EstadoDeConexion,
)
from cheatsheet.platform.soap import (
    ClienteSoap,
    FallaRecibida,
    ServicioSoapNoDisponible,
    raiz,
)

#: The integration row keeps the DER's NOT NULL credential column. With delegation there is
#: no company credential, so it stores this marker — encrypted like any other, and not a
#: secret.
MARCA_DE_DELEGACION = b"delegacion-arca"

#: ValidacionDeToken: the CUIT is not among the relations of the certificate.
CODIGOS_SIN_DELEGACION = frozenset({"600", "601"})

MENSAJE_SIN_DELEGACION = (
    "ARCA no registra que la CUIT {cuit} haya delegado Facturacion Electronica en "
    "CheatSheet. Delegala desde el Administrador de Relaciones de Clave Fiscal y volve a "
    "verificar."
)

_ACCION = "http://ar.gov.afip.dif.FEV1/FECompUltimoAutorizado"
_ESPACIO = "{http://ar.gov.afip.dif.FEV1/}"
_SOBRE = """<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ar="http://ar.gov.afip.dif.FEV1/">
  <soapenv:Body>
    <ar:FECompUltimoAutorizado>
      <ar:Auth>
        <ar:Token>{token}</ar:Token>
        <ar:Sign>{sign}</ar:Sign>
        <ar:Cuit>{cuit}</ar:Cuit>
      </ar:Auth>
      <ar:PtoVta>1</ar:PtoVta>
      <ar:CbteTipo>6</ar:CbteTipo>
    </ar:FECompUltimoAutorizado>
  </soapenv:Body>
</soapenv:Envelope>"""


class PortTicketDePlataforma(Protocol):
    """What the delegation check needs from `ObtenerTicketDePlataforma`."""

    async def ejecutar(self, servicio: ServicioDeArca) -> TicketVigente: ...


class ConsultaDeDelegacion:
    """Asks WSFEv1 whether the platform may speak for a CUIT."""

    def __init__(self, soap: ClienteSoap, tickets: PortTicketDePlataforma | None) -> None:
        self._soap = soap
        self._tickets = tickets

    async def esta_delegada(self, cuit: str) -> bool:
        """Raises `ProveedorNoDisponible` when ARCA could not be asked."""
        if self._tickets is None:
            raise ProveedorNoDisponible("Esta operacion necesita una sesion de base de datos")
        try:
            ticket = await self._tickets.ejecutar(ServicioDeArca.WSFE)
        except TicketNoDisponible as exc:
            raise ProveedorNoDisponible(str(exc)) from exc
        token, sign = desempaquetar(ticket.contenido)
        try:
            texto = await self._soap.enviar(
                _SOBRE.format(token=token, sign=sign, cuit=cuit), accion=_ACCION
            )
        except (FallaRecibida, ServicioSoapNoDisponible) as exc:
            raise ProveedorNoDisponible(f"WSFE no respondio: {exc}") from exc
        return not (_codigos_de_error(texto) & CODIGOS_SIN_DELEGACION)


class ConectorDelegacionArca:
    """Implements `PortConectorDeIntegracion` for ARCA under ADR-0014.

    `material.contenido` is the company's CUIT, and the composition root is what puts it
    there, from `identity`. The request body never decides on whose behalf ARCA is asked.
    """

    def __init__(self, consulta: ConsultaDeDelegacion) -> None:
        self._consulta = consulta

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        cuit = cuit_del_material(material)
        if not await self._consulta.esta_delegada(cuit):
            raise ConexionRechazada(MENSAJE_SIN_DELEGACION.format(cuit=formatear(cuit)))
        return resultado_delegado(cuit)


class VerificadorDelegacionArca:
    """Implements `PortVerificadorDeConexion`: is the delegation still there?"""

    def __init__(self, consulta: ConsultaDeDelegacion) -> None:
        self._consulta = consulta

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion:
        del credencial  # the marker says nothing; the CUIT is what is checked
        cuit = str(parametros.get(CLAVE_CUIT, "")).strip()
        if not cuit:
            return ResultadoDeVerificacion(
                EstadoDeConexion.ATENCION,
                "La integracion con ARCA no tiene CUIT: volve a verificar la delegacion",
            )
        if not await self._consulta.esta_delegada(cuit):
            return ResultadoDeVerificacion(
                EstadoDeConexion.NO_CONECTADO,
                MENSAJE_SIN_DELEGACION.format(cuit=formatear(cuit)),
            )
        return ResultadoDeVerificacion(EstadoDeConexion.CONECTADO, None, _parametros(cuit))


def cuit_del_material(material: MaterialDeConexion) -> str:
    digitos = "".join(c for c in material.contenido.decode("utf-8", errors="ignore") if c.isdigit())
    if len(digitos) != 11:
        raise ConexionRechazada(
            "La empresa no tiene un CUIT valido cargado: completalo en Datos de la empresa"
        )
    return digitos


def resultado_delegado(cuit: str) -> ResultadoDeConexion:
    return ResultadoDeConexion(credencial=MARCA_DE_DELEGACION, parametros=_parametros(cuit))


def formatear(cuit: str) -> str:
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}"


def _parametros(cuit: str) -> dict[str, Any]:
    return {CLAVE_CUIT: cuit, CLAVE_ETIQUETA: f"CUIT {formatear(cuit)} · delegada en CheatSheet"}


def _codigos_de_error(texto: str) -> set[str]:
    """The `<Err><Code>` values of a WSFEv1 answer. Empty when ARCA reported none."""
    try:
        documento = raiz(texto)
    except ServicioSoapNoDisponible as exc:
        raise ProveedorNoDisponible(str(exc)) from exc
    return {
        (codigo.text or "").strip()
        for codigo in documento.iter(f"{_ESPACIO}Code")
        if (codigo.text or "").strip()
    }
