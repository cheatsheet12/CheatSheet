"""`ConsultarPadron` — the second operation this context publishes for other contexts.

`ObtenerTicketDeAcceso` (ADR-0004) hands out a ticket and lets the caller do the talking.
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

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ConsultaDePadronNoDisponible,
    ProveedorNoDisponible,
    TicketNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import (
    DatosDePadron,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
)
from cheatsheet.contexts.integrations.application.tickets import ObtenerTicketDeAcceso
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.shared.empresa import EmpresaId


class ConsultarPadron:
    """Look one tax id up in ARCA's registry, on behalf of one company."""

    def __init__(
        self,
        *,
        tickets: ObtenerTicketDeAcceso,
        integraciones: PortRepositorioIntegraciones,
        adaptadores: PortRegistroDeAdaptadores,
    ) -> None:
        self._tickets = tickets
        self._integraciones = integraciones
        self._adaptadores = adaptadores

    async def ejecutar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosDePadron | None:
        """Raises `ConsultaDePadronNoDisponible` when the registry could not be asked.

        **No role is checked**, for the same reason `ObtenerTicketDeAcceso` checks none:
        the caller is another context acting for a company that already authorised the
        integration, and whoever asked *it* is where authorisation belongs.
        """
        adaptador = self._adaptadores.consulta_de_padron(SistemaExterno.ARCA)
        if adaptador is None:  # pragma: no cover — the registry always registers one
            raise ConsultaDePadronNoDisponible("No hay consulta de padron registrada para ARCA")

        configuracion = await self._integraciones.buscar(empresa_id, SistemaExterno.ARCA)
        if configuracion is None:
            # The ordinary case straight out of the onboarding, not an anomaly: the
            # company simply has not loaded its certificate yet.
            raise ConsultaDePadronNoDisponible(
                "La empresa no tiene conectada la integracion con ARCA"
            )

        try:
            ticket = await self._tickets.ejecutar(
                empresa_id=empresa_id, servicio=ServicioDeArca.PADRON_A5
            )
            return await adaptador.consultar(
                ticket=ticket.contenido, parametros=configuracion.parametros, cuit=cuit
            )
        except ConsultaDePadronNoDisponible:
            raise
        except (TicketNoDisponible, ProveedorNoDisponible, ConexionRechazada) as exc:
            # `ConexionRechazada` included on purpose. Against a *credential* it means the
            # Administrator loaded something wrong; against a *lookup* it means ARCA
            # refused this request — which says nothing about the tax id being asked
            # about, so it must not come back as "that CUIT does not exist".
            raise ConsultaDePadronNoDisponible(f"No se pudo consultar el padron: {exc}") from exc
