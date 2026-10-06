"""PostgreSQL adapter for `PortCorreccionDeNombres` (HU-E4-05 RN-09).

Like its siblings, nothing here filters by `empresa_id`: every statement runs in a session
that already set `app.current_empresa`, and the RLS policies (migrations 0008, 0009, 0010
and 0030) do the filtering. The one place that needs the company's id as a *value* — the
backup rows and the advisory lock — reads it from that same setting, so there is a single
source of truth for "which company is this".

**What the correction never writes.** Only `nombre`. `updated_at` stays as it was, because
the spreadsheet write-back decides what to send by comparing it (P2), and RN-09 says the
correction does not touch the sheets. So this module issues its own `UPDATE`s instead of
going through the aggregates, whose `renombrar` moves the timestamp.

**Compare-and-set.** Every `UPDATE` also requires `nombre = <the name that was read>`. A
row edited between the read and the write is skipped, never overwritten, and is not
returned, so it gets no backup row either.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, func, insert, literal_column, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from cheatsheet.contexts.master_data.application.ports import ResumenDeCorrida
from cheatsheet.contexts.master_data.domain.correccion import (
    Cambio,
    EntidadCorregible,
    NombreRegistrado,
)
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.contexts.master_data.infrastructure.models import (
    INDICE_CATEGORIA_UNICA,
    CategoriaEmpresaORM,
    ClienteORM,
    RespaldoDeNormalizacionORM,
    ServicioORM,
)
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CUIT

TAMANO_DE_LOTE = 500

TURNO = text(
    "SELECT pg_try_advisory_xact_lock("
    "hashtextextended('correccion_de_datos:' || current_setting('app.current_empresa', true), 0))"
)
EMPRESA_ACTUAL = text(
    "SELECT CAST(NULLIF(current_setting('app.current_empresa', true), '') AS uuid)"
)

#: The rule of migration 0025, as a boolean column: `IS TRUE` and not the bare expression,
#: because a `NULL` duration makes the rule evaluate to `NULL` and that must read as invalid.
DURACION_VALIDA = literal_column(
    "((agendable AND duracion_estandar_min IS NOT NULL "
    "AND duracion_estandar_min BETWEEN 5 AND 480) "
    "OR (NOT agendable AND duracion_estandar_min IS NULL)) IS TRUE",
    Boolean,
).label("duracion_valida")

# One literal statement per table, never interpolated: the same reason the migrations give.
# `unnest` over three parallel arrays is the batch: one round trip per 500 rows.
ACTUALIZAR_CLIENTES = text(
    "UPDATE cliente t SET nombre = v.nuevo "
    "FROM unnest(CAST(:ids AS uuid[]), CAST(:originales AS text[]), CAST(:nuevos AS text[])) "
    "AS v(id, original, nuevo) "
    "WHERE t.id = v.id AND t.nombre = v.original RETURNING t.id"
)
ACTUALIZAR_SERVICIOS = text(
    "UPDATE servicio t SET nombre = v.nuevo "
    "FROM unnest(CAST(:ids AS uuid[]), CAST(:originales AS text[]), CAST(:nuevos AS text[])) "
    "AS v(id, original, nuevo) "
    "WHERE t.id = v.id AND t.nombre = v.original RETURNING t.id"
)
RESTAURAR_CLIENTES = text(
    "UPDATE cliente t SET nombre = r.valor_original FROM respaldo_de_normalizacion r "
    "WHERE r.corrida_id = :corrida AND r.entidad = 'CLIENTE' AND t.id = r.entidad_id "
    "AND t.nombre = r.valor_normalizado RETURNING t.id"
)
RESTAURAR_SERVICIOS = text(
    "UPDATE servicio t SET nombre = r.valor_original FROM respaldo_de_normalizacion r "
    "WHERE r.corrida_id = :corrida AND r.entidad = 'SERVICIO' AND t.id = r.entidad_id "
    "AND t.nombre = r.valor_normalizado RETURNING t.id"
)


def _es_colision_de_categoria(error: IntegrityError) -> bool:
    return INDICE_CATEGORIA_UNICA in str(error.orig)


class CorreccionDeNombresPostgres:
    """Implements `PortCorreccionDeNombres`."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def tomar_turno(self) -> bool:
        return bool(await self._sesion.scalar(TURNO))

    async def leer_nombres(self) -> Sequence[NombreRegistrado]:
        clientes = await self._sesion.execute(
            select(ClienteORM.id, ClienteORM.nombre, ClienteORM.cuit)
        )
        servicios = await self._sesion.execute(
            select(ServicioORM.id, ServicioORM.nombre, DURACION_VALIDA)
        )
        categorias = await self._sesion.execute(
            select(CategoriaEmpresaORM.id, CategoriaEmpresaORM.nombre, CategoriaEmpresaORM.aplica_a)
        )
        registros = [
            NombreRegistrado(
                entidad=EntidadCorregible.CLIENTE,
                id=fila.id,
                nombre=fila.nombre,
                cuit=_cuit_o_nada(fila.cuit),
            )
            for fila in clientes
        ]
        registros.extend(
            NombreRegistrado(
                entidad=EntidadCorregible.SERVICIO,
                id=fila.id,
                nombre=fila.nombre,
                duracion_valida=bool(fila.duracion_valida),
            )
            for fila in servicios
        )
        registros.extend(
            NombreRegistrado(
                entidad=EntidadCorregible.CATEGORIA,
                id=fila.id,
                nombre=fila.nombre,
                aplica_a=AmbitoDeCategoria(fila.aplica_a),
            )
            for fila in categorias
        )
        return registros

    async def aplicar(
        self, corrida_id: UUID, cambios: Sequence[Cambio], momento: datetime
    ) -> Sequence[Cambio]:
        empresa_id = await self._sesion.scalar(EMPRESA_ACTUAL)
        escritos: list[Cambio] = []
        for entidad, sentencia in (
            (EntidadCorregible.CLIENTE, ACTUALIZAR_CLIENTES),
            (EntidadCorregible.SERVICIO, ACTUALIZAR_SERVICIOS),
        ):
            propios = [c for c in cambios if c.entidad is entidad]
            for inicio in range(0, len(propios), TAMANO_DE_LOTE):
                lote = propios[inicio : inicio + TAMANO_DE_LOTE]
                escritos_del_lote = await self._actualizar_lote(sentencia, lote)
                await self._respaldar(corrida_id, empresa_id, escritos_del_lote, momento)
                escritos.extend(escritos_del_lote)
        for cambio in cambios:
            if cambio.entidad is EntidadCorregible.CATEGORIA and await self._renombrar_categoria(
                corrida_id, empresa_id, cambio, momento
            ):
                escritos.append(cambio)
        return escritos

    async def _actualizar_lote(self, sentencia: TextClause, lote: Sequence[Cambio]) -> list[Cambio]:
        resultado = await self._sesion.execute(
            sentencia,
            {
                "ids": [c.id for c in lote],
                "originales": [c.original for c in lote],
                "nuevos": [c.normalizado for c in lote],
            },
        )
        devueltos = {fila.id for fila in resultado}
        return [c for c in lote if c.id in devueltos]

    async def _respaldar(
        self,
        corrida_id: UUID,
        empresa_id: UUID | None,
        cambios: Sequence[Cambio],
        momento: datetime,
    ) -> None:
        if not cambios:
            return
        await self._sesion.execute(
            insert(RespaldoDeNormalizacionORM),
            [
                {
                    "id": uuid4(),
                    "empresa_id": empresa_id,
                    "corrida_id": corrida_id,
                    "entidad": c.entidad.value,
                    "entidad_id": c.id,
                    "campo": "nombre",
                    "valor_original": c.original,
                    "valor_normalizado": c.normalizado,
                    "created_at": momento,
                }
                for c in cambios
            ],
        )

    async def _renombrar_categoria(
        self, corrida_id: UUID, empresa_id: UUID | None, cambio: Cambio, momento: datetime
    ) -> bool:
        """One category, inside a savepoint: the unique index is the second barrier.

        The domain already left out what it saw colliding, but Python's `lower()` and
        PostgreSQL's can disagree outside ASCII. When the index refuses, only this
        savepoint is rolled back — the transaction, and every other change, survives.
        """
        try:
            async with self._sesion.begin_nested():
                resultado = await self._sesion.execute(
                    update(CategoriaEmpresaORM)
                    .where(
                        CategoriaEmpresaORM.id == cambio.id,
                        CategoriaEmpresaORM.nombre == cambio.original,
                    )
                    .values(nombre=cambio.normalizado)
                    .returning(CategoriaEmpresaORM.id)
                    .execution_options(synchronize_session=False)
                )
                if resultado.scalar_one_or_none() is None:
                    return False
                await self._respaldar(corrida_id, empresa_id, [cambio], momento)
        except IntegrityError as error:
            if not _es_colision_de_categoria(error):
                raise
            return False
        return True

    async def restaurar(self, corrida_id: UUID) -> tuple[int, int]:
        respaldadas = await self._sesion.scalar(
            select(func.count())
            .select_from(RespaldoDeNormalizacionORM)
            .where(RespaldoDeNormalizacionORM.corrida_id == corrida_id)
        )
        restauradas = 0
        for sentencia in (RESTAURAR_CLIENTES, RESTAURAR_SERVICIOS):
            resultado = await self._sesion.execute(sentencia, {"corrida": corrida_id})
            restauradas += len(resultado.all())
        restauradas += await self._restaurar_categorias(corrida_id)
        return (restauradas, (respaldadas or 0) - restauradas)

    async def _restaurar_categorias(self, corrida_id: UUID) -> int:
        filas = await self._sesion.execute(
            select(
                RespaldoDeNormalizacionORM.entidad_id,
                RespaldoDeNormalizacionORM.valor_original,
                RespaldoDeNormalizacionORM.valor_normalizado,
            ).where(
                RespaldoDeNormalizacionORM.corrida_id == corrida_id,
                RespaldoDeNormalizacionORM.entidad == EntidadCorregible.CATEGORIA.value,
            )
        )
        restauradas = 0
        for fila in filas.all():
            try:
                async with self._sesion.begin_nested():
                    resultado = await self._sesion.execute(
                        update(CategoriaEmpresaORM)
                        .where(
                            CategoriaEmpresaORM.id == fila.entidad_id,
                            CategoriaEmpresaORM.nombre == fila.valor_normalizado,
                        )
                        .values(nombre=fila.valor_original)
                        .returning(CategoriaEmpresaORM.id)
                        .execution_options(synchronize_session=False)
                    )
                    restauradas += len(resultado.all())
            except IntegrityError as error:
                if not _es_colision_de_categoria(error):
                    raise
        return restauradas

    async def existe_corrida(self, corrida_id: UUID) -> bool:
        fila = await self._sesion.scalar(
            select(RespaldoDeNormalizacionORM.id)
            .where(RespaldoDeNormalizacionORM.corrida_id == corrida_id)
            .limit(1)
        )
        return fila is not None

    async def listar_corridas(self) -> Sequence[ResumenDeCorrida]:
        momento = func.min(RespaldoDeNormalizacionORM.created_at)
        filas = await self._sesion.execute(
            select(RespaldoDeNormalizacionORM.corrida_id, momento, func.count())
            .group_by(RespaldoDeNormalizacionORM.corrida_id)
            .order_by(momento.desc())
        )
        return [
            ResumenDeCorrida(corrida_id=corrida, creada_en=creada, cantidad=cantidad)
            for corrida, creada, cantidad in filas.all()
        ]


def _cuit_o_nada(valor: str | None) -> CUIT | None:
    """A stored CUIT passed the check digit on the way in; this only guards a corrupt row."""
    if not valor:
        return None
    try:
        return CUIT(valor)
    except EntradaInvalida:
        return None
