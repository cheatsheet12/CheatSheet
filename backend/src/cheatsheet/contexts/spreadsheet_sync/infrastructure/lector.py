"""Reading the rows out of a workbook — the adapter behind `PortLectorDePlanilla`.

Two formats, one interface. `.xlsx` and `.xls` go through `openpyxl`; `.csv` goes through
the standard library. Both yield the same thing: the header row, and then every data row
as text keyed by column name.

**Everything comes out as text, including numbers.** A cell holding `30712345671` is read
by openpyxl as an `int`, and `str(int)` is fine — but a cell holding `0303456` is a CUIT
prefix a person typed, and Excel already ate the leading zero. Text is what the mapping
layer expects and what `master_data`'s ingestion parses; converting here would mean
guessing twice.

**`read_only=True` is not a performance detail.** Without it openpyxl builds the whole
workbook in memory, and a 25 MB file becomes hundreds of megabytes in a worker that is
also running four other tasks.

**Nothing here validates.** A row that is nonsense is still a row: the processing turns it
into an `ErrorDeFila` with its original line number, which is what HU-E3-05 asks for. A
reader that refused bad rows would lose the row number by the time anybody could report it.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    FormatoDePlanillaNoSoportado,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import FilaLeida, PlanillaLeida
from cheatsheet.contexts.spreadsheet_sync.domain.valores import MENSAJE_FORMATO_NO_ACEPTADO

#: The row number a person sees for the first data row. Row 1 is the header, so the
#: numbers this module reports line up with what the spreadsheet shows in its margin --
#: which is the whole point of HU-E3-05 RN-02.
PRIMERA_FILA_DE_DATOS = 2


class LectorDePlanilla:
    """`PortLectorDePlanilla` over bytes, for both formats HU-E3-03 accepts."""

    def leer(self, *, contenido: bytes, nombre: str) -> PlanillaLeida:
        minusculas = nombre.lower()
        if minusculas.endswith(".csv"):
            return _leer_csv(contenido)
        if minusculas.endswith((".xlsx", ".xls")):
            return _leer_excel(contenido)
        raise FormatoDePlanillaNoSoportado(MENSAJE_FORMATO_NO_ACEPTADO)


def _texto(valor: object) -> str:
    """One cell, as text. `None` becomes empty, which is what an empty cell means."""
    if valor is None:
        return ""
    return str(valor).strip()


def _armar(columnas: tuple[str, ...], filas: Iterator[tuple[int, list[object]]]) -> PlanillaLeida:
    leidas: list[FilaLeida] = []
    for numero, valores in filas:
        celdas = {
            columna: _texto(valores[indice]) if indice < len(valores) else ""
            for indice, columna in enumerate(columnas)
        }
        # A row where every cell is empty is the blank line under the table, not data.
        # Counting it would report «40.000 filas» on a sheet with 39.998 customers.
        if any(celdas.values()):
            leidas.append(FilaLeida(numero=numero, celdas=celdas))
    return PlanillaLeida(columnas=columnas, filas=tuple(leidas))


def _leer_csv(contenido: bytes) -> PlanillaLeida:
    # utf-8-sig, not utf-8: a CSV exported from Excel in Spanish starts with a BOM, and
    # without this the first column is called `﻿Nombre` and never matches anything.
    texto = contenido.decode("utf-8-sig", errors="replace")
    lector = csv.reader(io.StringIO(texto))
    try:
        encabezado = next(lector)
    except StopIteration:
        return PlanillaLeida(columnas=(), filas=())

    columnas = tuple(_texto(c) for c in encabezado)
    return _armar(
        columnas,
        ((numero, list(fila)) for numero, fila in enumerate(lector, start=PRIMERA_FILA_DE_DATOS)),
    )


def _leer_excel(contenido: bytes) -> PlanillaLeida:
    try:
        # Deferred like every other heavy dependency here: the context stays importable
        # where openpyxl is absent, and only this function needs it.
        import openpyxl
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "Falta la dependencia openpyxl, que es el lector de planillas .xlsx. "
            "Instalala con: pip install -e backend"
        ) from exc

    libro = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    try:
        hoja = libro.worksheets[0]
        filas = hoja.iter_rows(values_only=True)
        try:
            encabezado = next(filas)
        except StopIteration:
            return PlanillaLeida(columnas=(), filas=())

        columnas = tuple(_texto(c) for c in encabezado)
        return _armar(
            columnas,
            (
                (numero, list(fila))
                for numero, fila in enumerate(filas, start=PRIMERA_FILA_DE_DATOS)
            ),
        )
    finally:
        # A read-only workbook holds the zip handle open until this is called.
        libro.close()
