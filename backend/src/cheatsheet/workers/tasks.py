"""The reference task.

One task exists so the queue infrastructure is verifiable rather than merely present:
it proves routing, idempotency and the audit trail line up end to end. It does no
business work, and it is deleted by whichever unit adds the first real task
(HU-E3-03, epic 4).

It also fixes the shape every later task follows: take primitives, claim the
idempotency key, do the work, publish what happened — with `usuario_id` left as `None`,
because a scheduled task has no user behind it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from cheatsheet.workers.base import EjecutorIdempotente
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE = "observability.registrar_latido"


async def registrar_latido(
    recursos: Recursos, empresa_id: EmpresaId, referencia: str
) -> UUID | None:
    """Write one audit entry from a task context. Returns None if already done."""
    clave = ClaveDeIdempotencia.de(
        empresa_id=empresa_id, tipo=NOMBRE, payload={"referencia": referencia}
    )
    ejecutor = EjecutorIdempotente(recursos.idempotencia())

    async def efecto() -> UUID:
        evento_id = uuid4()
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            await unidad.publicador.publicar(
                EventoAuditable(
                    evento_id=evento_id,
                    empresa_id=empresa_id,
                    ocurrido_en=unidad.reloj.ahora(),
                    modulo=Modulo.OBSERVABILITY,
                    accion="registrar_latido",
                    entidad_afectada=f"Worker:{referencia}",
                    resultado=Resultado.COMPLETADO,
                    # No usuario_id: nobody asked for this, the scheduler did.
                )
            )
        return evento_id

    return await ejecutor.ejecutar(clave, efecto)


def registrar_latido_sync(settings: Settings, empresa_id: str, referencia: str) -> Any:
    """Celery's bridge into the async world.

    Celery tasks are synchronous; everything below them is not. One event loop per task
    execution, **and one set of resources inside it** — see `workers/ejecucion.py` for the
    defect that taught us the second half.
    """
    return ejecutar_tarea(
        settings,
        lambda recursos: registrar_latido(recursos, EmpresaId(UUID(empresa_id)), referencia),
    )
