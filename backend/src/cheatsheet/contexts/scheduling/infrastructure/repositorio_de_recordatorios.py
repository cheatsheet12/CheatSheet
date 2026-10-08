"""Adaptador PostgreSQL de las filas de recordatorio de turno.

Las convenciones de siempre: mapeo a mano en los dos sentidos y `empresa_id` nunca en un `WHERE`,
porque RLS ya acota. **`agregar` es donde la idempotencia llega al código**: el índice único
`uq_recordatorio_de_turno` rechaza la segunda fila de la misma clave y acá se traduce a
`RecordatorioDeTurnoDuplicado`. El `INSERT` corre en su propio savepoint para que el rechazo no
deje abortada la transacción del barrido.

`empresas_con_turnos_por_recordar` es el fan-out entre empresas: llama a la función
`SECURITY DEFINER` de la migración 0039, que devuelve solo ids.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.scheduling.application.errors import RecordatorioDeTurnoDuplicado
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    RecordatorioDeTurno,
    ResultadoDeRecordatorio,
)
from cheatsheet.contexts.scheduling.infrastructure.models import RecordatorioDeTurnoORM

#: El nombre que pone la migración 0039. Se compara contra el texto del `IntegrityError` porque
#: asyncpg no expone el nombre de la restricción de forma tipada.
INDICE_UNICO = "uq_recordatorio_de_turno"

_EMPRESAS_CON_TURNOS_POR_RECORDAR = text(
    "SELECT empresa_id FROM empresas_con_turnos_por_recordar(:hasta)"
)


class RepositorioRecordatoriosDeTurnoPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, recordatorio: RecordatorioDeTurno) -> None:
        try:
            async with self._sesion.begin_nested():
                self._sesion.add(_a_fila(recordatorio, RecordatorioDeTurnoORM()))
                await self._sesion.flush()
        except IntegrityError as exc:
            if INDICE_UNICO in str(exc.orig):
                raise RecordatorioDeTurnoDuplicado(
                    "Ya existe el recordatorio de ese turno, anticipación y franja"
                ) from exc
            raise

    async def guardar(self, recordatorio: RecordatorioDeTurno) -> None:
        fila = await self._sesion.get(RecordatorioDeTurnoORM, recordatorio.id)
        if fila is None:
            raise LookupError(f"El recordatorio {recordatorio.id} no existe para esta empresa")
        _a_fila(recordatorio, fila)
        await self._sesion.flush()

    async def de_turnos(self, turno_ids: list[UUID]) -> list[RecordatorioDeTurno]:
        if not turno_ids:
            return []
        sentencia = (
            select(RecordatorioDeTurnoORM)
            .where(RecordatorioDeTurnoORM.turno_id.in_(turno_ids))
            .order_by(RecordatorioDeTurnoORM.created_at, RecordatorioDeTurnoORM.id)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def pendientes(self, hasta: datetime) -> list[RecordatorioDeTurno]:
        sentencia = (
            select(RecordatorioDeTurnoORM)
            .where(RecordatorioDeTurnoORM.resultado.is_(None))
            .where(RecordatorioDeTurnoORM.proximo_intento_en <= hasta)
            .order_by(RecordatorioDeTurnoORM.proximo_intento_en, RecordatorioDeTurnoORM.id)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]


async def empresas_con_turnos_por_recordar(sesion: AsyncSession, hasta: datetime) -> list[UUID]:
    """Las empresas a visitar: con un turno abierto que empieza hasta `hasta`, o con un
    recordatorio sin terminar. Solo ids, y **no** corre bajo RLS de una empresa.
    """
    filas = await sesion.execute(_EMPRESAS_CON_TURNOS_POR_RECORDAR, {"hasta": hasta})
    return [fila[0] for fila in filas.all()]


def _a_dominio(fila: RecordatorioDeTurnoORM) -> RecordatorioDeTurno:
    return RecordatorioDeTurno(
        id=fila.id,
        empresa_id=fila.empresa_id,
        turno_id=fila.turno_id,
        anticipacion_min=fila.anticipacion_min,
        franja_inicio=fila.franja_inicio,
        created_at=fila.created_at,
        resultado=ResultadoDeRecordatorio(fila.resultado) if fila.resultado else None,
        intentos=fila.intentos,
        proximo_intento_en=fila.proximo_intento_en,
        ultimo_error=fila.ultimo_error,
        procesado_en=fila.procesado_en,
    )


def _a_fila(
    recordatorio: RecordatorioDeTurno, fila: RecordatorioDeTurnoORM
) -> RecordatorioDeTurnoORM:
    fila.id = recordatorio.id
    fila.empresa_id = recordatorio.empresa_id
    fila.turno_id = recordatorio.turno_id
    fila.anticipacion_min = recordatorio.anticipacion_min
    fila.franja_inicio = recordatorio.franja_inicio
    fila.resultado = recordatorio.resultado.value if recordatorio.resultado else None
    fila.intentos = recordatorio.intentos
    fila.proximo_intento_en = recordatorio.proximo_intento_en
    fila.ultimo_error = recordatorio.ultimo_error
    fila.procesado_en = recordatorio.procesado_en
    fila.created_at = recordatorio.created_at
    return fila


__all__ = ["RepositorioRecordatoriosDeTurnoPostgres", "empresas_con_turnos_por_recordar"]
