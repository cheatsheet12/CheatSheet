"""`RegistroDeAuditoria` — the aggregate behind HS-T5.

Its shape is the DER's (`docs/aidlc/inputs/der.md`, BC10) plus `modulo` and
`evento_id`; the reason for each addition is in `shared/auditoria.py`.

The rest of this file follows from RN-03: **audit records are immutable**. That is not
a convention to be respected here, it is enforced three times, because it takes only
one of the three to be missing for the guarantee to be a lie:

1. **Here**, as a frozen dataclass with no method that changes anything. There is no
   `marcar_como`, no setter, no `evolucionar`. The type system says no.
2. **In the port** (`application/ports.py`), which offers `agregar` and reads, and
   deliberately does not offer `actualizar` or `eliminar`.
3. **In the database** (migration 0001), where the application role holds `SELECT` and
   `INSERT` on this table and nothing else.

Level 1 is what a developer meets first; level 3 is what holds when someone opens a
`psql` session at three in the morning during an incident.

The aggregate carries no behaviour beyond validating itself. That is not an anaemic
model by accident — an audit record has no lifecycle. It happened, and that is all it
will ever do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cheatsheet.shared.auditoria import (
    Modulo,
    Resultado,
    validar_accion,
    validar_entidad_afectada,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida


@dataclass(frozen=True, slots=True, kw_only=True)
class RegistroDeAuditoria:
    """One line of the log: what happened, to what, by whom, how it ended and when."""

    id: UUID
    #: Identity of the *occurrence* that produced this record. Unique in the table, and
    #: what makes a redelivered event leave one row instead of two (ADR-009).
    evento_id: UUID
    empresa_id: EmpresaId
    #: `None` means the system acted: a scheduled task, a webhook, the agent.
    usuario_id: UsuarioId | None
    modulo: Modulo
    accion: str
    entidad_afectada: str
    resultado: Resultado
    direccion_ip: str | None
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise EntradaInvalida("timestamp debe tener zona horaria (UTC)")
        object.__setattr__(self, "accion", validar_accion(self.accion))
        object.__setattr__(
            self, "entidad_afectada", validar_entidad_afectada(self.entidad_afectada)
        )

    @property
    def fue_exitosa(self) -> bool:
        return self.resultado is Resultado.COMPLETADO

    @property
    def fue_del_sistema(self) -> bool:
        return self.usuario_id is None
