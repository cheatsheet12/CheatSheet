"""El lector de planillas: los dos formatos, y el número de fila.

El test que más importa es el del **número de fila**. HU-E3-05 RN-02 dice que cada error
indica «el número de fila del archivo original», y el usuario va a abrir su planilla y
buscar esa línea en el margen. Un off-by-one lo manda a la fila equivocada, que es peor
que no darle ningún número.
"""

from __future__ import annotations

import io

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    FormatoDePlanillaNoSoportado,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.lector import LectorDePlanilla

LECTOR = LectorDePlanilla()


def _csv(texto: str, *, bom: bool = False) -> bytes:
    crudo = texto.encode("utf-8")
    return b"\xef\xbb\xbf" + crudo if bom else crudo


def _xlsx(filas: list[list[object]]) -> bytes:
    import openpyxl

    libro = openpyxl.Workbook()
    hoja = libro.active
    assert hoja is not None
    for fila in filas:
        hoja.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_el_csv_numera_la_primera_fila_de_datos_como_la_2() -> None:
    """La fila 1 es el encabezado, como la ve el usuario en su propia planilla."""
    planilla = LECTOR.leer(
        contenido=_csv("Cliente,CUIT\nPanaderia,30712345671\nKiosco,20123456786\n"),
        nombre="clientes.csv",
    )

    assert planilla.columnas == ("Cliente", "CUIT")
    assert [f.numero for f in planilla.filas] == [2, 3]
    assert planilla.filas[0].celdas == {"Cliente": "Panaderia", "CUIT": "30712345671"}


def test_el_xlsx_numera_igual_que_el_csv() -> None:
    planilla = LECTOR.leer(
        contenido=_xlsx([["Cliente", "CUIT"], ["Panaderia", 30712345671], ["Kiosco", None]]),
        nombre="clientes.xlsx",
    )

    assert planilla.columnas == ("Cliente", "CUIT")
    assert [f.numero for f in planilla.filas] == [2, 3]
    # Los números salen como texto: convertir acá sería adivinar dos veces.
    assert planilla.filas[0].celdas["CUIT"] == "30712345671"
    # Una celda vacía es una cadena vacía, no un `None` que después revienta.
    assert planilla.filas[1].celdas["CUIT"] == ""


def test_un_csv_exportado_de_excel_en_espanol_trae_bom_y_se_lee_igual() -> None:
    """Sin `utf-8-sig`, la primera columna se llama `\\ufeffCliente` y no matchea nada."""
    planilla = LECTOR.leer(
        contenido=_csv("Cliente,CUIT\nPanaderia,30712345671\n", bom=True),
        nombre="clientes.csv",
    )

    assert planilla.columnas[0] == "Cliente"


def test_las_filas_vacias_no_se_cuentan() -> None:
    """La línea en blanco debajo de la tabla no es un cliente.

    Contarla haría que la pantalla diga «40.000 filas» sobre una planilla con 39.998.
    """
    planilla = LECTOR.leer(
        contenido=_csv("Cliente,CUIT\nPanaderia,30712345671\n,\n\n"), nombre="clientes.csv"
    )

    assert len(planilla.filas) == 1


def test_una_planilla_vacia_no_revienta() -> None:
    assert LECTOR.leer(contenido=b"", nombre="clientes.csv").filas == ()


def test_solo_devuelve_las_filas_pedidas() -> None:
    """Lo que usa el reproceso de HU-E3-06 RN-02."""
    planilla = LECTOR.leer(contenido=_csv("Cliente,CUIT\nA,1\nB,2\nC,3\n"), nombre="clientes.csv")

    subconjunto = planilla.solo((3,))

    assert [f.numero for f in subconjunto.filas] == [3]
    assert subconjunto.columnas == planilla.columnas


@pytest.mark.parametrize("nombre", ["clientes.pdf", "clientes", "clientes.json"])
def test_un_formato_no_soportado_se_rechaza(nombre: str) -> None:
    with pytest.raises(FormatoDePlanillaNoSoportado):
        LECTOR.leer(contenido=b"x", nombre=nombre)


def test_una_fila_mas_corta_que_el_encabezado_completa_con_vacios() -> None:
    """Una planilla real tiene filas a las que les faltan las últimas columnas."""
    planilla = LECTOR.leer(contenido=_csv("A,B,C\n1,2\n"), nombre="x.csv")

    assert planilla.filas[0].celdas == {"A": "1", "B": "2", "C": ""}
