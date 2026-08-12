"""The reference task.

One task exists so the queue infrastructure is verifiable rather than merely present:
it proves routing, idempotency and the audit trail line up end to end. It does no
business work, and it is deleted by whichever unit adds the first real task
(HU-E3-03, epic 4).

It also fixes the shape every later task follows: take primitives, rebuild the value
objects, claim the idempotency key, do the work, publish what happened.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import (
    EntidadAfectada,
    EventoAuditable,
    Iniciador,
    Modulo,
    Resultado,
)
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from cheatsheet.shared.tenant import TenantId
from cheatsheet.workers.base import EjecutorIdempotente

logger = obtener_logger(__name__)

NOMBRE = "observability.registrar_latido"


async def registrar_latido(recursos: Recursos, tenant_id: TenantId, referencia: str) -> UUID | None:
    """Write one audit entry from a task context. Returns None if already done."""
    clave = ClaveDeIdempotencia.de(
        tenant_id=tenant_id, tipo=NOMBRE, payload={"referencia": referencia}
    )
    ejecutor = EjecutorIdempotente(recursos.idempotencia())

    async def efecto() -> UUID:
        evento_id = uuid4()
        async for unidad in unidad_de_trabajo(recursos, tenant_id):
            await unidad.publicador.publicar(
                EventoAuditable(
                    evento_id=evento_id,
                    tenant_id=tenant_id,
                    ocurrido_en=unidad.reloj.ahora(),
                    modulo=Modulo.OBSERVABILITY,
                    operacion="registrar_latido",
                    entidad_afectada=EntidadAfectada(tipo="Worker", identificador=referencia),
                    iniciador=Iniciador.sistema(NOMBRE),
                    resultado=Resultado.COMPLETADO,
                )
            )
        return evento_id

    return await ejecutor.ejecutar(clave, efecto)


def registrar_latido_sync(recursos: Recursos, tenant_id: str, referencia: str) -> Any:
    """Celery's bridge into the async world.

    Celery tasks are synchronous; everything below them is not. One event loop per
    task execution is the simple, correct answer at this volume.
    """
    return asyncio.run(registrar_latido(recursos, TenantId(UUID(tenant_id)), referencia))
