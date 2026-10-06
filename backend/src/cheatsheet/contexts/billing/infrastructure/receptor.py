"""Anti-corruption layer over `integrations`: the receptor, in `billing`'s vocabulary.

The third one over the same published operation — `identity` has one for onboarding and
`master_data` one for the client catalogue — and that repetition is the point of ADR-0003,
not a smell: one context publishes one contract and knows none of its consumers, and each
consumer decides what the answer means to *it*.

Here it means something the other two do not care about: **`activo=False` blocks the sale**.
A deregistered CUIT is a real taxpayer that ARCA will not accept as the receptor of a
document, which is a different thing from a CUIT that does not exist — and the use case
says so with a different sentence.
"""

from __future__ import annotations

from cheatsheet.contexts.billing.application.errors import ArcaNoDisponible
from cheatsheet.contexts.billing.application.ports import DatosDelReceptor
from cheatsheet.contexts.integrations.application.errors import ConsultaDePadronNoDisponible
from cheatsheet.contexts.integrations.application.padron import ConsultarPadron
from cheatsheet.shared.empresa import EmpresaId


class ReceptorViaPadron:
    """`PortValidacionDeReceptor`, backed by `integrations`' registry lookup."""

    def __init__(self, consulta: ConsultarPadron) -> None:
        self._consulta = consulta

    async def validar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosDelReceptor | None:
        try:
            datos = await self._consulta.ejecutar(empresa_id=empresa_id, cuit=cuit)
        except ConsultaDePadronNoDisponible as exc:
            # Translated rather than propagated: `billing` answers 503 for "could not ask"
            # and 422 for "that CUIT is no good", and letting the other context's exception
            # through would collapse the two at the router.
            raise ArcaNoDisponible(f"No se pudo consultar el padron de ARCA: {exc}") from exc

        if datos is None:
            # «No se encontró el CUIT en el padrón de ARCA.» The use case writes the
            # sentence; this layer only reports the fact.
            return None
        return DatosDelReceptor(
            cuit=datos.cuit,
            razon_social=datos.razon_social,
            condicion_iva=datos.condicion_iva,
            activo=datos.activo,
        )


__all__ = ["ReceptorViaPadron"]
