"""PostgreSQL adapter for `PortRepositorioComprobante`.

Same two conventions as every repository here: the mapping is hand-written in both
directions so the domain keeps no framework dependency (R1), and `empresa_id` never reaches
a `WHERE` clause because Row-Level Security already scopes the statement (HU-E5-01 RN-01).

**There is no `eliminar`, and the role has no `DELETE`.** A document with a CAE is a legal
record; it is reversed with a credit note, never removed.

One thing worth reading twice: `guardar` rewrites the items rather than diffing them. That
is only safe because a document stops being editable the moment it leaves `VALIDADO` --
`_exigir_editable` in the aggregate is what makes it so -- and it is much safer than a diff,
which is the shape that silently drops a line.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.billing.application.ports import FiltrosDeComprobante
from cheatsheet.contexts.billing.domain.comprobante import (
    CAE,
    AlicuotaIVA,
    Comprobante,
    EstadoComprobante,
    ItemDeComprobante,
    Receptor,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.contexts.billing.infrastructure.models_comprobante import (
    ComprobanteORM,
    ItemDeComprobanteORM,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA


def _item_a_dominio(fila: ItemDeComprobanteORM) -> ItemDeComprobante:
    return ItemDeComprobante(
        id=fila.id,
        descripcion=fila.descripcion,
        cantidad=fila.cantidad,
        precio_unitario=fila.precio_unitario,
        alicuota_iva=AlicuotaIVA.desde_tasa(fila.alicuota_iva),
    )


def _a_dominio(fila: ComprobanteORM, items: list[ItemDeComprobanteORM]) -> Comprobante:
    cae = (
        CAE(codigo=fila.cae_codigo, vence_el=fila.cae_fecha_vencimiento)
        if fila.cae_codigo is not None and fila.cae_fecha_vencimiento is not None
        else None
    )
    return Comprobante(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        cliente_id=fila.cliente_id,
        punto_de_venta_id=fila.punto_de_venta_id,
        tipo=TipoComprobante(fila.tipo),
        receptor=Receptor(
            nombre=fila.receptor_nombre,
            cuit=fila.receptor_cuit,
            condicion_iva=CondicionIVA(fila.receptor_condicion_iva),
            domicilio=fila.receptor_domicilio,
        ),
        emisor_condicion_iva=CondicionIVA(fila.emisor_condicion_iva),
        created_at=fila.created_at,
        items=[_item_a_dominio(item) for item in items],
        estado=EstadoComprobante(fila.estado),
        numero=fila.numero,
        cae=cae,
        fecha_emision=fila.fecha_emision,
        motivo_de_rechazo=fila.motivo_de_rechazo,
        comprobante_origen_id=fila.comprobante_origen_id,
        turno_id=fila.turno_id,
        saldo_pendiente=fila.saldo_pendiente,
    )


class RepositorioComprobantePostgres:
    """Documents, backed by PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, comprobante: Comprobante) -> None:
        self._sesion.add(self._a_fila(comprobante, ComprobanteORM()))
        self._agregar_items(comprobante)
        await self._sesion.flush()

    async def guardar(self, comprobante: Comprobante) -> None:
        fila = await self._sesion.get(ComprobanteORM, comprobante.id)
        if fila is None:
            raise LookupError(f"El comprobante {comprobante.id} no existe para esta empresa")
        self._a_fila(comprobante, fila)
        # Rewritten, not diffed. Safe because the aggregate refuses to change the items of
        # anything past `VALIDADO`, and a diff is the shape that drops a line unnoticed.
        await self._sesion.execute(
            delete(ItemDeComprobanteORM).where(
                ItemDeComprobanteORM.comprobante_id == comprobante.id
            )
        )
        self._agregar_items(comprobante)
        await self._sesion.flush()

    async def buscar_por_id(self, comprobante_id: UUID) -> Comprobante | None:
        fila = await self._sesion.get(ComprobanteORM, comprobante_id)
        if fila is None:
            return None
        return _a_dominio(fila, await self._items_de(comprobante_id))

    async def listar(self, filtros: FiltrosDeComprobante) -> list[Comprobante]:
        sentencia = select(ComprobanteORM)
        if filtros.desde is not None:
            sentencia = sentencia.where(ComprobanteORM.fecha_emision >= filtros.desde)
        if filtros.hasta is not None:
            sentencia = sentencia.where(ComprobanteORM.fecha_emision <= filtros.hasta)
        if filtros.tipos:
            sentencia = sentencia.where(
                ComprobanteORM.tipo.in_([tipo.value for tipo in filtros.tipos])
            )
        if filtros.estados:
            sentencia = sentencia.where(
                ComprobanteORM.estado.in_([estado.value for estado in filtros.estados])
            )
        # RN-03: issue date descending. `nulls_last` puts drafts at the bottom -- they have
        # no issue date, and PostgreSQL sorts NULLs first on a descending order, which would
        # float every unfinished draft above the documents somebody came here to see.
        sentencia = sentencia.order_by(
            ComprobanteORM.fecha_emision.desc().nulls_last(), ComprobanteORM.created_at.desc()
        )
        return await self._armar(sentencia)

    async def notas_de(self, origen_id: UUID) -> list[Comprobante]:
        sentencia = (
            select(ComprobanteORM)
            .where(ComprobanteORM.comprobante_origen_id == origen_id)
            .order_by(ComprobanteORM.created_at)
        )
        return await self._armar(sentencia)

    async def en_vuelo(self, *, anteriores_a: datetime) -> list[Comprobante]:
        sentencia = (
            select(ComprobanteORM)
            .where(ComprobanteORM.estado == EstadoComprobante.ENVIADO_A_ARCA.value)
            .where(ComprobanteORM.fecha_emision < anteriores_a)
            .order_by(ComprobanteORM.fecha_emision)
        )
        return await self._armar(sentencia)

    async def _armar(self, sentencia: Select[tuple[ComprobanteORM]]) -> list[Comprobante]:
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        # One query for every document's items instead of one per document: a listing of a
        # hundred documents is a hundred and one queries otherwise, and PAN-FAC-01 shows the
        # total, which needs them.
        por_comprobante = await self._items_de_varios([fila.id for fila in filas])
        return [_a_dominio(fila, por_comprobante.get(fila.id, [])) for fila in filas]

    async def _items_de(self, comprobante_id: UUID) -> list[ItemDeComprobanteORM]:
        sentencia = select(ItemDeComprobanteORM).where(
            ItemDeComprobanteORM.comprobante_id == comprobante_id
        )
        return list((await self._sesion.execute(sentencia)).scalars().all())

    async def _items_de_varios(self, ids: list[UUID]) -> dict[UUID, list[ItemDeComprobanteORM]]:
        if not ids:
            return {}
        sentencia = select(ItemDeComprobanteORM).where(ItemDeComprobanteORM.comprobante_id.in_(ids))
        agrupados: dict[UUID, list[ItemDeComprobanteORM]] = {}
        for item in (await self._sesion.execute(sentencia)).scalars().all():
            agrupados.setdefault(item.comprobante_id, []).append(item)
        return agrupados

    def _agregar_items(self, comprobante: Comprobante) -> None:
        for item in comprobante.items:
            self._sesion.add(
                ItemDeComprobanteORM(
                    id=item.id,
                    comprobante_id=comprobante.id,
                    descripcion=item.descripcion,
                    cantidad=item.cantidad,
                    precio_unitario=item.precio_unitario,
                    alicuota_iva=item.alicuota_iva.tasa,
                    subtotal=item.subtotal,
                )
            )

    @staticmethod
    def _a_fila(comprobante: Comprobante, fila: ComprobanteORM) -> ComprobanteORM:
        fila.id = comprobante.id
        fila.empresa_id = comprobante.empresa_id
        fila.cliente_id = comprobante.cliente_id
        fila.punto_de_venta_id = comprobante.punto_de_venta_id
        fila.tipo = comprobante.tipo.value
        fila.estado = comprobante.estado.value
        fila.numero = comprobante.numero
        fila.receptor_nombre = comprobante.receptor.nombre
        fila.receptor_cuit = comprobante.receptor.cuit
        fila.receptor_condicion_iva = comprobante.receptor.condicion_iva.value
        fila.receptor_domicilio = comprobante.receptor.domicilio
        fila.emisor_condicion_iva = comprobante.emisor_condicion_iva.value
        fila.cae_codigo = comprobante.cae.codigo if comprobante.cae else None
        fila.cae_fecha_vencimiento = comprobante.cae.vence_el if comprobante.cae else None
        fila.motivo_de_rechazo = comprobante.motivo_de_rechazo
        # The totals are written from the aggregate's already-rounded values (D15), never
        # recomputed here: a second implementation of the arithmetic is a second chance to
        # disagree with the document ARCA authorised.
        fila.subtotal = comprobante.subtotal
        fila.total_iva = comprobante.total_iva
        fila.total = comprobante.total
        fila.saldo_pendiente = comprobante.saldo_pendiente
        fila.comprobante_origen_id = comprobante.comprobante_origen_id
        fila.turno_id = comprobante.turno_id
        fila.fecha_emision = comprobante.fecha_emision
        fila.created_at = comprobante.created_at
        fila.updated_at = comprobante.fecha_emision or comprobante.created_at
        return fila


async def empresas_con_comprobantes_en_vuelo(sesion: AsyncSession) -> list[EmpresaId]:
    """Which companies have a document stuck in `ENVIADO_A_ARCA`, for the sweep of D17.

    The one cross-company read of this context, and the same shape as the five that came
    before it: a `SECURITY DEFINER` function that returns ids and nothing else, feeding a
    per-company task where Row-Level Security applies exactly as it does for a request.

    The session handed in here must be one **without** a company (`sesion_sin_empresa`):
    with one set, the policy would scope the function's caller to a single tenant and the
    sweep would quietly only ever reconcile that company's documents.
    """
    filas = await sesion.execute(
        text("SELECT empresa_id FROM empresas_con_comprobantes_en_vuelo()")
    )
    return [EmpresaId(fila[0]) for fila in filas]


__all__ = ["RepositorioComprobantePostgres", "empresas_con_comprobantes_en_vuelo"]
