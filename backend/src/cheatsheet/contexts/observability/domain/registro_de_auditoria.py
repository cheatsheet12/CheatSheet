"""`RegistroDeAuditoria` — the aggregate behind HS-T5.

The whole design of this file follows from RN-03: **audit records are immutable**.
Immutability is not a convention to be respected here; it is enforced three times,
because it only takes one of the three to be missing for the guarantee to be a lie:

1. **Here**, as a frozen dataclass with no method that changes anything. There is no
   `marcar_como`, no setter, no `evolucionar`. The type system says no.
2. **In the port** (`application/ports.py`), which offers `agregar` and reads, and
   deliberately does not offer `actualizar` or `eliminar`.
3. **In the database** (migration 0001), where the application role holds `SELECT`
   and `INSERT` on this table and nothing else.

Level 1 is what a developer meets first; level 3 is what holds when someone writes
raw SQL at three in the morning during an incident.

The aggregate carries no behaviour beyond validating itself. That is not an anaemic
model by accident — an audit record has no lifecycle. It happened, and that is all it
will ever do.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from cheatsheet.shared.auditoria import EntidadAfectada, Iniciador, Modulo, Resultado
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.tenant import TenantId

LARGO_MAXIMO_OPERACION = 120


@dataclass(frozen=True, slots=True, kw_only=True)
class RegistroDeAuditoria:
    """One line of the log: what happened, to what, by whom, how it ended and when."""

    id: UUID
    #: Identity of the *occurrence* that produced this record. Unique in the table, and
    #: what makes a redelivered event leave one row instead of two (ADR-009).
    evento_id: UUID
    tenant_id: TenantId
    modulo: Modulo
    operacion: str
    entidad_afectada: EntidadAfectada
    iniciador: Iniciador
    resultado: Resultado
    ocurrido_en: datetime
    detalle: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        operacion = self.operacion.strip()
        if not operacion:
            raise EntradaInvalida("Un registro de auditoria requiere una operacion")
        if len(operacion) > LARGO_MAXIMO_OPERACION:
            raise EntradaInvalida(
                f"La operacion excede {LARGO_MAXIMO_OPERACION} caracteres: {operacion[:40]}…"
            )
        if self.ocurrido_en.tzinfo is None:
            raise EntradaInvalida("ocurrido_en debe tener zona horaria (UTC)")
        object.__setattr__(self, "operacion", operacion)
        # A frozen dataclass still hands out the *same* dict it was given, which the
        # caller can then mutate. Copying it behind a read-only view closes that door.
        object.__setattr__(self, "detalle", MappingProxyType(dict(self.detalle)))

    @property
    def fue_exitosa(self) -> bool:
        return self.resultado is Resultado.COMPLETADO
