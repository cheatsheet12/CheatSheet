"""El detalle de cobranza del período: la lectura que alimenta los gráficos del tablero.

Lo que se prueba con un doble es lo que el caso de uso garantiza por sí mismo: que `estados`
**no interviene** (es del listado, igual que en `metricas`) y que `por_estado` sale siempre en el
orden de declaración de `EstadoCobro`, para que el gráfico tenga un orden estable sin que
`reporting` nombre el enum. Que las sumas salgan bien se prueba contra el motor, en
`tests/integracion/test_cobranza_del_periodo_postgres.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, tzinfo
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from cheatsheet.contexts.payments.application.cobranza_del_periodo import (
    CobrosDeUnEstado,
    DetalleDeCobranza,
    DetalleDeCobranzaDelPeriodo,
)
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro
from cheatsheet.contexts.payments.domain.cobro import EstadoCobro

pytestmark = pytest.mark.asyncio

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


class ConsultasFalsas:
    """Devuelve lo que se le puso, y anota con qué filtros y zona se lo pidieron."""

    def __init__(self) -> None:
        self.pedidos_por_dia: list[tuple[FiltrosDeCobro, tzinfo]] = []
        self.pedidos_por_estado: list[FiltrosDeCobro] = []
        # A propósito en un orden que no es el del enum.
        self.estados: dict[EstadoCobro, CobrosDeUnEstado] = {
            EstadoCobro.VENCIDO: CobrosDeUnEstado(1, Decimal("250.00")),
            EstadoCobro.APROBADO: CobrosDeUnEstado(2, Decimal("1000.00")),
        }

    async def cobrado_por_dia(self, filtros: FiltrosDeCobro, zona: tzinfo) -> dict[date, Decimal]:
        self.pedidos_por_dia.append((filtros, zona))
        return {date(2026, 3, 31): Decimal("0.30")}

    async def por_estado(self, filtros: FiltrosDeCobro) -> dict[EstadoCobro, CobrosDeUnEstado]:
        self.pedidos_por_estado.append(filtros)
        return self.estados


def _filtros() -> FiltrosDeCobro:
    return FiltrosDeCobro(
        desde=datetime(2026, 3, 1, tzinfo=ZONA),
        hasta=datetime(2026, 3, 31, 23, 59, tzinfo=ZONA),
        estados=(EstadoCobro.PENDIENTE,),
    )


async def test_pasa_los_filtros_sin_estados_y_la_zona_al_puerto() -> None:
    consultas = ConsultasFalsas()
    filtros = _filtros()

    await DetalleDeCobranzaDelPeriodo(consultas).ejecutar(filtros=filtros, zona=ZONA)

    esperado = FiltrosDeCobro(desde=filtros.desde, hasta=filtros.hasta, estados=())
    assert consultas.pedidos_por_dia == [(esperado, ZONA)]
    assert consultas.pedidos_por_estado == [esperado]


async def test_devuelve_el_cobrado_por_dia_tal_cual_lo_dio_el_puerto() -> None:
    detalle = await DetalleDeCobranzaDelPeriodo(ConsultasFalsas()).ejecutar(
        filtros=_filtros(), zona=ZONA
    )

    assert isinstance(detalle, DetalleDeCobranza)
    assert detalle.cobrado_por_dia == {date(2026, 3, 31): Decimal("0.30")}


async def test_por_estado_sale_en_el_orden_de_declaracion_de_estado_cobro() -> None:
    detalle = await DetalleDeCobranzaDelPeriodo(ConsultasFalsas()).ejecutar(
        filtros=_filtros(), zona=UTC
    )

    declarados = list(EstadoCobro)
    assert list(detalle.por_estado) == [EstadoCobro.APROBADO, EstadoCobro.VENCIDO]
    assert list(detalle.por_estado) == sorted(detalle.por_estado, key=declarados.index)
    assert detalle.por_estado[EstadoCobro.APROBADO] == CobrosDeUnEstado(2, Decimal("1000.00"))
