"""Anti-corruption layer over `identity`: who is issuing, in `billing`'s vocabulary.

The shape ADR-0003 asks for and that `master_data` and `identity` already use over the
padrón: the publishing context offers one contract and knows none of its consumers; each
consumer translates it into its own terms and decides what an absent value means here.

**What this layer decides is the meaning of `None`.** `identity` may legitimately not know
the company's VAT condition — the onboarding is unfinished. For invoicing that is not a
missing field, it is a hard stop: which type of document is legal depends on it, and
guessing would guess a legal fact.
"""

from __future__ import annotations

from cheatsheet.contexts.identity.application.empresa import ConsultarDatosFiscales
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CondicionIVA

#: Shown on PAN-FAC-03, so it says what to do rather than what is missing.
MENSAJE_SIN_CONDICION_EMISOR = (
    "Tu empresa todavía no tiene una condición de IVA cargada. Completá los datos fiscales "
    "antes de emitir comprobantes."
)


class EmisorViaIdentity:
    """`PortDatosDelEmisor`, backed by `identity`'s published operation."""

    def __init__(self, consulta: ConsultarDatosFiscales) -> None:
        self._consulta = consulta

    async def condicion_iva(self, *, empresa_id: EmpresaId) -> CondicionIVA:
        datos = await self._consulta.ejecutar(empresa_id=empresa_id)
        if datos.condicion_iva is None:
            raise EntradaInvalida(MENSAJE_SIN_CONDICION_EMISOR)
        return datos.condicion_iva


__all__ = ["MENSAJE_SIN_CONDICION_EMISOR", "EmisorViaIdentity"]
