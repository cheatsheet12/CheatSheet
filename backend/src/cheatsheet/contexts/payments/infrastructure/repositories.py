"""Adaptadores PostgreSQL de los dos repositorios de `payments`.

Las convenciones de siempre: mapeo a mano en los dos sentidos para que el dominio no cargue
una dependencia de framework (R1), y `empresa_id` nunca en un `WHERE` porque RLS ya acota.

**Ninguno tiene `eliminar`.** Un cobro aprobado es plata que entro y un recordatorio enviado es
un mensaje que un cliente recibio: los dos se cancelan o se reembolsan, no se borran.

`metricas` suma **en la base** y no en Python sobre `listar`. La diferencia no es de
rendimiento: las metricas son del periodo entero y el listado se pagina, asi que sumarlas
sobre la pagina mostraria un total que cambia al pasar de hoja.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.payments.application.errors import RecordatorioDuplicado
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro, MetricasDeCobros
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.contexts.payments.infrastructure.models import CobroORM, RecordatorioORM
from cheatsheet.shared.empresa import EmpresaId

CERO = Decimal("0.00")

#: El listado y las métricas comparten los mismos filtros y devuelven formas distintas —una
#: entidad y una agregación—, así que `_con_filtros` es genérico sobre el `Select`. Sin esto
#: habría dos copias de los mismos tres `where`, que es donde una empresa termina viendo un
#: total calculado sobre un filtro distinto del que muestra.
_Sentencia = TypeVar("_Sentencia", bound=Select[Any])


def _a_dominio(fila: CobroORM) -> Cobro:
    link = (
        LinkDePago(preference_id=fila.mp_preference_id, url=fila.mp_url_pago)
        if fila.mp_preference_id is not None and fila.mp_url_pago is not None
        else None
    )
    return Cobro(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        cliente_id=fila.cliente_id,
        monto=fila.monto,
        descripcion=fila.descripcion,
        vence_el=fila.vence_el,
        created_at=fila.created_at,
        estado=EstadoCobro(fila.estado),
        link=link,
        mp_payment_id=fila.mp_payment_id,
        comprobante_id=fila.comprobante_id,
        turno_id=fila.turno_id,
        pagado_en=fila.pagado_en,
        monto_reembolsado=fila.monto_reembolsado,
        reembolso_solicitado_en=fila.reembolso_solicitado_en,
        motivo_de_cancelacion=fila.motivo_de_cancelacion,
        updated_at=fila.updated_at,
    )


def _a_fila(cobro: Cobro, fila: CobroORM) -> CobroORM:
    fila.id = cobro.id
    fila.empresa_id = cobro.empresa_id
    fila.cliente_id = cobro.cliente_id
    fila.comprobante_id = cobro.comprobante_id
    fila.turno_id = cobro.turno_id
    fila.monto = cobro.monto
    fila.monto_reembolsado = cobro.monto_reembolsado
    fila.descripcion = cobro.descripcion
    fila.estado = cobro.estado.value
    fila.mp_preference_id = cobro.link.preference_id if cobro.link else None
    fila.mp_url_pago = cobro.link.url if cobro.link else None
    fila.mp_payment_id = cobro.mp_payment_id
    fila.vence_el = cobro.vence_el
    fila.pagado_en = cobro.pagado_en
    fila.reembolso_solicitado_en = cobro.reembolso_solicitado_en
    fila.motivo_de_cancelacion = cobro.motivo_de_cancelacion
    fila.created_at = cobro.created_at
    fila.updated_at = cobro.updated_at or cobro.created_at
    return fila


class RepositorioCobroPostgres:
    """Cobros, sobre PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, cobro: Cobro) -> None:
        self._sesion.add(_a_fila(cobro, CobroORM()))
        await self._sesion.flush()

    async def guardar(self, cobro: Cobro) -> None:
        fila = await self._sesion.get(CobroORM, cobro.id)
        if fila is None:
            raise LookupError(f"El cobro {cobro.id} no existe para esta empresa")
        _a_fila(cobro, fila)
        await self._sesion.flush()

    async def buscar_por_id(self, cobro_id: UUID) -> Cobro | None:
        fila = await self._sesion.get(CobroORM, cobro_id)
        return _a_dominio(fila) if fila is not None else None

    async def buscar_por_payment_id(self, payment_id: str) -> Cobro | None:
        """La primera linea de la idempotencia del webhook (D20).

        Una consulta antes de hablar con MercadoPago: si ya procesamos este pago, no hace
        falta una llamada de red para descubrirlo.
        """
        sentencia = select(CobroORM).where(CobroORM.mp_payment_id == payment_id)
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return _a_dominio(fila) if fila is not None else None

    async def buscar_por_preference_id(self, preference_id: str) -> Cobro | None:
        sentencia = select(CobroORM).where(CobroORM.mp_preference_id == preference_id)
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return _a_dominio(fila) if fila is not None else None

    async def listar(self, filtros: FiltrosDeCobro) -> list[Cobro]:
        sentencia = self._con_filtros(select(CobroORM), filtros)
        # HU-E6-01: «ordenados por antiguedad». El mas viejo primero es lo que alguien que
        # revisa la mora quiere ver arriba.
        sentencia = sentencia.order_by(CobroORM.vence_el.asc(), CobroORM.created_at.asc())
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def metricas(self, filtros: FiltrosDeCobro) -> MetricasDeCobros:
        sentencia = self._con_filtros(
            select(CobroORM.estado, func.coalesce(func.sum(CobroORM.monto), CERO)), filtros
        ).group_by(CobroORM.estado)
        totales = {estado: monto for estado, monto in (await self._sesion.execute(sentencia)).all()}
        return MetricasDeCobros(
            cobrado=totales.get(EstadoCobro.APROBADO.value, CERO),
            pendiente=totales.get(EstadoCobro.PENDIENTE.value, CERO),
            en_mora=totales.get(EstadoCobro.VENCIDO.value, CERO),
        )

    async def de_comprobante(self, comprobante_id: UUID) -> list[Cobro]:
        sentencia = (
            select(CobroORM)
            .where(CobroORM.comprobante_id == comprobante_id)
            .order_by(CobroORM.created_at)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def abiertos_vencidos_a(self, ahora: datetime) -> list[Cobro]:
        sentencia = (
            select(CobroORM)
            .where(CobroORM.estado == EstadoCobro.PENDIENTE.value)
            .where(CobroORM.vence_el <= ahora)
            .order_by(CobroORM.vence_el)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def abiertos(self) -> list[Cobro]:
        sentencia = (
            select(CobroORM)
            .where(CobroORM.estado.in_([EstadoCobro.PENDIENTE.value, EstadoCobro.VENCIDO.value]))
            .order_by(CobroORM.vence_el)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    @staticmethod
    def _con_filtros(sentencia: _Sentencia, filtros: FiltrosDeCobro) -> _Sentencia:
        if filtros.desde is not None:
            sentencia = sentencia.where(CobroORM.created_at >= filtros.desde)
        if filtros.hasta is not None:
            sentencia = sentencia.where(CobroORM.created_at <= filtros.hasta)
        if filtros.estados:
            sentencia = sentencia.where(
                CobroORM.estado.in_([estado.value for estado in filtros.estados])
            )
        return sentencia


class RepositorioRecordatoriosPostgres:
    """Recordatorios, sobre PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, recordatorio: Recordatorio) -> None:
        self._sesion.add(
            RecordatorioORM(
                id=recordatorio.id,
                cobro_id=recordatorio.cobro_id,
                paso=recordatorio.paso,
                canal=recordatorio.canal,
                enviado_en=recordatorio.enviado_en,
                estado_entrega=(
                    recordatorio.estado_entrega.value if recordatorio.estado_entrega else None
                ),
            )
        )
        try:
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
        await self._sesion.flush()

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
    )


async def empresas_con_cobros_abiertos(sesion: AsyncSession) -> list[EmpresaId]:
    """Que empresas tienen algo pendiente, para los dos barridos del epico.

    La septima funcion `SECURITY DEFINER` del sistema, y la misma forma que las seis
    anteriores: **devuelve ids y nada mas**. La sesion que se le pasa tiene que ser una
    **sin** empresa (`sesion_sin_empresa`): con una puesta, la politica acotaria al llamador a
    un solo inquilino y el barrido cobraria siempre a la misma empresa.
    """
    filas = await sesion.execute(text("SELECT empresa_id FROM empresas_con_cobros_abiertos()"))
    return [EmpresaId(fila[0]) for fila in filas]


__all__ = [
    "RepositorioCobroPostgres",
    "RepositorioRecordatoriosPostgres",
    "empresas_con_cobros_abiertos",
]
