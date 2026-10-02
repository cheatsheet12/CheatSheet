"""`PortConsultasDeCobranza` sobre PostgreSQL: las series de los gráficos de cobranza.

La **misma definición** que `RepositorioCobroPostgres.metricas` (ADR-0010, punto 6), por eso
comparten `ESTADOS_PAGADOS` y el recorte por período. Si una de las dos cambia sin la otra, el
encabezado y el gráfico dejan de cuadrar; un test de PostgreSQL fija las identidades.

Las tres agregaciones se hacen **en la base** y en `Decimal`, y el día se corta en la zona que
se pida (`timezone(zona, fecha)`): un pago del 31/3 a las 23:30 hora argentina es del 31/3 aunque
en UTC ya sea el 1/4. Las devoluciones se suman sin `JOIN` contra `cobro`: `reembolso` lleva su
propia `empresa_id` y su propia fecha, y RLS la acota.

Vive aparte de `RepositorioCobroPostgres` para no engordar ese archivo.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo
from decimal import Decimal

from sqlalchemy import ColumnElement, Date, String, bindparam, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from cheatsheet.contexts.payments.application.cobranza_del_periodo import CobrosDeUnEstado
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro
from cheatsheet.contexts.payments.domain.cobro import EstadoCobro
from cheatsheet.contexts.payments.infrastructure.models import CobroORM, ReembolsoORM
from cheatsheet.contexts.payments.infrastructure.repositories import (
    CERO,
    ESTADOS_PAGADOS,
    en_periodo,
)

_ZONA = "zona"


def _dia_local(
    columna: InstrumentedAttribute[datetime] | InstrumentedAttribute[datetime | None], zona: tzinfo
) -> ColumnElement[date]:
    """El día calendario de la columna en `zona`, como expresión SQL."""
    return func.date(func.timezone(bindparam(_ZONA, str(zona), type_=String), columna), type_=Date)


class ConsultasDeCobranzaPostgres:
    """Cobrado por día y cobros por estado. **Sólo lectura.**"""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def cobrado_por_dia(self, filtros: FiltrosDeCobro, zona: tzinfo) -> dict[date, Decimal]:
        """Pagos del día menos devoluciones del día, por día local de cada fecha.

        Las correcciones (devoluciones negativas) suman de vuelta, y un día puede quedar
        negativo: es lo que pasó con la caja. Sólo trae los días con movimiento.
        """
        dia_de_pago = _dia_local(CobroORM.fecha_pago, zona)
        pagos = en_periodo(
            select(dia_de_pago, func.coalesce(func.sum(CobroORM.monto), CERO))
            .where(CobroORM.estado.in_(ESTADOS_PAGADOS))
            .group_by(dia_de_pago),
            CobroORM.fecha_pago,
            filtros,
        )
        dia_de_devolucion = _dia_local(ReembolsoORM.fecha_devolucion, zona)
        devoluciones = en_periodo(
            select(dia_de_devolucion, func.coalesce(func.sum(ReembolsoORM.monto), CERO)).group_by(
                dia_de_devolucion
            ),
            ReembolsoORM.fecha_devolucion,
            filtros,
        )
        por_dia: dict[date, Decimal] = {}
        for dia, monto in (await self._sesion.execute(pagos)).all():
            por_dia[dia] = por_dia.get(dia, CERO) + monto
        for dia, monto in (await self._sesion.execute(devoluciones)).all():
            por_dia[dia] = por_dia.get(dia, CERO) - monto
        return dict(sorted(por_dia.items()))

    async def por_estado(self, filtros: FiltrosDeCobro) -> dict[EstadoCobro, CobrosDeUnEstado]:
        """Lo **creado** en el período, por su estado actual, con cantidad y monto.

        Un cobro creado en febrero y pagado en marzo cuenta como pagado al mirar febrero y no
        aparece al mirar marzo. `CANCELADO` entra: también es un cobro que se creó.
        """
        creados = en_periodo(
            select(
                CobroORM.estado,
                func.count(CobroORM.id),
                func.coalesce(func.sum(CobroORM.monto), CERO),
            ).group_by(CobroORM.estado),
            CobroORM.created_at,
            filtros,
        )
        filas = (await self._sesion.execute(creados)).all()
        return {
            EstadoCobro(estado): CobrosDeUnEstado(cantidad, monto)
            for estado, cantidad, monto in filas
        }


__all__ = ["ConsultasDeCobranzaPostgres"]
