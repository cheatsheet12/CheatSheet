"""`EmisorArcaDeTickets`: WSAA, signed with the platform certificate (ADR-0014).

It used to share this file with `ConectorArca` and `VerificadorArca`, the adapters of the
per-company certificate. Delegation replaced them (`delegacion.py`); what is left is the
one piece both models need: a signer plus a WSAA client that turns a certificate into an
access ticket.
"""

from __future__ import annotations

from cheatsheet.contexts.integrations.application.ports import TicketEmitido
from cheatsheet.contexts.integrations.application.ticket import empaquetar
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.infrastructure.arca import firma
from cheatsheet.contexts.integrations.infrastructure.arca.wsaa import ClienteWsaa
from cheatsheet.shared.clock import Reloj


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
        return TicketEmitido(
            servicio=servicio,
            # `empaquetar` and `desempaquetar` are two halves of one format: the padrón and
            # WSFE clients read back what this writes.
            contenido=empaquetar(ticket),
            expira_en=ticket.expira_en,
        )
