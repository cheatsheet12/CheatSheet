"""The three ports ARCA plugs into, each a thin composition over `firma` and `wsaa`.

They are together in one file because they share one construction — a signer plus a client
— and separating them would mean three modules of ten lines and one of wiring.

**What each one costs is the reason they are three and not one:**

- `ConectorArca` is the only one that talks to WSAA on the Administrator's behalf, and it
  does it exactly once, when the credential is loaded. That single call is what makes
  RN-02 true: the credential is validated *against ARCA* before the integration is marked
  connected.
- `VerificadorArca` **never** calls WSAA. The certificate carries its own expiry, so the
  live check of HU-E2-05 reads it locally: refreshing the screen costs nothing and, more
  to the point, does not burn a ticket that ARCA will refuse to reissue for twelve hours.
- `EmisorArcaDeTickets` mints a ticket when one is actually needed — at connection time and
  at renewal — and nowhere else.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    ResultadoDeConexion,
    ResultadoDeVerificacion,
    TicketEmitido,
)
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import CLAVE_ETIQUETA, EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.arca import firma
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import (
    CLAVE_CUIT,
    CLAVE_TITULAR,
    CLAVE_VENCIMIENTO,
    YaAutenticado,
    estado_por_vencimiento,
)
from cheatsheet.contexts.integrations.infrastructure.arca.wsaa import ClienteWsaa
from cheatsheet.shared.clock import Reloj

#: The service a connection is validated against. WSFE rather than the padrón because it
#: is the one epic 5 depends on, so a credential that validates here is a credential that
#: can invoice.
SERVICIO_DE_VALIDACION = ServicioDeArca.WSFE


def parametros_de_la_credencial(credencial: firma.CredencialFiscal) -> dict[str, Any]:
    """What the card shows about a fiscal credential.

    The CUIT and the expiry date, and no part of the credential itself. `etiqueta` is the
    generic slot the domain declares, so the screen renders it without knowing what ARCA
    is.
    """
    vence = credencial.vence_en.date().isoformat()
    etiqueta = f"CUIT {credencial.cuit}" if credencial.cuit else credencial.titular
    valores: dict[str, Any] = {
        CLAVE_CUIT: credencial.cuit,
        CLAVE_TITULAR: credencial.titular,
        CLAVE_VENCIMIENTO: credencial.vence_en.isoformat(),
    }
    if etiqueta:
        valores[CLAVE_ETIQUETA] = f"{etiqueta} · vence {vence}"
    return valores


class EmisorArcaDeTickets:
    """Implements `PortEmisorDeTickets`."""

    def __init__(self, cliente: ClienteWsaa, reloj: Reloj) -> None:
        self._cliente = cliente
        self._reloj = reloj

    async def emitir(self, credencial: bytes, servicio: ServicioDeArca) -> TicketEmitido:
        fiscal = firma.leer_credencial(credencial)
        ahora = self._reloj.ahora()
        firma.exigir_vigente(fiscal, ahora)
        solicitud = firma.armar_solicitud(servicio, ahora)
        ticket = await self._cliente.login(firma.firmar(solicitud, fiscal))
        # The token and the sign travel together because every later call needs both, and
        # a pair split across two columns is a pair that eventually disagrees.
        return TicketEmitido(
            servicio=servicio,
            contenido=f"{ticket.token}\n{ticket.sign}".encode(),
            expira_en=ticket.expira_en,
        )


class ConectorArca:
    """Implements `PortConectorDeIntegracion`.

    The order is RN-02's: everything checkable locally is checked first — the bundle
    parses, the key matches the certificate, the certificate has not expired — and only
    then does anything reach ARCA. Each of those would otherwise come back as a generic
    CMS fault that reads like "your certificate is not authorised", sending the
    Administrator to ask ARCA about a problem on this side.
    """

    def __init__(self, emisor: EmisorArcaDeTickets, reloj: Reloj) -> None:
        self._emisor = emisor
        self._reloj = reloj

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        fiscal = firma.leer_credencial(material.contenido)
        firma.exigir_vigente(fiscal, self._reloj.ahora())

        try:
            ticket = await self._emisor.emitir(material.contenido, SERVICIO_DE_VALIDACION)
        except YaAutenticado:
            # ARCA confirming the credential works while declining to hand over a second
            # ticket. The connection is valid; there is simply nothing new to store, and
            # the next renewal picks up once the live one expires.
            return ResultadoDeConexion(
                credencial=material.contenido, parametros=parametros_de_la_credencial(fiscal)
            )
        return ResultadoDeConexion(
            credencial=material.contenido,
            parametros=parametros_de_la_credencial(fiscal),
            tickets=(ticket,),
        )


class VerificadorArca:
    """Implements `PortVerificadorDeConexion`. **Opens no socket.**

    Decision D-e: a ticket lasts twelve hours and ARCA refuses to mint a second one while
    the first is alive, so a live check that called WSAA would break the very next live
    check. The certificate's `notAfter` answers the question that matters — is this
    credential still usable — and answers it for free.

    What this deliberately does not catch is a certificate revoked before its expiry date.
    That surfaces at the next renewal, which is the first moment it actually matters.
    """

    def __init__(self, reloj: Reloj, aviso: timedelta) -> None:
        self._reloj = reloj
        self._aviso = aviso

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion:
        del parametros  # everything needed is inside the certificate itself
        try:
            fiscal = firma.leer_credencial(credencial)
        except ConexionRechazada as exc:
            # A stored credential that no longer parses is a data problem, not an outage,
            # and not a rejection by ARCA either — nothing was asked. `ATENCION` says so on
            # the card instead of failing a scheduled task with an exception nobody reads.
            return ResultadoDeVerificacion(
                EstadoDeConexion.ATENCION, f"No se pudo leer la credencial guardada: {exc}"
            )
        estado, detalle = estado_por_vencimiento(fiscal.vence_en, self._reloj.ahora(), self._aviso)
        return ResultadoDeVerificacion(estado, detalle, parametros_de_la_credencial(fiscal))
