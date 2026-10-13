"""`ObtenerTicketDePlataforma` — the access ticket of the platform certificate (ADR-0014).

With web service delegation CheatSheet reaches ARCA through **one** certificate, acting for
every company that delegated to it. WSAA issues one ticket per certificate and service and
refuses a second while the first is alive, so the ticket belongs to the platform: one per
service, shared by every company, kept in a row that is locked while it is renewed and
committed apart from the request that renewed it.

The rules are ADR-0004's: reuse until close to expiry, fall back
to the stored one when renewing fails, and never hand out the ciphertext.
"""

from __future__ import annotations

from datetime import timedelta

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
    TicketNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import (
    PortCifradoDeCredenciales,
    PortEmisorDeTickets,
    PortRepositorioTicketsDePlataforma,
    ReservaDeTicket,
    TicketVigente,
)
from cheatsheet.contexts.integrations.domain.ticket import (
    MARGEN_DE_RENOVACION,
    ServicioDeArca,
    TicketDePlataforma,
)
from cheatsheet.shared.clock import Reloj


class ObtenerTicketDePlataforma:
    """Hand out a ticket of the platform certificate, minting one only when necessary."""

    def __init__(
        self,
        *,
        tickets: PortRepositorioTicketsDePlataforma,
        cifrado: PortCifradoDeCredenciales,
        emisor: PortEmisorDeTickets,
        credencial: bytes,
        reloj: Reloj,
        margen: timedelta = MARGEN_DE_RENOVACION,
    ) -> None:
        self._tickets = tickets
        self._cifrado = cifrado
        self._emisor = emisor
        self._credencial = credencial
        self._reloj = reloj
        self._margen = margen

    async def ejecutar(self, servicio: ServicioDeArca) -> TicketVigente:
        """Raises `TicketNoDisponible` when no ticket ARCA would accept can be produced.

        The whole read-mint-save runs inside the repository's reservation, which commits on
        its own: a ticket WSAA handed out survives whatever the caller does next.
        """
        async with self._tickets.reservar(servicio) as reserva:
            return await self._dentro_de_la_reserva(servicio, reserva)

    async def _dentro_de_la_reserva(
        self, servicio: ServicioDeArca, reserva: ReservaDeTicket
    ) -> TicketVigente:
        ahora = self._reloj.ahora()
        guardado = reserva.guardado
        if guardado is not None and not guardado.hay_que_renovar(ahora, self._margen):
            return self._desde_guardado(guardado)

        try:
            emitido = await self._emisor.emitir(self._credencial, servicio)
        except (ProveedorNoDisponible, ConexionRechazada) as exc:
            # Includes `TicketTodaviaVigente`: ARCA holds one we may still have. If the
            # stored one is valid it is the answer; if not, it resolves when it expires.
            if guardado is not None and guardado.vigente(ahora):
                return self._desde_guardado(guardado)
            raise TicketNoDisponible(f"No se pudo obtener un ticket de ARCA: {exc}") from exc

        cifrado = self._cifrado.cifrar(emitido.contenido)
        if guardado is None:
            guardado = TicketDePlataforma(
                servicio=servicio, contenido=cifrado, expira_en=emitido.expira_en
            )
        else:
            guardado.reemplazar(cifrado, emitido.expira_en)
        await reserva.guardar(guardado)
        return TicketVigente(
            servicio=servicio, contenido=emitido.contenido, expira_en=emitido.expira_en
        )

    def _desde_guardado(self, ticket: TicketDePlataforma) -> TicketVigente:
        return TicketVigente(
            servicio=ticket.servicio,
            contenido=self._cifrado.descifrar(ticket.contenido),
            expira_en=ticket.expira_en,
        )
