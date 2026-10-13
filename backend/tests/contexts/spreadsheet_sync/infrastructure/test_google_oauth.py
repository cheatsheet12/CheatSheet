"""Google OAuth token exchange contracts without a network connection."""

from __future__ import annotations

import httpx
import pytest
from cheatsheet.contexts.integrations.application.credenciales_oauth import CredencialOAuthRevocada
from cheatsheet.contexts.spreadsheet_sync.application.errors import ProveedorDePlanillaNoDisponible
from cheatsheet.contexts.spreadsheet_sync.infrastructure import google_sheets as modulo

pytestmark = pytest.mark.asyncio


async def test_exchange_keeps_refresh_token_for_scheduled_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An access token alone expires before an unattended write-back can run."""

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/token"
        return httpx.Response(
            200,
            json={
                "access_token": "short-lived",
                "refresh_token": "long-lived",
                "expires_in": 3600,
            },
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    provider = modulo.ProveedorGoogleSheets(
        modulo.ConfiguracionGoogleSheets("client-id", "client-secret", "https://app.test/callback")
    )

    tokens = await provider.canjear_codigo("authorization-code")

    assert tokens.acceso == "short-lived"
    assert tokens.renovacion == "long-lived"


async def test_refresh_credential_yields_access_for_unattended_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert b"grant_type=refresh_token" in request.content
        assert b"refresh_token=long-lived" in request.content
        return httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    provider = modulo.ProveedorGoogleSheets(
        modulo.ConfiguracionGoogleSheets("client-id", "client-secret", "https://app.test/callback")
    )

    assert await provider.renovar(b"long-lived") == "new-access"


async def test_revoked_refresh_token_requires_reconnection(monkeypatch: pytest.MonkeyPatch) -> None:
    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(400, json={"error": "invalid_grant"})
            ),
            **kwargs,
        ),
    )
    provider = modulo.ProveedorGoogleSheets(
        modulo.ConfiguracionGoogleSheets("client-id", "client-secret", "https://app.test/callback")
    )

    with pytest.raises(CredencialOAuthRevocada):
        await provider.renovar(b"revoked")


async def test_non_native_spreadsheet_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    400,
                    json={
                        "error": {
                            "code": 400,
                            "message": "This operation is not supported for this document",
                            "status": "FAILED_PRECONDITION",
                        }
                    },
                )
            ),
            **kwargs,
        ),
    )
    provider = modulo.ProveedorGoogleSheets(
        modulo.ConfiguracionGoogleSheets("client-id", "client-secret", "https://app.test/callback")
    )

    with pytest.raises(ProveedorDePlanillaNoDisponible, match="Hoja de cálculo de Google"):
        await provider.describir_documento(token="token", identificador="document-1")
