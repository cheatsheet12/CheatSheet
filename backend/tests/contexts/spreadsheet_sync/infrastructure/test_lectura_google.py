"""Google Sheets values are read from the selected source sheet, never the write-back tab."""

from __future__ import annotations

from urllib.parse import unquote

import httpx
import pytest
from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    PermisosDePlanillaInsuficientes,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure import google_sheets as modulo

pytestmark = pytest.mark.asyncio


def _proveedor() -> modulo.ProveedorGoogleSheets:
    return modulo.ProveedorGoogleSheets(
        modulo.ConfiguracionGoogleSheets("client-id", "client-secret", "https://app.test/callback")
    )


async def test_reads_source_rows_with_sheet_numbers_and_formatted_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ranges: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer company-token"
        if request.url.path.endswith("/document-1"):
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {
                            "properties": {
                                "title": "Clientes 2026",
                                "gridProperties": {"rowCount": 4},
                            }
                        }
                    ]
                },
            )
        ranges.append(unquote(request.url.path))
        assert request.url.params["valueRenderOption"] == "FORMATTED_VALUE"
        return httpx.Response(
            200,
            json={"values": [["Nombre", "CUIT"], [], ["Ana", "030123"], ["Luis", "30712345671"]]},
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )

    leida = await _proveedor().leer_hoja(
        token="company-token", identificador="document-1", hoja="Clientes 2026"
    )

    assert leida.columnas == ("Nombre", "CUIT")
    assert [(fila.numero, fila.celdas) for fila in leida.filas] == [
        (3, {"Nombre": "Ana", "CUIT": "030123"}),
        (4, {"Nombre": "Luis", "CUIT": "30712345671"}),
    ]
    assert ranges == ["/v4/spreadsheets/document-1/values/'Clientes 2026'!1:4"]


async def test_read_rejects_revoked_sheet_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(403)), **kwargs
        ),
    )

    with pytest.raises(PermisosDePlanillaInsuficientes):
        await _proveedor().leer_hoja(
            token="revoked", identificador="document-1", hoja="Clientes 2026"
        )


async def test_sheet_name_with_url_special_characters_stays_in_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rutas: list[bytes] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/document-1"):
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {
                            "properties": {
                                "title": "Clientes #1/2026",
                                "gridProperties": {"rowCount": 2},
                            }
                        }
                    ]
                },
            )
        rutas.append(request.url.raw_path)
        return httpx.Response(200, json={"values": [["Nombre"], ["Ana"]]})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )

    leida = await _proveedor().leer_hoja(
        token="company-token", identificador="document-1", hoja="Clientes #1/2026"
    )

    assert leida.filas[0].celdas["Nombre"] == "Ana"
    assert len(rutas) == 1
    assert b"%23" in rutas[0]
    assert b"%2F" in rutas[0]


async def test_reads_second_batch_without_resetting_google_row_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rangos: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/document-1"):
            return httpx.Response(
                200,
                json={
                    "sheets": [
                        {"properties": {"title": "Clientes", "gridProperties": {"rowCount": 502}}}
                    ]
                },
            )
        rangos.append(unquote(request.url.path))
        if "!1:500" in rangos[-1]:
            return httpx.Response(200, json={"values": [["Nombre"], *[[""] for _ in range(499)]]})
        return httpx.Response(200, json={"values": [["Ana"], ["Luis"]]})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )

    leida = await _proveedor().leer_hoja(
        token="company-token", identificador="document-1", hoja="Clientes"
    )

    assert [fila.numero for fila in leida.filas] == [501, 502]
    assert len(rangos) == 2
