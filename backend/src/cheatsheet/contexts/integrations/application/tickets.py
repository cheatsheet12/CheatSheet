"""`ObtenerTicketDeAcceso` — the operation [ADR-0004](../../../../../docs/adr/0004-arca-wsaa-access-tickets.md) publishes.

**This is the seam epic 5 depends on.** `billing` has to call WSFE, calling WSFE needs an
access ticket, and minting one needs the company's private key — which ADR-0003 point 3
keeps inside this context. So `billing` asks here and receives a token, a sign and an
expiry: something usable, never the credential and never the ciphertext. The padrón unit,
which is next, asks the same way with a different service name.

**Reuse is not an optimisation here, it is the rule of the provider.** WSAA refuses to
issue a second ticket while the first is alive, answering `coe.alreadyAuthenticated`. A
caller that minted one per operation would work exactly once and then fail for twelve
hours, so this returns the stored ticket until it approaches expiry.

Together with `ports.py`, `integraciones.py` and `sondeo.py`, this module is the published
contract of the Open Host Service. It imports from no other context.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
    TicketNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import (
    PortCifradoDeCredenciales,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
    PortRepositorioTickets,
    TicketEmitido,
    TicketVigente,
)
from cheatsheet.contexts.integrations.domain.ticket import (
    MARGEN_DE_RENOVACION,
    ServicioDeArca,
    TicketDeAcceso,
)
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId


class ObtenerTicketDeAcceso:
    """Hand out a ticket that ARCA will accept, minting one only when necessary."""

    def __init__(
        self,
        *,
        integraciones: PortRepositorioIntegraciones,
        tickets: PortRepositorioTickets,
        cifrado: PortCifradoDeCredenciales,
        adaptadores: PortRegistroDeAdaptadores,
        reloj: Reloj,
        margen: timedelta = MARGEN_DE_RENOVACION,
    ) -> None:
        self._integraciones = integraciones
        self._tickets = tickets
        self._cifrado = cifrado
        self._adaptadores = adaptadores
        self._reloj = reloj
        self._margen = margen

    async def ejecutar(self, *, empresa_id: EmpresaId, servicio: ServicioDeArca) -> TicketVigente:
        """Raises `TicketNoDisponible` when the company has no usable ARCA credential.

        **No role is checked, and that is deliberate.** This is not a user operation: the
        caller is another context acting on behalf of a company that already authorised
        the integration. Whoever asked *it* to invoice is where authorisation belongs.
        """
        ahora = self._reloj.ahora()
        guardado = await self._tickets.buscar(empresa_id, servicio)
        if guardado is not None and not guardado.hay_que_renovar(ahora, self._margen):
            return self._desde_guardado(servicio, guardado)

        try:
            emitido = await self._emitir(empresa_id, servicio)
        except (ProveedorNoDisponible, ConexionRechazada) as exc:
            # The renewal failed but the stored ticket is still one ARCA accepts. That is
            # the whole reason `vigente` and `hay_que_renovar` are two questions: an outage
            # during renewal must not take down an operation that could have proceeded.
            if guardado is not None and guardado.vigente(ahora):
                return self._desde_guardado(servicio, guardado)
            raise TicketNoDisponible(f"No se pudo obtener un ticket de ARCA: {exc}") from exc

        cifrado = self._cifrado.cifrar(emitido.contenido)
        if guardado is None:
            guardado = TicketDeAcceso(
                id=uuid4(),
                empresa_id=empresa_id,
                servicio=servicio,
                contenido=cifrado,
                expira_en=emitido.expira_en,
            )
            await self._tickets.agregar(guardado)
        else:
            guardado.reemplazar(cifrado, emitido.expira_en)
            await self._tickets.guardar(guardado)
        return TicketVigente(
            servicio=servicio, contenido=emitido.contenido, expira_en=emitido.expira_en
        )

    def _desde_guardado(self, servicio: ServicioDeArca, ticket: TicketDeAcceso) -> TicketVigente:
        """Decrypted here and handed straight out. The ciphertext never leaves."""
        return TicketVigente(
            servicio=servicio,
            contenido=self._cifrado.descifrar(ticket.contenido),
            expira_en=ticket.expira_en,
        )

    async def _emitir(self, empresa_id: EmpresaId, servicio: ServicioDeArca) -> TicketEmitido:
        """Mint a fresh ticket. Raises what the provider raised; the caller decides."""
        emisor = self._adaptadores.emisor_de_tickets(SistemaExterno.ARCA)
        if emisor is None:  # pragma: no cover — the registry always registers one
            raise TicketNoDisponible("No hay emisor de tickets registrado para ARCA")

        configuracion = await self._integraciones.buscar(empresa_id, SistemaExterno.ARCA)
        if configuracion is None:
            raise TicketNoDisponible("La empresa no tiene conectada la integracion con ARCA")
        return await emisor.emitir(self._cifrado.descifrar(configuracion.credencial), servicio)
