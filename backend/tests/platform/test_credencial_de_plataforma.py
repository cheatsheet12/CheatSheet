"""`ARCA_CREDENCIAL_PLATAFORMA` (ADR-0014): sin ella, con ARCA real, no se llega a nadie."""

from __future__ import annotations

import base64

import pytest
from cheatsheet.platform.settings import (
    AdaptadorDeArca,
    ConfiguracionFaltante,
    _credencial_de_plataforma,
)


@pytest.fixture(autouse=True)
def _sin_credencial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCA_CREDENCIAL_PLATAFORMA", raising=False)


def test_arca_real_sin_credencial_de_plataforma_no_arranca() -> None:
    with pytest.raises(ConfiguracionFaltante, match="ARCA_CREDENCIAL_PLATAFORMA"):
        _credencial_de_plataforma(AdaptadorDeArca.ARCA)


def test_la_credencial_se_lee_de_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    pem = b"-----BEGIN CERTIFICATE-----\n...\n-----BEGIN PRIVATE KEY-----\n...\n"
    monkeypatch.setenv("ARCA_CREDENCIAL_PLATAFORMA", base64.b64encode(pem).decode())

    assert _credencial_de_plataforma(AdaptadorDeArca.ARCA) == pem


def test_una_credencial_que_no_es_base64_se_rechaza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCA_CREDENCIAL_PLATAFORMA", "-----BEGIN CERTIFICATE-----")

    with pytest.raises(ConfiguracionFaltante, match="base64"):
        _credencial_de_plataforma(AdaptadorDeArca.ARCA)


def test_con_el_simulador_no_hace_falta() -> None:
    assert _credencial_de_plataforma(AdaptadorDeArca.SIMULADO) == b""
