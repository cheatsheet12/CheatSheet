"""Shared Kernel — the vocabulary of an auditable operation (HS-T5).

**Why this is in `shared/` and not in `observability/domain/`.** Rule R3 forbids
`billing/domain` from importing `observability/domain`, so with these types there,
*no context could emit an auditable event without breaking the architecture* — the
guard would block the write. They are cross-context value objects, which is exactly
what CLAUDE.md §2 says the Shared Kernel holds. The aggregate that stores them stays
in `observability/domain/`.

**The shape follows the DER** (`docs/aidlc/inputs/der.md`, BC10): `usuario_id`
nullable, `accion`, `entidad_afectada` as a single string, `direccion_ip`. Two fields
sit on top of it, each because a rule demands it and neither on taste:

- **`modulo`** — HS-T5 RN-02 lists it among the six data points the log must capture,
  and HU-E12-01 filters the audit panel by it. The DER has no such column; the conflict
  is recorded as gap H2 in `der.md`.
- **`evento_id`** (inherited from `EventoDeDominio`) — ADR-009. Delivery is
  at-least-once, so without an identity for the *occurrence*, a retried task writes the
  row twice and the log stops being a count of what happened.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from cheatsheet.shared.empresa import UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import EventoDeDominio


class Modulo(StrEnum):
    """Which bounded context executed the operation.

    A closed catalogue, not a free string: the audit panel of epic 10 filters by module
    (HU-E12-01), and a filter over free text silently misses the rows somebody spelled
    differently.
    """

    IDENTITY = "identity"
    MASTER_DATA = "master_data"
    BUSINESS_CONFIG = "business_config"
    INTEGRATIONS = "integrations"
    SPREADSHEET_SYNC = "spreadsheet_sync"
    BILLING = "billing"
    PAYMENTS = "payments"
    SCHEDULING = "scheduling"
    CONVERSATIONAL = "conversational"
    OBSERVABILITY = "observability"
    REPORTING = "reporting"
    REFERENCE_DATA = "reference_data"


class Resultado(StrEnum):
    """HS-T5 RN-04: the outcome is a column, never the condition for writing the row."""

    COMPLETADO = "completado"
    ERROR = "error"


class Iniciador(StrEnum):
    """Who set the operation in motion (HS-T5 RN-02, HS-T2 RN-05).

    The DER has no such column, exactly as it has no `modulo` — gap H2, already resolved once
    in migration 0001 by adding the column the rule requires. This is the same resolution for
    the other half of the same sentence: the rule lists «iniciador» among what the record
    captures, and epic 10's panel filters by it (HU-E12-01).

    `usuario_id is None` was enough while «not a person» meant one thing. Epic 8 makes it mean
    two very different things — a Beat sweep and **an LLM acting on a stranger's message** —
    and the first question anyone asks after an odd conversation is which of the two it was.
    """

    USUARIO = "usuario"
    SISTEMA = "sistema"
    IA = "ia"


LARGO_MAXIMO_ACCION = 120
LARGO_MAXIMO_ENTIDAD = 200


def validar_accion(accion: str) -> str:
    """Shared by the event and the aggregate, so the two cannot drift apart."""
    limpia = accion.strip()
    if not limpia:
        raise EntradaInvalida("Una operacion auditable requiere una accion")
    if len(limpia) > LARGO_MAXIMO_ACCION:
        raise EntradaInvalida(f"La accion excede {LARGO_MAXIMO_ACCION} caracteres: {limpia[:40]}…")
    return limpia


def validar_entidad_afectada(entidad: str) -> str:
    limpia = entidad.strip()
    if not limpia:
        raise EntradaInvalida("Una operacion auditable requiere la entidad afectada")
    if len(limpia) > LARGO_MAXIMO_ENTIDAD:
        raise EntradaInvalida(f"La entidad afectada excede {LARGO_MAXIMO_ENTIDAD} caracteres")
    return limpia


@dataclass(frozen=True, kw_only=True)
class EventoAuditable(EventoDeDominio):
    """The event any context publishes when it does something worth remembering.

    `usuario_id` being `None` is not missing data — it is the statement that **the
    system** acted: a Beat schedule, an inbound webhook, the conversational agent. The
    DER models it exactly that way, with a nullable FK, and so does this.
    """

    modulo: Modulo
    accion: str
    entidad_afectada: str
    resultado: Resultado
    usuario_id: UsuarioId | None = None
    #: Origin of the request. Personal data under most readings, so it stays inside the
    #: audit trail and never leaves it — in particular it is never sent to an LLM
    #: (CLAUDE.md §3.6).
    direccion_ip: str | None = None
    #: Who set this in motion. Left `None`, it is derived from `usuario_id`, so every call
    #: site written before epic 8 keeps meaning exactly what it meant; only the agent has to
    #: say so explicitly.
    iniciador: Iniciador | None = None
    #: What the operation is worth remembering beyond its outcome: the input that triggered
    #: it, and what an external service answered (HU-E12-02 RN-01 and RN-02).
    #:
    #: Optional, and **empty for almost every emitter**. An operation that has nothing to add
    #: says nothing, and the detail screen says "no se registró" instead of inventing a
    #: timeline. The one populated case today is a document authorised by ARCA, because RN-02
    #: names it: CAE, número and status.
    #:
    #: **Never personal data and never a secret** (`CLAUDE.md` §3.2 and §3.6). What goes here
    #: is read by whoever opens the audit panel, and it is stored forever in a table nobody
    #: can update or delete.
    detalle: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        validar_accion(self.accion)
        validar_entidad_afectada(self.entidad_afectada)

    @property
    def fue_del_sistema(self) -> bool:
        return self.usuario_id is None

    @property
    def quien_inicio(self) -> Iniciador:
        """The initiator, derived when it was not stated.

        A derived default rather than a required field: making it mandatory would have meant
        touching every call site in seven epics to say something the code already implied,
        and each of those edits is a chance to say the wrong thing.
        """
        if self.iniciador is not None:
            return self.iniciador
        return Iniciador.SISTEMA if self.usuario_id is None else Iniciador.USUARIO
