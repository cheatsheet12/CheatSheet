"""El detalle de cobranza de un período: lo que dibujan los gráficos del tablero (HU-E10-01).

Es la lectura **de los gráficos**, y comparte su definición con `metricas` (ADR-0010, punto 6):

- `cobrado_por_dia` es lo cobrado por **día local de la fecha de pago**, menos lo devuelto por
  **día local de la fecha de devolución**. La suma de los días es el `cobrado` del encabezado.
  Un día puede dar negativo: es lo que pasó con la caja.
- `por_estado` es lo **creado** en el período, agrupado por su estado actual. La fila `PENDIENTE`
  es el `pendiente` del encabezado, la `VENCIDO` es el `en_mora`, y la suma de los tres estados
  pagados es `cobrado_de_lo_creado`.

Vive en un módulo propio y no en `ports.py` ni en `cobros.py` porque los dos están al borde del
tope de líneas. Es **sólo lectura**: ningún método de acá cambia un cobro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, tzinfo
from decimal import Decimal
from typing import Protocol

from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro
from cheatsheet.contexts.payments.domain.cobro import EstadoCobro


@dataclass(frozen=True, slots=True)
class CobrosDeUnEstado:
    """Cuántos cobros creados en el período están hoy en un estado, y por cuánto."""

    cantidad: int
    monto: Decimal


@dataclass(frozen=True, slots=True)
class DetalleDeCobranza:
    """Las dos series de los gráficos de cobranza."""

    #: Neto por día local: pagos del día menos devoluciones del día. Sólo trae días con
    #: movimiento.
    cobrado_por_dia: dict[date, Decimal]
    #: En el orden de declaración de `EstadoCobro`. Sólo trae estados con cobros.
    por_estado: dict[EstadoCobro, CobrosDeUnEstado]


class PortConsultasDeCobranza(Protocol):
    """Las agregaciones del detalle. **Sólo lectura**, y hechas en la base."""

    async def cobrado_por_dia(self, filtros: FiltrosDeCobro, zona: tzinfo) -> dict[date, Decimal]:
        """Neto por día local en `zona`, con la misma definición que `metricas.cobrado`."""
        ...

    async def por_estado(self, filtros: FiltrosDeCobro) -> dict[EstadoCobro, CobrosDeUnEstado]:
        """Lo creado en el período, por su estado actual."""
        ...


class DetalleDeCobranzaDelPeriodo:
    """Pide las dos series con los mismos filtros y las entrega en un orden estable."""

    def __init__(self, consultas: PortConsultasDeCobranza) -> None:
        self._consultas = consultas

    async def ejecutar(self, *, filtros: FiltrosDeCobro, zona: tzinfo) -> DetalleDeCobranza:
        # `estados` es del listado y no de la cobranza: filtrarlo acá haría que los gráficos
        # dejaran de cuadrar con el encabezado, que tampoco lo mira.
        efectivos = FiltrosDeCobro(desde=filtros.desde, hasta=filtros.hasta, estados=())
        por_dia = await self._consultas.cobrado_por_dia(efectivos, zona)
        por_estado = await self._consultas.por_estado(efectivos)
        return DetalleDeCobranza(
            cobrado_por_dia=por_dia,
            por_estado={
                estado: por_estado[estado] for estado in EstadoCobro if estado in por_estado
            },
        )


__all__ = [
    "CobrosDeUnEstado",
    "DetalleDeCobranza",
    "DetalleDeCobranzaDelPeriodo",
    "PortConsultasDeCobranza",
]
