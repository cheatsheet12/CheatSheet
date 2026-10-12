"""Google Sheets write-back contracts without a network connection."""

from __future__ import annotations

import json

import httpx
import pytest
from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    PermisosDePlanillaInsuficientes,
    ProveedorDePlanillaNoDisponible,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import FilaParaEscribir
from cheatsheet.contexts.spreadsheet_sync.infrastructure import escritura as modulo

pytestmark = pytest.mark.asyncio


async def test_real_writer_rejects_missing_company_access_token() -> None:
    with pytest.raises(ValueError, match="token"):
        modulo.EscrituraEnGoogleSheets(modulo.ConfiguracionDeEscritura(token=""))


async def test_write_back_sends_every_record_beyond_the_first_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 501st record must not disappear while the link records a successful write."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {
                            "properties": {"sheetId": 23, "title": "CheatSheet (no editar)"},
                            "protectedRanges": [{"range": {"sheetId": 23}}],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"updatedCells": 5})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        modulo.httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    rows = tuple(
        FilaParaEscribir(valores=(f"Customer {number}", "", "", "", "PANEL"))
        for number in range(501)
    )

    await modulo.EscrituraEnGoogleSheets(
        modulo.ConfiguracionDeEscritura(token="test-token")
    ).escribir(identificador="sheet-123", hoja="CheatSheet (no editar)", filas=rows)

    sent = [
        value
        for request in requests
        if request.method == "PUT"
        for value in json.loads(request.content)["values"]
    ]
    assert [value[0] for value in sent if value[0].startswith("Customer ")] == [
        f"Customer {number}" for number in range(501)
    ]


async def test_first_write_creates_and_protects_own_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new link has no system sheet; writing must create it before values.update."""
    requests: list[httpx.Request] = []
    created = False

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal created
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"sheets": [{"properties": {"title": "Clientes"}}]})
        if request.url.path.endswith(":batchUpdate"):
            body = json.loads(request.content)
            if "addSheet" in body["requests"][0]:
                created = True
                return httpx.Response(
                    200, json={"replies": [{"addSheet": {"properties": {"sheetId": 23}}}]}
                )
            return httpx.Response(200, json={"replies": [{}]})
        return httpx.Response(200 if created else 404, json={"updatedCells": 5})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        modulo.httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    rows = (FilaParaEscribir(valores=("Test customer", "", "", "", "PANEL")),)

    await modulo.EscrituraEnGoogleSheets(
        modulo.ConfiguracionDeEscritura(token="test-token")
    ).escribir(identificador="sheet-123", hoja="CheatSheet (no editar)", filas=rows)

    updates = [
        json.loads(request.content)
        for request in requests
        if request.url.path.endswith(":batchUpdate")
    ]
    assert any("addSheet" in action for body in updates for action in body["requests"])
    assert any("addProtectedRange" in action for body in updates for action in body["requests"])
    assert requests[-1].method == "PUT"


async def test_revoked_sheet_access_does_not_report_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = httpx.AsyncClient
    monkeypatch.setattr(
        modulo.httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(403)), **kwargs
        ),
    )
    rows = (FilaParaEscribir(valores=("Customer", "", "", "", "PANEL")),)
    writer = modulo.EscrituraEnGoogleSheets(modulo.ConfiguracionDeEscritura(token="test-token"))

    with pytest.raises(PermisosDePlanillaInsuficientes):
        await writer.escribir(identificador="sheet-123", hoja="CheatSheet", filas=rows)


async def test_second_batch_failure_is_not_reported_as_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal writes
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {
                            "properties": {"sheetId": 23, "title": "CheatSheet"},
                            "protectedRanges": [{"range": {"sheetId": 23}}],
                        }
                    ]
                },
            )
        if request.method == "PUT":
            writes += 1
            if writes == 2:
                return httpx.Response(400, json={"error": "invalid range"})
        return httpx.Response(200, json={})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        modulo.httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    rows = tuple(
        FilaParaEscribir(valores=(str(index), "", "", "", "PANEL")) for index in range(501)
    )

    with pytest.raises(ProveedorDePlanillaNoDisponible):
        await modulo.EscrituraEnGoogleSheets(
            modulo.ConfiguracionDeEscritura(token="test-token")
        ).escribir(identificador="sheet-123", hoja="CheatSheet", filas=rows)
    assert writes == 2
