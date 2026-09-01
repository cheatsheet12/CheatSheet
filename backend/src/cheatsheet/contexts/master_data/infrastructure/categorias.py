"""PostgreSQL adapters for the category and classification ports.

In their own module rather than in `repositories.py` for a plain reason: that file already
holds two aggregates and 237 lines, and `CLAUDE.md` §5 caps a file at 400. Splitting by
aggregate keeps both readable.

Nothing here filters by `empresa_id` except `listar`, and that is the same arrangement the
sibling module explains: the company filter is the RLS policy of migration 0010, not a
`WHERE` somebody could forget.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from cheatsheet.contexts.master_data.domain.categoria import CategoriaEmpresa
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.contexts.master_data.infrastructure.models import (
    CategoriaEmpresaORM,
    ClienteCategoriaORM,
    ServicioCategoriaORM,
)
from cheatsheet.shared.empresa import EmpresaId


def _a_dominio(fila: CategoriaEmpresaORM) -> CategoriaEmpresa:
    return CategoriaEmpresa(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        nombre=fila.nombre,
        aplica_a=AmbitoDeCategoria(fila.aplica_a),
        creado_en=fila.created_at,
    )


def _volcar(categoria: CategoriaEmpresa, fila: CategoriaEmpresaORM) -> None:
    fila.empresa_id = categoria.empresa_id
    fila.nombre = categoria.nombre
    fila.aplica_a = categoria.aplica_a.value
    fila.created_at = categoria.creado_en


def _ambitos_que_admiten(aplica_a: AmbitoDeCategoria) -> tuple[str, ...]:
    """Which stored scopes can classify what `aplica_a` names.

    Asking for `CLIENTE` has to return the `AMBOS` ones too — those are assignable to a
    client — and asking for `AMBOS` returns only the ones that admit both. This is
    HU-E4-04 RN-01 expressed as a query, so the form's dropdown does not have to know it.
    """
    if aplica_a is AmbitoDeCategoria.AMBOS:
        return (AmbitoDeCategoria.AMBOS.value,)
    return (aplica_a.value, AmbitoDeCategoria.AMBOS.value)


class RepositorioCategoriaPostgres:
    """Implements `PortRepositorioCategoria`."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, categoria: CategoriaEmpresa) -> None:
        fila = CategoriaEmpresaORM(id=categoria.id)
        _volcar(categoria, fila)
        self._sesion.add(fila)
        await self._sesion.flush()

    async def guardar(self, categoria: CategoriaEmpresa) -> None:
        fila = await self._sesion.get(CategoriaEmpresaORM, categoria.id)
        if fila is None:
            await self.agregar(categoria)
            return
        _volcar(categoria, fila)
        await self._sesion.flush()

    async def eliminar(self, categoria_id: UUID) -> None:
        """The one delete `master_data` performs. See migration 0010 for why it is granted.

        The classifications go with it through `ON DELETE CASCADE`, which is RN-03: the
        elements lose the label and nothing else.
        """
        await self._sesion.execute(
            delete(CategoriaEmpresaORM).where(CategoriaEmpresaORM.id == categoria_id)
        )
        await self._sesion.flush()

    async def buscar_por_id(self, categoria_id: UUID) -> CategoriaEmpresa | None:
        fila = await self._sesion.get(CategoriaEmpresaORM, categoria_id)
        return _a_dominio(fila) if fila is not None else None

    async def buscar_por_nombre_y_ambito(
        self, *, nombre: str, aplica_a: AmbitoDeCategoria
    ) -> CategoriaEmpresa | None:
        """Case-insensitive, matching the functional unique index exactly.

        If the two ever disagreed, the message would say one thing and the database would
        do another — so both compare `lower(nombre)`.
        """
        fila = await self._sesion.scalar(
            select(CategoriaEmpresaORM).where(
                func.lower(CategoriaEmpresaORM.nombre) == nombre.strip().lower(),
                CategoriaEmpresaORM.aplica_a == aplica_a.value,
            )
        )
        return _a_dominio(fila) if fila is not None else None

    async def listar(
        self, *, empresa_id: EmpresaId, aplica_a: AmbitoDeCategoria | None = None
    ) -> Sequence[CategoriaEmpresa]:
        consulta: Select[tuple[CategoriaEmpresaORM]] = select(CategoriaEmpresaORM).where(
            CategoriaEmpresaORM.empresa_id == empresa_id
        )
        if aplica_a is not None:
            consulta = consulta.where(
                CategoriaEmpresaORM.aplica_a.in_(_ambitos_que_admiten(aplica_a))
            )
        filas = await self._sesion.scalars(consulta.order_by(CategoriaEmpresaORM.nombre))
        return [_a_dominio(fila) for fila in filas]


class ClasificacionesPostgres:
    """Implements `PortClasificaciones`.

    **Every operation is idempotent**, and the way that is achieved matters: assigning uses
    `INSERT … ON CONFLICT DO NOTHING` against the composite primary key, so a second click
    is a no-op in the database rather than a duplicate the application has to notice.
    Removing something that is not there deletes zero rows, which is the same end state.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def asignar_a_cliente(self, *, cliente_id: UUID, categoria_id: UUID) -> None:
        await self._asignar(ClienteCategoriaORM, "cliente_id", cliente_id, categoria_id)

    async def quitar_de_cliente(self, *, cliente_id: UUID, categoria_id: UUID) -> None:
        await self._sesion.execute(
            delete(ClienteCategoriaORM).where(
                ClienteCategoriaORM.cliente_id == cliente_id,
                ClienteCategoriaORM.categoria_id == categoria_id,
            )
        )
        await self._sesion.flush()

    async def categorias_de_cliente(self, cliente_id: UUID) -> Sequence[CategoriaEmpresa]:
        return await self._categorias_de(
            ClienteCategoriaORM, ClienteCategoriaORM.cliente_id, cliente_id
        )

    async def asignar_a_servicio(self, *, servicio_id: UUID, categoria_id: UUID) -> None:
        await self._asignar(ServicioCategoriaORM, "servicio_id", servicio_id, categoria_id)

    async def quitar_de_servicio(self, *, servicio_id: UUID, categoria_id: UUID) -> None:
        await self._sesion.execute(
            delete(ServicioCategoriaORM).where(
                ServicioCategoriaORM.servicio_id == servicio_id,
                ServicioCategoriaORM.categoria_id == categoria_id,
            )
        )
        await self._sesion.flush()

    async def categorias_de_servicio(self, servicio_id: UUID) -> Sequence[CategoriaEmpresa]:
        return await self._categorias_de(
            ServicioCategoriaORM, ServicioCategoriaORM.servicio_id, servicio_id
        )

    async def _asignar(
        self,
        modelo: type[ClienteCategoriaORM] | type[ServicioCategoriaORM],
        columna: str,
        elemento_id: UUID,
        categoria_id: UUID,
    ) -> None:
        """`empresa_id` is read off the category rather than taken as a parameter.

        The category was already fetched through the repository by the use case, so it is
        known to belong to the caller's company — and copying it from there is what keeps
        the link's own `empresa_id` consistent with the row RLS will check it against.
        """
        empresa_id = await self._sesion.scalar(
            select(CategoriaEmpresaORM.empresa_id).where(CategoriaEmpresaORM.id == categoria_id)
        )
        await self._sesion.execute(
            insert(modelo)
            .values({columna: elemento_id, "categoria_id": categoria_id, "empresa_id": empresa_id})
            .on_conflict_do_nothing()
        )
        await self._sesion.flush()

    async def _categorias_de(
        self,
        modelo: type[ClienteCategoriaORM] | type[ServicioCategoriaORM],
        columna: InstrumentedAttribute[UUID],
        elemento_id: UUID,
    ) -> Sequence[CategoriaEmpresa]:
        filas = await self._sesion.scalars(
            select(CategoriaEmpresaORM)
            .join(modelo, modelo.categoria_id == CategoriaEmpresaORM.id)
            .where(columna == elemento_id)
            .order_by(CategoriaEmpresaORM.nombre)
        )
        return [_a_dominio(fila) for fila in filas]
