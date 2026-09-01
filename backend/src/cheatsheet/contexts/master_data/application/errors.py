"""Application-level conditions of the master data context."""

from __future__ import annotations

from uuid import UUID

from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada, OperacionNoPermitida


class PermisoDenegado(OperacionNoPermitida):
    """The role does not allow this. Answered as 403.

    The access matrix of the navigation map §5 gives Datos Maestros to Admin and Operador
    in full and to Solo Lectura read-only. So this is raised when a `SOLO_LECTURA` tries
    to write, and when anybody else tries to read.
    """


class ClienteNoEncontrado(EntradaInvalida):
    """No client with that id in **this** company.

    Deliberately the same error whether the client does not exist at all or belongs to
    another company. The isolation barrier is RLS, so the repository genuinely cannot see
    the difference — and if it could, answering differently would let somebody probe
    which ids exist elsewhere.
    """


class CuitInexistente(EntradaInvalida):
    """ARCA's registry does not know this tax id (HU-E4-01 RN-02).

    **Blocks the save**, which is the whole point of the rule. Its opposite number is
    `PadronNoDisponible` — the registry could not be asked — and that one does not block.
    The two must never collapse into one: a bad afternoon at ARCA would then stop a
    company from loading its own customers.
    """


class ClienteDuplicado(InvarianteViolada):
    """Another client of this company already has this CUIT (RN-03).

    Carries the existing client's id because the acceptance criterion asks for more than
    a message: «ofrece ver el duplicado». Without the id the screen can say *that* there
    is a duplicate and not *which*, which leaves the user to search for it by hand.

    **The id is optional, and the case where it is missing is the interesting one.** The
    duplicate is normally found by looking it up, which is also what produces the id. But
    the check that actually *prevents* the duplicate is the unique index, and it fires in
    the race the lookup cannot win — two tabs saving the same CUIT at once. In that path
    the session is already unusable, so there is no second query to be made and the screen
    shows the message without the link. Rare, correct, and honest about what it knows.
    """

    def __init__(self, mensaje: str, *, cliente_existente_id: UUID | None = None) -> None:
        super().__init__(mensaje)
        self.cliente_existente_id = cliente_existente_id


class ServicioNoEncontrado(EntradaInvalida):
    """No service with that id in **this** company.

    Same shape and same reasoning as `ClienteNoEncontrado`: the isolation barrier is RLS,
    so the repository genuinely cannot tell "does not exist" from "belongs to somebody
    else" — and answering differently would let somebody probe which ids exist elsewhere.
    """


class CategoriaNoEncontrada(EntradaInvalida):
    """No category with that id in **this** company.

    Same shape and reasoning as its two siblings — and here it carries extra weight: it is
    what stops a company from classifying with somebody else's category. A foreign key is
    checked with the table owner's permissions and therefore *sees* rows RLS hides, so the
    barrier is this lookup, which goes through the policy and simply finds nothing.
    """


class CategoriaDuplicada(EntradaInvalida):
    """Another category of this company already has this name in this scope (RN-02).

    Comparison is case-insensitive: «VIP» and «vip» are the same name to anybody reading
    the list.

    **An `EntradaInvalida` — 422 — and not an `InvarianteViolada` like `ClienteDuplicado`,
    and the difference is not cosmetic.** It is the same argument `ConexionRechazada` makes
    in `integrations`: a name already taken and a name that is malformed are the same thing
    to whoever is filling in the form, and both need the message to reach them. The BFF
    forwards `detalle` **only** for `EntradaInvalida` (`app/api/auth/_sesion.ts`), so an
    `InvarianteViolada` arrives at the browser as a bare code — which is right for a
    permission error and wrong for a message the story wrote out in full.

    That policy is also why `ClienteDuplicado` does not reach the screen with its text
    today; see `TODO.md` §10.
    """
