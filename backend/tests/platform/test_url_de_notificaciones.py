"""`API_URL_PUBLICA` is what every MercadoPago link tells MercadoPago to call back.

With the real adapter and no public URL, links would be created, paid, and never reported:
the cobro stays pending with the money already in the account. That has to stop the process
at boot, not show up weeks later in a reconciliation.
"""

from __future__ import annotations

import pytest
from cheatsheet.platform.settings import (
    AdaptadorDeMercadoPago,
    ConfiguracionFaltante,
    _url_de_notificaciones,
)


@pytest.fixture(autouse=True)
def _sin_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_URL_PUBLICA", raising=False)


def test_mercadopago_real_sin_url_publica_no_arranca() -> None:
    with pytest.raises(ConfiguracionFaltante, match="API_URL_PUBLICA"):
        _url_de_notificaciones(AdaptadorDeMercadoPago.MERCADOPAGO)


def test_la_url_publica_se_guarda_sin_barra_final(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_URL_PUBLICA", "https://api.ejemplo.test/")

    url = _url_de_notificaciones(AdaptadorDeMercadoPago.MERCADOPAGO)

    assert url == "https://api.ejemplo.test"


def test_con_el_simulador_la_url_publica_es_opcional() -> None:
    assert _url_de_notificaciones(AdaptadorDeMercadoPago.SIMULADO) == ""
