"""What another context may ask about the company itself.

`billing` needs one fact to issue a document: **the company's own VAT condition**, because
that plus the receptor's decides which types are legal (HU-E5-03 RN-01, decision D16). It
cannot read `empresa` directly — rule R3 — so this is what it reads instead.

Published as an application service rather than by handing out the aggregate, which is the
same rule ADR-0003 sets for `integrations`: a consumer gets the answer to its question, not
the row. `Empresa` carries an email, a responsible person's name and an onboarding state
that `billing` has no business seeing, and a DTO is what keeps it that way.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.contexts.identity.application.ports import PortRepositorioEmpresa
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CondicionIVA


@dataclass(frozen=True, slots=True)
class DatosFiscalesDeEmpresa:
    """The issuer, as anyone outside `identity` sees it."""

    razon_social: str | None
    cuit: str | None
    #: `None` until the onboarding is finished. Consumers must not invent one: which kind
    #: of document may be issued depends on it, and guessing would guess a legal fact.
    condicion_iva: CondicionIVA | None


class ConsultarDatosFiscales:
    """The company's own fiscal data, for whoever has to invoice on its behalf.

    **No role is checked**, for the same reason `ObtenerTicketDeAcceso` checks none: the
    caller is another context acting for the company whose session is already open, and
    whoever asked *it* is where authorisation belongs.
    """

    def __init__(self, empresas: PortRepositorioEmpresa) -> None:
        self._empresas = empresas

    async def ejecutar(self, *, empresa_id: EmpresaId) -> DatosFiscalesDeEmpresa:
        empresa = await self._empresas.buscar_por_id(empresa_id)
        if empresa is None:  # pragma: no cover - the session was opened for it
            raise EntradaInvalida("La empresa no existe")
        return DatosFiscalesDeEmpresa(
            razon_social=empresa.razon_social,
            cuit=empresa.cuit.valor if empresa.cuit else None,
            condicion_iva=empresa.condicion_iva,
        )


__all__ = ["ConsultarDatosFiscales", "DatosFiscalesDeEmpresa"]
