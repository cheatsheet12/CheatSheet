"""What the aggregate reports back when something worth recording happened.

**Why this is a domain fact and not an `EventoAuditable`.** `identity` builds its audit
events in the application layer (`onboarding.py`, `usuarios.py`, `registro.py`), and this
context follows the same seam. The aggregate knows what changed; only the use case knows
*who* asked and from which address, and an aggregate that took a `usuario_id` and an IP
just to fill an audit row would be carrying the audit trail's vocabulary through the
domain to get there.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion, SistemaExterno


@dataclass(frozen=True, slots=True)
class CambioDeEstado:
    """An integration moved between the states of HU-E2-05 RN-02.

    Produced only on an actual transition — see
    `ConfiguracionDeIntegracion.registrar_verificacion`.
    """

    sistema: SistemaExterno
    anterior: EstadoDeConexion
    nuevo: EstadoDeConexion
    detalle: str | None

    @property
    def descripcion(self) -> str:
        """What the audit row's `accion` reads as."""
        return f"Integracion {self.sistema.value}: {self.anterior.value} → {self.nuevo.value}"
