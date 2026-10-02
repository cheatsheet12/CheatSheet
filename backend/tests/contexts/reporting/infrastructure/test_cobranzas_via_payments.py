"""`CobranzasViaPayments`: reporting hereda la definicion de «cobrado» de `payments` (D91).

El ACL no recalcula nada: pide las mismas metricas que ve PAN-COB-01, asi que cuando `payments`
pasa a medir «cobrado» por fecha de pago, el tablero cambia de significado sin tocar una linea
de reporting. La columna `pagado` de las filas sale de `fecha_pago`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, tzinfo
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro, MetricasDeCobros
from cheatsheet.contexts.payments.domain.cobro import EstadoCobro
from cheatsheet.contexts.reporting.application.ports import CobrosPorEstado
from cheatsheet.contexts.reporting.domain.reporte import Periodo
from cheatsheet.contexts.reporting.infrastructure.acl import (
    ZONA_DEL_REPORTE,
    CobranzasViaPayments,
)

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


class _CantidadYMonto:
    """El valor de `por_estado`: el ACL lee `cantidad` y `monto` por atributo."""

    def __init__(self, cantidad: int, monto: str) -> None:
        self.cantidad = cantidad
        self.monto = Decimal(monto)


class ConsultasFalsas:
    def __init__(self, por_dia: dict[date, Decimal] | None = None) -> None:
        self.por_dia = por_dia or {}
        self.pedidos: list[tuple[FiltrosDeCobro, tzinfo]] = []

    async def cobrado_por_dia(self, filtros: FiltrosDeCobro, zona: tzinfo) -> dict[date, Decimal]:
        self.pedidos.append((filtros, zona))
        return self.por_dia

    async def por_estado(self, filtros: FiltrosDeCobro) -> dict[EstadoCobro, _CantidadYMonto]:
        del filtros
        return {
            EstadoCobro.APROBADO: _CantidadYMonto(8, "120000.00"),
            EstadoCobro.PENDIENTE: _CantidadYMonto(3, "30000.50"),
        }


def _acl(cobros: CobrosFalsos, consultas: ConsultasFalsas | None = None) -> CobranzasViaPayments:
    # El ACL solo lee atributos; el doble no necesita ser un `PortRepositorioCobro` completo.
    puerto: Any = cobros
    detalle: Any = consultas or ConsultasFalsas()
    return CobranzasViaPayments(puerto, detalle)


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


async def test_los_totales_traen_la_tasa_de_cobro_que_calcula_payments_sin_recalcularla() -> None:
    totales = await _acl(CobrosFalsos()).totales(Periodo(date(2026, 9, 1), date(2026, 9, 30)))

    # 1000 de lo creado cobrado sobre 1750 creado: 57,14. Recalcularla con el `cobrado` (3000)
    # daria otra cosa.
    assert totales.tasa_de_cobro == Decimal("57.14")


class TestDetalle:
    async def test_agrupa_los_dias_en_semanas_iso_con_la_etiqueta_de_la_facturacion(self) -> None:
        consultas = ConsultasFalsas(
            {
                date(2026, 3, 1): Decimal("100.00"),  # domingo: semana 9
                date(2026, 3, 2): Decimal("50.00"),  # lunes: semana 10
                date(2026, 3, 8): Decimal("25.00"),  # domingo: semana 10
            }
        )

        detalle = await _acl(CobrosFalsos(), consultas).detalle(Periodo.del_mes(2026, 3))

        assert detalle.por_semana == {
            "2026-W09": Decimal("100.00"),
            "2026-W10": Decimal("75.00"),
        }

    async def test_las_semanas_salen_en_orden_aunque_los_dias_lleguen_desordenados(self) -> None:
        consultas = ConsultasFalsas(
            {
                date(2026, 3, 16): Decimal("30.00"),  # semana 12
                date(2026, 3, 2): Decimal("10.00"),  # semana 10
                date(2026, 3, 9): Decimal("20.00"),  # semana 11
            }
        )

        detalle = await _acl(CobrosFalsos(), consultas).detalle(Periodo.del_mes(2026, 3))

        # El gráfico dibuja las barras en el orden del diccionario.
        assert list(detalle.por_semana) == ["2026-W10", "2026-W11", "2026-W12"]

    async def test_el_cambio_de_anio_usa_el_anio_iso(self) -> None:
        consultas = ConsultasFalsas(
            {
                date(2025, 12, 31): Decimal("1.00"),  # ya es semana 1 de 2026
                date(2026, 12, 31): Decimal("2.00"),  # 2026 tiene 53 semanas
                date(2027, 1, 1): Decimal("3.00"),  # todavia semana 53 de 2026
                date(2027, 1, 4): Decimal("4.00"),
            }
        )

        detalle = await _acl(CobrosFalsos(), consultas).detalle(
            Periodo(date(2025, 12, 1), date(2027, 1, 31))
        )

        assert detalle.por_semana == {
            "2026-W01": Decimal("1.00"),
            "2026-W53": Decimal("5.00"),
            "2027-W01": Decimal("4.00"),
        }

    async def test_los_dias_negativos_restan_y_la_suma_es_decimal_exacta(self) -> None:
        consultas = ConsultasFalsas(
            {
                date(2026, 3, 2): Decimal("0.10"),
                date(2026, 3, 3): Decimal("0.20"),
                date(2026, 3, 4): Decimal("-0.50"),
                date(2026, 3, 9): Decimal("-10.00"),
            }
        )

        detalle = await _acl(CobrosFalsos(), consultas).detalle(Periodo.del_mes(2026, 3))

        assert detalle.por_semana == {
            "2026-W10": Decimal("-0.20"),
            "2026-W11": Decimal("-10.00"),
        }
        assert all(isinstance(monto, Decimal) for monto in detalle.por_semana.values())

    async def test_pide_los_limites_del_periodo_en_la_zona_del_reporte(self) -> None:
        consultas = ConsultasFalsas()

        await _acl(CobrosFalsos(), consultas).detalle(Periodo(date(2026, 3, 1), date(2026, 3, 31)))

        [(filtros, zona)] = consultas.pedidos
        assert zona is ZONA_DEL_REPORTE
        assert filtros.desde == datetime(2026, 3, 1, 0, 0, tzinfo=ZONA_DEL_REPORTE)
        assert filtros.hasta == datetime(2026, 3, 31, 23, 59, 59, 999999, tzinfo=ZONA_DEL_REPORTE)
        assert filtros.estados == ()

    async def test_traduce_los_estados_a_su_nombre_en_texto(self) -> None:
        detalle = await _acl(CobrosFalsos()).detalle(Periodo.del_mes(2026, 3))

        assert detalle.por_estado == {
            "APROBADO": CobrosPorEstado(cantidad=8, monto=Decimal("120000.00")),
            "PENDIENTE": CobrosPorEstado(cantidad=3, monto=Decimal("30000.50")),
        }
