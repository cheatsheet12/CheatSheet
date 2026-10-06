"""The simulated OAuth provider — and, above all, where it refuses to run.

Its value is that HU-E1-01 RN-02 becomes reachable without a Google client. Its danger is
obvious, so the test that matters most here is the one asserting it cannot be built in
production.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from cheatsheet.contexts.identity.application.errors import OAuthFallido
from cheatsheet.contexts.identity.infrastructure.ensamblado import proveedor_google
from cheatsheet.contexts.identity.infrastructure.oauth_falso import (
    PREFIJO,
    ProveedorOAuthSimulado,
)
from cheatsheet.contexts.identity.infrastructure.oauth_google import ProveedorOAuthGoogle
from cheatsheet.platform.settings import Entorno

from tests.conftest import settings_de_prueba


def _simulado(entorno: Entorno = Entorno.TEST) -> ProveedorOAuthSimulado:
    return ProveedorOAuthSimulado(url_base_de_la_app="http://localhost:3000", entorno=entorno)


@pytest.mark.asyncio
async def test_el_codigo_simulado_devuelve_el_perfil_de_ese_email():
    perfil = await _simulado().perfil_desde_codigo(f"{PREFIJO}ana.perez@empresa.com")

    assert str(perfil.email) == "ana.perez@empresa.com"
    assert perfil.nombre == "Ana Perez"


@pytest.mark.asyncio
async def test_un_codigo_sin_el_prefijo_se_rechaza():
    """A real Google code never looks like this, and must not be accepted by accident."""
    with pytest.raises(OAuthFallido):
        await _simulado().perfil_desde_codigo("4/0AY0e-g7...")


@pytest.mark.asyncio
async def test_un_email_invalido_en_el_codigo_se_rechaza():
    with pytest.raises(OAuthFallido):
        await _simulado().perfil_desde_codigo(f"{PREFIJO}no-es-un-email")


def test_la_url_simulada_apunta_al_callback_de_la_propia_app():
    url = _simulado().url_de_autorizacion("un-state")

    assert url.startswith("http://localhost:3000/api/auth/google/callback?")
    assert "state=un-state" in url


def test_no_se_puede_construir_en_produccion():
    """Not a warning: a refusal, at construction, before anything can use it."""
    with pytest.raises(RuntimeError, match="produccion"):
        _simulado(Entorno.PRODUCTION)


def test_sin_credenciales_fuera_de_produccion_se_arma_el_simulado():
    proveedor = proveedor_google(settings_de_prueba())

    assert isinstance(proveedor, ProveedorOAuthSimulado)


def test_sin_credenciales_en_produccion_no_hay_proveedor():
    """The endpoint refuses; the process still starts, because eleven other contexts
    have nothing to do with Google."""
    assert proveedor_google(settings_de_prueba(Entorno.PRODUCTION)) is None


def test_con_credenciales_se_arma_el_adaptador_real():
    settings = replace(
        settings_de_prueba(),
        google_oauth_client_id="un-client-id",
        google_oauth_client_secret="fake-secret-for-tests",
        google_oauth_redirect_uri="https://app.cheatsheet.test/callback",
    )

    assert isinstance(proveedor_google(settings), ProveedorOAuthGoogle)
