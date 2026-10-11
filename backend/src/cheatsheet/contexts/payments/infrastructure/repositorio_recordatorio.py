"""Los recordatorios de cobro, sobre PostgreSQL.

Salió de `repositories.py`, que con las dos operaciones del reintento (U7) pasaba el tope de 400
líneas (`CLAUDE.md` §5).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.payments.application.errors import RecordatorioDuplicado
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.contexts.payments.infrastructure.models import RecordatorioORM


class RepositorioRecordatoriosPostgres:
    """Recordatorios, sobre PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, recordatorio: Recordatorio) -> None:
        # **El `flush` va en su propio savepoint** (U5, H1b). En PostgreSQL un `IntegrityError`
        # aborta la transacción entera: sin el savepoint, atrapar el duplicado dejaba la sesión
        # inservible y el «no es un error, seguí» del barrido tiraba a todos los cobros que
        # venían después. Con él, sólo se deshace este `INSERT`.
        try:
            async with self._sesion.begin_nested():
                self._sesion.add(
                    RecordatorioORM(
                        id=recordatorio.id,
                        cobro_id=recordatorio.cobro_id,
                        paso=recordatorio.paso,
                        canal=recordatorio.canal,
                        enviado_en=recordatorio.enviado_en,
                        estado_entrega=(
                            recordatorio.estado_entrega.value
                            if recordatorio.estado_entrega
                            else None
                        ),
                        externo_id=recordatorio.externo_id,
                        ultimo_error=recordatorio.ultimo_error,
                        intentos=recordatorio.intentos,
                        proximo_intento_en=recordatorio.proximo_intento_en,
                    )
                )
                await self._sesion.flush()
        except IntegrityError as exc:
            # El indice unico `(cobro_id, paso)`, no una lectura previa: un «existe? -> no ->
            # insertá» pierde contra dos barridos solapados, que es exactamente el caso que
            # HS-T3 RN-05 describe.
            raise RecordatorioDuplicado(
                f"El paso {recordatorio.paso} del cobro {recordatorio.cobro_id} ya fue enviado"
            ) from exc

    async def guardar(self, recordatorio: Recordatorio) -> None:
        fila = await self._sesion.get(RecordatorioORM, recordatorio.id)
        if fila is None:  # pragma: no cover - siempre se guarda algo recien agregado
            raise LookupError(f"El recordatorio {recordatorio.id} no existe")
        fila.enviado_en = recordatorio.enviado_en
        fila.estado_entrega = (
            recordatorio.estado_entrega.value if recordatorio.estado_entrega else None
        )
        fila.externo_id = recordatorio.externo_id
        fila.ultimo_error = recordatorio.ultimo_error
        fila.intentos = recordatorio.intentos
        fila.proximo_intento_en = recordatorio.proximo_intento_en
        await self._sesion.flush()

    async def buscar_para_actualizar(self, recordatorio_id: UUID) -> Recordatorio | None:
        """La fila bloqueada (`FOR UPDATE`) y **releída**: lo que otro barrido confirmó ya se ve.

        `populate_existing` es lo que hace que la relectura no devuelva la copia vieja de la
        sesión: quien esperó el bloqueo tiene que decidir sobre el estado que quedó.
        """
        sentencia = (
            select(RecordatorioORM)
            .where(RecordatorioORM.id == recordatorio_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        fila = (await self._sesion.execute(sentencia)).scalars().first()
        return _recordatorio_a_dominio(fila) if fila is not None else None

    async def pendientes_de_reintento(self, ahora: datetime) -> list[Recordatorio]:
        """Los que esperan un reintento o cuyo envío en curso venció, con su fecha cumplida.

        Los lee `ix_recordatorio_reintento`. RLS (`aislamiento_por_cobro`) los acota a la empresa
        de la sesión. Cada uno se vuelve a leer bloqueado antes de tocarlo.
        """
        sentencia = (
            select(RecordatorioORM)
            .where(
                RecordatorioORM.enviado_en.is_(None),
                RecordatorioORM.proximo_intento_en.is_not(None),
                RecordatorioORM.proximo_intento_en <= ahora,
            )
            .order_by(RecordatorioORM.proximo_intento_en)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_recordatorio_a_dominio(fila) for fila in filas]

    async def buscar_por_externo_id(
        self, externo_id: str, *, para_actualizar: bool = False
    ) -> Recordatorio | None:
        """Por el `wamid`. RLS (`aislamiento_por_cobro`) acota a los cobros de la empresa.

        Con `para_actualizar` bloquea solo la fila de `recordatorio` (`FOR UPDATE`): la política
        es `FOR ALL`, así que el bloqueo respeta el mismo `USING` que la lectura.
        """
        sentencia = select(RecordatorioORM).where(RecordatorioORM.externo_id == externo_id)
        if para_actualizar:
            sentencia = sentencia.with_for_update().execution_options(populate_existing=True)
        fila = (await self._sesion.execute(sentencia)).scalars().first()
        return _recordatorio_a_dominio(fila) if fila is not None else None

    async def de_cobro(self, cobro_id: UUID) -> list[Recordatorio]:
        sentencia = (
            select(RecordatorioORM)
            .where(RecordatorioORM.cobro_id == cobro_id)
            .order_by(RecordatorioORM.paso)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_recordatorio_a_dominio(fila) for fila in filas]

    async def de_cobros(self, cobro_ids: list[UUID]) -> dict[UUID, list[Recordatorio]]:
        if not cobro_ids:
            return {}
        sentencia = (
            select(RecordatorioORM)
            .where(RecordatorioORM.cobro_id.in_(cobro_ids))
            .order_by(RecordatorioORM.paso)
        )
        agrupados: dict[UUID, list[Recordatorio]] = {}
        for fila in (await self._sesion.execute(sentencia)).scalars().all():
            agrupados.setdefault(fila.cobro_id, []).append(_recordatorio_a_dominio(fila))
        return agrupados


def _recordatorio_a_dominio(fila: RecordatorioORM) -> Recordatorio:
    return Recordatorio(
        id=fila.id,
        cobro_id=fila.cobro_id,
        paso=fila.paso,
        canal=fila.canal,
        enviado_en=fila.enviado_en,
        estado_entrega=EstadoEntrega(fila.estado_entrega) if fila.estado_entrega else None,
        externo_id=fila.externo_id,
        ultimo_error=fila.ultimo_error,
        intentos=fila.intentos,
        proximo_intento_en=fila.proximo_intento_en,
    )


__all__ = ["RepositorioRecordatoriosPostgres"]
