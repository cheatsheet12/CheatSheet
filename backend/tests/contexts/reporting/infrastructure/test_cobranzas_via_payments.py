"""`CobranzasViaPayments`: reporting hereda la definicion de «cobrado» de `payments` (D91).

El ACL no recalcula nada: pide las mismas metricas que ve PAN-COB-01, asi que cuando `payments`
pasa a medir «cobrado» por fecha de pago, el tablero cambia de significado sin tocar una linea
de reporting. La columna `pagado` de las filas sale de `fecha_pago`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro, MetricasDeCobros
from cheatsheet.contexts.reporting.domain.reporte import Periodo
from cheatsheet.contexts.reporting.infrastructure.acl import CobranzasViaPayments

pytestmark = pytest.mark.asyncio


class CobrosFalsos:
    def __init__(self, cobros: list[SimpleNamespace] | None = None) -> None:
        self.cobros = cobros or []
        self.filtros_de_metricas: list[FiltrosDeCobro] = []

    async def metricas(self, filtros: FiltrosDeCobro) -> MetricasDeCobros:
        self.filtros_de_metricas.append(filtros)
        return MetricasDeCobros(
            cobrado=Decimal("3000.00"),
            pendiente=Decimal("500.00"),
            en_mora=Decimal("250.00"),
            cobrado_de_lo_creado=Decimal("1000.00"),
        )

    async def listar(self, filtros: FiltrosDeCobro) -> list[SimpleNamespace]:
        del filtros
        return self.cobros


def _acl(cobros: CobrosFalsos) -> CobranzasViaPayments:
    # El ACL solo lee atributos; el doble no necesita ser un `PortRepositorioCobro` completo.
    puerto: Any = cobros
    return CobranzasViaPayments(puerto)


async def test_los_totales_toman_el_cobrado_por_fecha_de_pago_que_calcula_payments() -> None:
    cobros = CobrosFalsos()

    totales = await _acl(cobros).totales(Periodo(date(2026, 9, 1), date(2026, 9, 30)))

    # El «cobrado» viaja tal cual (por fecha de pago); no se recalcula ni se toca la tasa.
    assert totales.cobrado == Decimal("3000.00")
    assert totales.pendiente == Decimal("500.00")
    assert totales.en_mora == Decimal("250.00")
    assert len(cobros.filtros_de_metricas) == 1
    assert cobros.filtros_de_metricas[0].estados == ()


async def test_las_filas_muestran_la_fecha_de_pago_y_vacio_si_no_se_pago() -> None:
    pagado = SimpleNamespace(
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        descripcion="Consulta",
        monto=Decimal("1210.00"),
        estado=SimpleNamespace(value="APROBADO"),
        vence_el=datetime(2026, 9, 20, tzinfo=UTC),
        fecha_pago=datetime(2026, 9, 3, 15, 0, tzinfo=UTC),
    )
    abierto = SimpleNamespace(
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        descripcion="Otra",
        monto=Decimal("100.00"),
        estado=SimpleNamespace(value="PENDIENTE"),
        vence_el=datetime(2026, 10, 1, tzinfo=UTC),
        fecha_pago=None,
    )

    filas = await _acl(CobrosFalsos([pagado, abierto])).filas(
        Periodo(date(2026, 9, 1), date(2026, 9, 30))
    )

    assert [fila.valores["pagado"] for fila in filas] == ["03/09/2026", ""]
