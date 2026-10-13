"""Writing back into the company's workbook (HU-E3-07), and reading what to write.

Two adapters and one hard rule between them: **what we write goes into our own sheet, and
nothing else**. That is RN-02 and the anti-loop mechanism of ADR-007 — a system that wrote
into the sheet it also reads would ingest its own output on the next sweep, forever.

`EscrituraEnGoogleSheets` can name exactly one sheet per call and has no delete. The sheet
it is given is always the one this context created, whose name lives on the link. There is
no code path that reaches the company's own sheet, which is a stronger statement than a
check that could be forgotten.

`RegistrosDeMasterData` is the other half of the Context Map edge, and it is where the
`origen` filter of RN-03 lives: a record that came from the spreadsheet is never written
back into it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from cheatsheet.contexts.master_data.application.ingesta import (
    ListarClientesParaEscrituraDeVuelta,
)
from cheatsheet.contexts.master_data.application.ports import PortRepositorioCliente
from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    PermisosDePlanillaInsuficientes,
    ProveedorDePlanillaNoDisponible,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import FilaParaEscribir
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

URL_HOJAS = "https://sheets.googleapis.com/v4/spreadsheets"

TIMEOUT_SEGUNDOS = 30.0
MAX_INTENTOS = 3
ESPERA_BASE = 0.5

#: How many records one write-back carries. Google's API rejects very large bodies, and a
#: sweep that tried to push a whole catalogue in one call would fail as a unit rather than
#: make progress.
TAMANO_DE_LOTE = 500

#: The header CheatSheet writes at the top of its own sheet. Fixed, because the sheet is
#: ours: a company that reorders it is reordering something we recreate on the next write.
ENCABEZADO = ("Nombre", "CUIT", "WhatsApp", "Email", "Origen")


@dataclass(frozen=True, slots=True)
class ConfiguracionDeEscritura:
    """The OAuth token for one company's document. Obtained by the sync task."""

    token: str


class EscrituraEnGoogleSheets:
    """`PortEscrituraDePlanilla` against the real Google Sheets API."""

    def __init__(self, configuracion: ConfiguracionDeEscritura) -> None:
        if not configuracion.token:
            raise ValueError("Falta el token de acceso de la empresa para Google Sheets")
        self._token = configuracion.token

    async def escribir(
        self, *, identificador: str, hoja: str, filas: tuple[FilaParaEscribir, ...]
    ) -> None:
        if not filas:
            return

        await self._asegurar_hoja(identificador, hoja)
        # Remove rows left by an earlier, larger snapshot. A retry reconstructs the
        # same complete sheet, even if an earlier attempt stopped between batches.
        await self._pedir("POST", f"{URL_HOJAS}/{identificador}/values/'{hoja}'!A:Z:clear")
        # Each update names only our sheet. The header occupies row 1, so a later batch
        # starts after every row already sent. No success is reported for a partial run.
        for comienzo in range(0, len(filas), TAMANO_DE_LOTE):
            lote = filas[comienzo : comienzo + TAMANO_DE_LOTE]
            valores = [list(f.valores) for f in lote]
            if comienzo == 0:
                valores.insert(0, list(ENCABEZADO))
            rango = f"'{hoja}'!A{comienzo + (1 if comienzo == 0 else 2)}"
            await self._pedir(
                "PUT",
                f"{URL_HOJAS}/{identificador}/values/{rango}",
                params={"valueInputOption": "RAW"},
                json={"values": valores},
            )
        logger.info("planilla_escrita", hoja=hoja, filas=len(filas))

    async def _asegurar_hoja(self, identificador: str, hoja: str) -> None:
        url = f"{URL_HOJAS}/{identificador}"
        documento = await self._pedir(
            "GET",
            url,
            params={"fields": "sheets(properties(sheetId,title),protectedRanges(range))"},
        )
        existentes = [
            sheet
            for sheet in documento.get("sheets", [])
            if sheet.get("properties", {}).get("title") == hoja
        ]
        if existentes:
            sheet = existentes[0]
            sheet_id = sheet["properties"]["sheetId"]
            if any(
                item.get("range", {}).get("sheetId") == sheet_id
                for item in sheet.get("protectedRanges", [])
            ):
                return
        else:
            creado = await self._pedir(
                "POST",
                f"{url}:batchUpdate",
                json={"requests": [{"addSheet": {"properties": {"title": hoja}}}]},
            )
            sheet_id = creado["replies"][0]["addSheet"]["properties"]["sheetId"]
        await self._pedir(
            "POST",
            f"{url}:batchUpdate",
            json={
                "requests": [
                    {
                        "addProtectedRange": {
                            "protectedRange": {
                                "range": {"sheetId": sheet_id},
                                "description": "Managed by CheatSheet",
                                "warningOnly": False,
                            }
                        }
                    }
                ]
            },
        )

    async def _pedir(self, metodo: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Timeout and bounded retry, as CLAUDE.md section 5 requires."""
        ultimo: Exception | None = None
        for intento in range(1, MAX_INTENTOS + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
                    respuesta = await cliente.request(
                        metodo,
                        url,
                        headers={"Authorization": f"Bearer {self._token}"},
                        **kwargs,
                    )
                if respuesta.status_code in (401, 403):
                    raise PermisosDePlanillaInsuficientes(
                        "Google ya no permite escribir en esta planilla; volvé a vincularla."
                    )
                if 400 <= respuesta.status_code < 500:
                    # Not retried: Google has decided. A revoked token or a deleted
                    # document will be just as revoked in two seconds.
                    raise ProveedorDePlanillaNoDisponible(
                        f"Google rechazo la escritura con {respuesta.status_code}"
                    )
                respuesta.raise_for_status()
                cuerpo: dict[str, Any] = respuesta.json()
                return cuerpo
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                ultimo = exc
                if intento < MAX_INTENTOS:
                    await asyncio.sleep(ESPERA_BASE * (2 ** (intento - 1)))

        raise ProveedorDePlanillaNoDisponible(
            "No pudimos escribir en la planilla. Se reintenta en la proxima sincronizacion."
        ) from ultimo


class EscrituraSimulada:
    """The stand-in: records the writes and opens no socket.

    **Rejected in production**, like every other simulator here: a company that believes
    the panel is feeding its spreadsheet, and finds the sheet empty a month later, has
    been keeping two sets of books without knowing.
    """

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "La escritura simulada no es valida en produccion: "
                "nada llegaria a la planilla de la empresa."
            )
        self.escrituras: list[tuple[str, str, int]] = []

    async def escribir(
        self, *, identificador: str, hoja: str, filas: tuple[FilaParaEscribir, ...]
    ) -> None:
        self.escrituras.append((identificador, hoja, len(filas)))


class RegistrosDeMasterData:
    """`PortRegistrosParaEscribir` over `master_data`'s application layer.

    A thin translation and nothing else. **The `origen` filter of RN-03 is not here** -- it
    lives in `ListarClientesParaEscrituraDeVuelta`, inside `master_data`, because `origen`
    is that context's concept and rule R3 keeps this one out of its `domain/`. The
    architecture guard caught exactly that when this adapter first reached for
    `FiltrosDeCliente`.
    """

    def __init__(self, *, clientes: PortRepositorioCliente, empresa_id: EmpresaId) -> None:
        self._consulta = ListarClientesParaEscrituraDeVuelta(clientes)
        self._empresa_id = empresa_id

    async def pendientes_de_escritura(
        self, *, desde: datetime | None
    ) -> tuple[FilaParaEscribir, ...]:
        registros = await self._consulta.ejecutar(empresa_id=self._empresa_id, desde=desde)
        # The order of the tuple is the order of `ENCABEZADO` above: that is what makes the
        # columns line up with the header this context writes.
        return tuple(
            FilaParaEscribir(
                valores=(
                    registro.nombre,
                    registro.cuit,
                    registro.contacto_whatsapp,
                    registro.contacto_email,
                    registro.origen,
                )
            )
            for registro in registros
        )
