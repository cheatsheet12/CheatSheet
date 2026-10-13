"""`ConsultarPadron` — the second operation this context publishes for other contexts.

`ObtenerTicketDePlataforma` (ADR-0014) hands out a ticket and lets the caller do the talking.
That is right for `billing`, which will speak WSFE at length. It would be wrong here: the
padrón is one request, and letting `identity` build it would put ARCA's two hosts, its
retry policy and its XML in a context whose job is companies and users.

So this asks the registry and answers in the vocabulary of the Shared Kernel. What
`identity` receives is a name and a `CondicionIVA` — never a ticket, never a credential,
which is ADR-0003 point 3 applied one level further out.

**The one distinction everything rests on**: `None` means ARCA does not know that tax id,
and it blocks the Administrator. An exception means ARCA could not be asked, and it must
not. Collapsing the two would turn a bad afternoon at ARCA into a company unable to save
its own fiscal data.
"""

from __future__ import annotations

from typing import Protocol

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ConsultaDePadronNoDisponible,
    ProveedorNoDisponible,
    TicketNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import (
    DatosDePadron,
    PortRegistroDeAdaptadores,
    TicketVigente,
)
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import CLAVE_CUIT, SistemaExterno
from cheatsheet.shared.empresa import EmpresaId


class PortTicketDePadron(Protocol):
    """What the lookup needs from `ObtenerTicketDePlataforma` (ADR-0014)."""

    async def ejecutar(self, servicio: ServicioDeArca) -> TicketVigente: ...


class ConsultarPadron:
    """Look one tax id up in ARCA's registry, on behalf of one company.

    **With delegation (ADR-0014) the company does not need to have connected ARCA**: the
    registry is asked with the platform certificate, as the platform. That is what lets
    step 2 of the onboarding validate a CUIT before anything else is configured.
    """

    def __init__(
        self,
        *,
        tickets: PortTicketDePadron,
        adaptadores: PortRegistroDeAdaptadores,
        cuit_de_plataforma: str,
    ) -> None:
        self._tickets = tickets
        self._adaptadores = adaptadores
        self._cuit_de_plataforma = cuit_de_plataforma

    async def ejecutar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosDePadron | None:
        """Raises `ConsultaDePadronNoDisponible` when the registry could not be asked.

        **No role is checked**: the caller is another context acting for a company, and
        whoever asked *it* is where authorisation belongs. `empresa_id` stays in the
        signature because every consumer speaks for one company, even if ARCA no longer
        needs to know which.
        """
        del empresa_id
        adaptador = self._adaptadores.consulta_de_padron(SistemaExterno.ARCA)
        if adaptador is None:  # pragma: no cover — the registry always registers one
            raise ConsultaDePadronNoDisponible("No hay consulta de padron registrada para ARCA")

        try:
            ticket = await self._tickets.ejecutar(ServicioDeArca.PADRON_A5)
            return await adaptador.consultar(
                ticket=ticket.contenido,
                # `cuitRepresentada` is the platform: it asks the registry as itself.
                parametros={CLAVE_CUIT: self._cuit_de_plataforma},
                cuit=cuit,
            )
        except ConsultaDePadronNoDisponible:
            raise
        except (TicketNoDisponible, ProveedorNoDisponible, ConexionRechazada) as exc:
            # `ConexionRechazada` included on purpose: against a *lookup* it means ARCA
            # refused this request — which says nothing about the tax id being asked
            # about, so it must not come back as "that CUIT does not exist".
            raise ConsultaDePadronNoDisponible(f"No se pudo consultar el padron: {exc}") from exc
