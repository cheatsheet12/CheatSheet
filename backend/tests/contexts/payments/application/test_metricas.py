"""El encabezado de PAN-COB-01: qué mide cada número (D91, ADR-0010).

`cobrado` se mide por **fecha de pago**; `pendiente` y `en_mora` por fecha de creación. La
tasa de cobro es otra cosa que «cobrado»: es la cohorte de lo *creado* en el período, y por eso
tiene su propio numerador (`cobrado_de_lo_creado`) y no puede pasar de 100 %.
"""

from __future__ import annotations

from decimal import Decimal

from cheatsheet.contexts.payments.application.ports import MetricasDeCobros


def _metricas(*, cobrado: str, pendiente: str, en_mora: str, de_lo_creado: str) -> MetricasDeCobros:
    return MetricasDeCobros(
        cobrado=Decimal(cobrado),
        pendiente=Decimal(pendiente),
        en_mora=Decimal(en_mora),
        cobrado_de_lo_creado=Decimal(de_lo_creado),
    )


def test_la_tasa_se_calcula_con_lo_cobrado_de_lo_creado_y_no_con_cobrado() -> None:
    metricas = _metricas(
        cobrado="9999.00", pendiente="500.00", en_mora="250.00", de_lo_creado="1000.00"
    )

    # 1000 sobre 1750: el «cobrado» del encabezado (9999) no participa.
    assert metricas.tasa_de_cobro == Decimal("57.14")


def test_la_tasa_no_pasa_de_cien_aunque_se_cobre_mas_de_lo_creado() -> None:
    """Se cobró en el período mucho de lo creado antes: el encabezado lo muestra y la tasa no."""
    metricas = _metricas(
        cobrado="5000.00", pendiente="0.00", en_mora="0.00", de_lo_creado="1000.00"
    )

    assert metricas.tasa_de_cobro == Decimal("100.00")


def test_un_periodo_vacio_tiene_tasa_cero() -> None:
    metricas = _metricas(cobrado="0.00", pendiente="0.00", en_mora="0.00", de_lo_creado="0.00")

    assert metricas.tasa_de_cobro == Decimal("0.00")


def test_un_periodo_con_cobrado_por_pagos_viejos_y_nada_creado_tiene_tasa_cero() -> None:
    metricas = _metricas(cobrado="800.00", pendiente="0.00", en_mora="0.00", de_lo_creado="0.00")

    assert metricas.tasa_de_cobro == Decimal("0.00")


def test_la_tasa_redondea_half_up_a_dos_decimales() -> None:
    """Un octavo de punto porcentual (0.125) sube a 0.13; el default de Python daria 0.12."""
    metricas = _metricas(cobrado="0", pendiente="799.00", en_mora="0.00", de_lo_creado="1.00")

    assert metricas.tasa_de_cobro == Decimal("0.13")


def test_los_importes_son_decimal_de_punta_a_punta() -> None:
    """`0.10 + 0.20` da `0.30` y nunca `0.30000000000000004`."""
    metricas = _metricas(cobrado="0.10", pendiente="0.20", en_mora="0.00", de_lo_creado="0.10")

    assert metricas.cobrado + metricas.pendiente == Decimal("0.30")
    assert isinstance(metricas.tasa_de_cobro, Decimal)
    # 0.10 sobre 0.30 = 33.33...
    assert metricas.tasa_de_cobro == Decimal("33.33")


def test_un_cobrado_negativo_no_altera_la_tasa() -> None:
    """RN-11: un período que devolvió más de lo que cobró da `cobrado` negativo (es lo que pasó
    con la caja); la tasa sale de lo creado y **no** de ese número."""
    metricas = _metricas(
        cobrado="-300.00", pendiente="500.00", en_mora="0.00", de_lo_creado="500.00"
    )

    assert metricas.cobrado == Decimal("-300.00")
    assert metricas.tasa_de_cobro == Decimal("50.00")
