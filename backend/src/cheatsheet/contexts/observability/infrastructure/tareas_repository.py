"""PostgreSQL adapter for `PortRepositorioTareaAsincrona`.

Same two conventions as `repository.py` next door, for the same two reasons:

- the mapping between row and aggregate is written by hand in both directions, so the
  domain never acquires a framework dependency (rule R1);
- `empresa_id` never appears in a `WHERE` clause, because Row-Level Security already
  scopes every statement to `app.current_empresa` and a second copy of that rule in
  application code is a copy that can drift from the policy.

One difference worth naming: this repository **updates**. The aggregate is mutable and
already loaded into the session's identity map, so `actualizar` flushes rather than
merges — re-attaching a detached copy would silently resurrect stale state from before
another worker's attempt.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.observability.domain.tarea_asincrona import EstadoTarea, TareaAsincrona
from cheatsheet.contexts.observability.infrastructure.models import TareaAsincronaORM
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia


def _a_dominio(fila: TareaAsincronaORM) -> TareaAsincrona:
    return TareaAsincrona(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        tipo=fila.tipo,
        payload=dict(fila.payload or {}),
        clave_idempotencia=ClaveDeIdempotencia(fila.clave_idempotencia),
        estado=EstadoTarea(fila.estado),
        intentos=fila.intentos,
        resultado=fila.resultado,
        created_at=fila.created_at,
        updated_at=fila.updated_at,
    )


class RepositorioTareaAsincrona:
    """Async task persistence backed by PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, tarea: TareaAsincrona) -> None:
        self._sesion.add(
            TareaAsincronaORM(
                id=tarea.id,
                empresa_id=tarea.empresa_id,
                tipo=tarea.tipo,
                payload=dict(tarea.payload),
                estado=tarea.estado.value,
                intentos=tarea.intentos,
                clave_idempotencia=tarea.clave_idempotencia.valor,
                resultado=tarea.resultado,
                created_at=tarea.created_at,
                updated_at=tarea.updated_at,
            )
        )
        await self._sesion.flush()

    async def actualizar(self, tarea: TareaAsincrona) -> None:
        fila = await self._sesion.get(TareaAsincronaORM, tarea.id)
        if fila is None:
            # Not an assertion about programmer error: RLS makes a row from another
            # company invisible, so this is also what a cross-company id looks like.
            raise LookupError(f"La tarea {tarea.id} no existe para esta empresa")
        fila.estado = tarea.estado.value
        fila.intentos = tarea.intentos
        fila.resultado = tarea.resultado
        fila.updated_at = tarea.updated_at
        await self._sesion.flush()

    async def buscar_por_id(self, tarea_id: UUID) -> TareaAsincrona | None:
        fila = await self._sesion.get(TareaAsincronaORM, tarea_id)
        return _a_dominio(fila) if fila is not None else None

    async def buscar_por_clave(self, clave: ClaveDeIdempotencia) -> TareaAsincrona | None:
        sentencia = select(TareaAsincronaORM).where(
            TareaAsincronaORM.clave_idempotencia == clave.valor
        )
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return _a_dominio(fila) if fila is not None else None

    async def listar_fallidas(self, *, limite: int) -> list[TareaAsincrona]:
        sentencia = (
            select(TareaAsincronaORM)
            .where(TareaAsincronaORM.estado == EstadoTarea.FALLIDA.value)
            .order_by(TareaAsincronaORM.created_at)
            .limit(limite)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]


async def empresas_con_tareas_fallidas(sesion: AsyncSession) -> list[EmpresaId]:
    """Which companies have something sitting in `FALLIDA`, for the Beat sweep.

    The one cross-company read of this context, and the same shape as the three that
    `integrations` already has: it goes through a `SECURITY DEFINER` function that returns
    ids and nothing else, and the per-company task it feeds opens an ordinary session where
    Row-Level Security applies normally.

    The session handed in here must be one **without** a company (`sesion_sin_empresa`):
    with one set, the policy would scope the function's caller to a single tenant and the
    sweep would quietly only ever retire that company's tasks.
    """
    filas = await sesion.execute(text("SELECT empresa_id FROM empresas_con_tareas_fallidas()"))
    return [EmpresaId(fila[0]) for fila in filas]
