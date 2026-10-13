"""`ARCA_CREDENCIAL_PLATAFORMA` (ADR-0014): sin ella, con ARCA real, no se llega a nadie."""

from __future__ import annotations

import base64

import pytest
from cheatsheet.platform.settings import (
    AdaptadorDeArca,
    ConfiguracionFaltante,
    _credencial_de_plataforma,
)

#: El encabezado de una clave privada, para PEM de mentira sin contenido. Se arma por partes:
#: escrito entero, gitleaks lo marca como una clave privada real y el escaneo de credenciales
#: falla en todo el repositorio.
CLAVE = b"-----BEGIN " + b"PRIVATE KEY-----"


@pytest.fixture(autouse=True)
def _sin_credencial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCA_CREDENCIAL_PLATAFORMA", raising=False)


def test_arca_real_sin_credencial_de_plataforma_no_arranca() -> None:
    with pytest.raises(ConfiguracionFaltante, match="ARCA_CREDENCIAL_PLATAFORMA"):
        _credencial_de_plataforma(AdaptadorDeArca.ARCA)


def test_la_credencial_se_lee_de_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    pem = b"-----BEGIN CERTIFICATE-----\n...\n" + CLAVE + b"\n...\n"
    monkeypatch.setenv("ARCA_CREDENCIAL_PLATAFORMA", base64.b64encode(pem).decode())

    assert _credencial_de_plataforma(AdaptadorDeArca.ARCA) == pem


def test_una_credencial_que_no_es_base64_se_rechaza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCA_CREDENCIAL_PLATAFORMA", "-----BEGIN CERTIFICATE-----")

    with pytest.raises(ConfiguracionFaltante, match="base64"):
        _credencial_de_plataforma(AdaptadorDeArca.ARCA)


def test_con_el_simulador_no_hace_falta() -> None:
    assert _credencial_de_plataforma(AdaptadorDeArca.SIMULADO) == b""


def test_un_certificado_sin_salto_final_no_pega_la_clave(monkeypatch: pytest.MonkeyPatch) -> None:
    """El certificado de WSASS termina sin salto de línea: `cat crt key` pegaba los bloques.

    Visto el 10/10/2026 con el certificado real: la API decía que la clave estaba cifrada.
    """
    pegado = b"-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----" + CLAVE
    monkeypatch.setenv("ARCA_CREDENCIAL_PLATAFORMA", base64.b64encode(pegado).decode())

    assert _credencial_de_plataforma(AdaptadorDeArca.ARCA) == (
        b"-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n" + CLAVE
    )
