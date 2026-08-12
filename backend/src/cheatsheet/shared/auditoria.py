"""Shared Kernel — the vocabulary of an auditable operation (HS-T5).

**Why this is in `shared/` and not in `observability/domain/`.** The unit plan put
`Modulo`, `Iniciador` and `Resultado` in the audit context's domain. Writing it
proved that wrong in the only way that counts: rule R3 forbids `billing/domain` from
importing `observability/domain`, so with the enums there, *no context could emit an
auditable event without breaking the architecture*. The guard would block the write.

These are cross-context value objects — `Modulo` is literally the list of the twelve
bounded contexts — which is exactly what CLAUDE.md §2 says the Shared Kernel holds.
The aggregate that stores them stays in `observability/domain/`, where it belongs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.tenant import UserId


class Modulo(StrEnum):
    """Which bounded context executed the operation.

    A closed catalogue, not a free string: the audit panel of epic 10 filters by
    module (HU-E12-01), and a filter over free text is a filter that silently misses
    the rows someone spelled differently.
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


class TipoDeIniciador(StrEnum):
    """Who set the operation in motion.

    `AGENTE` exists from day one although the conversational context is epic 8. It
    costs one enum member now and spares a migration over an append-only table later.
    """

    USUARIO = "usuario"
    SISTEMA = "sistema"
    AGENTE = "agente"


@dataclass(frozen=True, slots=True)
class Iniciador:
    """The actor behind an operation, in the three shapes this system has.

    Built through the factories rather than the constructor so the pairing of type and
    reference cannot be got wrong.
    """

    tipo: TipoDeIniciador
    user_id: UserId | None = None
    referencia: str | None = None

    def __post_init__(self) -> None:
        if self.tipo is TipoDeIniciador.USUARIO and self.user_id is None:
            raise EntradaInvalida("Un iniciador de tipo USUARIO requiere user_id")
        if self.tipo is not TipoDeIniciador.USUARIO and not self.referencia:
            raise EntradaInvalida(f"Un iniciador {self.tipo} requiere una referencia")

    @classmethod
    def usuario(cls, user_id: UserId) -> Iniciador:
        return cls(tipo=TipoDeIniciador.USUARIO, user_id=user_id)

    @classmethod
    def sistema(cls, referencia: str) -> Iniciador:
        """`referencia` is the task or scheduler entry, e.g. `despachar_recordatorios`."""
        return cls(tipo=TipoDeIniciador.SISTEMA, referencia=referencia)

    @classmethod
    def agente(cls, referencia: str) -> Iniciador:
        """`referencia` identifies the conversation, never the customer's phone number."""
        return cls(tipo=TipoDeIniciador.AGENTE, referencia=referencia)


@dataclass(frozen=True, slots=True)
class EntidadAfectada:
    """What the operation acted upon: aggregate type plus its identifier."""

    tipo: str
    identificador: str

    def __post_init__(self) -> None:
        if not self.tipo.strip() or not self.identificador.strip():
            raise EntradaInvalida("EntidadAfectada requiere tipo e identificador")


def _congelar(detalle: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(detalle))


@dataclass(frozen=True, kw_only=True)
class EventoAuditable(EventoDeDominio):
    """The event any context publishes when it does something worth remembering.

    Carries exactly the six data points HS-T5 RN-02 demands. `detalle` is for context
    that helps a human reading the log — never personal or tax data (CLAUDE.md §3.6),
    and never a credential.
    """

    modulo: Modulo
    operacion: str
    entidad_afectada: EntidadAfectada
    iniciador: Iniciador
    resultado: Resultado
    detalle: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.operacion.strip():
            raise EntradaInvalida("Un evento auditable requiere una operacion")
        object.__setattr__(self, "detalle", _congelar(self.detalle))
