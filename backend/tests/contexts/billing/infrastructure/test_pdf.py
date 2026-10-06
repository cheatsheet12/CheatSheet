"""La caché del PDF del comprobante (HU-E5-02 RN-03).

Lo que se prueba acá es que **la caché sea una caché**: un fallo de lectura no es un error,
significa regenerar. Es lo que hace cierta la frase «regenerándolo si fuese necesario» de
la historia, y lo que hace que el bucket sea descartable — perderlo no pierde nada, porque
el comprobante fiscal es la fila y su CAE.

El contenido del papel se prueba en `test_pdf_contenido.py`, que es sincrónico.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.billing.infrastructure.pdf import PdfDeComprobante, clave_de
from cheatsheet.platform.almacenamiento import (
    AlmacenamientoEnMemoria,
    AlmacenamientoNoDisponible,
    ArchivoGuardado,
)

from tests.contexts.billing.infrastructure.test_pdf_contenido import comprobante

pytestmark = pytest.mark.asyncio


class AlmacenamientoQueFalla:
    """Un doble que rompe al leer, para el camino que **no** es un error."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.guardados: dict[str, bytes] = {}

    async def guardar(
        self, *, clave: str, contenido: bytes, tipo_de_contenido: str
    ) -> ArchivoGuardado:
        del tipo_de_contenido
        self.guardados[clave] = contenido
        return ArchivoGuardado(clave=clave, tamano_bytes=len(contenido))

    async def leer(self, clave: str) -> bytes:
        del clave
        raise self.error

    async def eliminar(self, clave: str) -> None:
        self.guardados.pop(clave, None)


async def test_la_primera_vez_se_genera_y_se_guarda() -> None:
    almacen = AlmacenamientoEnMemoria()
    documento = comprobante()

    contenido = await PdfDeComprobante(almacen).obtener(documento, 1)

    assert contenido.startswith(b"%PDF-")
    assert almacen.archivos[clave_de(documento)] == contenido


async def test_la_segunda_vez_sale_de_la_cache() -> None:
    almacen = AlmacenamientoEnMemoria()
    documento = comprobante()
    pdf = PdfDeComprobante(almacen)
    await pdf.obtener(documento, 1)

    # Se pisa el contenido guardado con algo reconocible: si volviera a renderizar, esto
    # no seria lo que sale.
    almacen.archivos[clave_de(documento)] = b"%PDF-cacheado"

    assert await pdf.obtener(documento, 1) == b"%PDF-cacheado"


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError("no esta"), AlmacenamientoNoDisponible("R2 no contesta")],
)
async def test_un_fallo_de_lectura_regenera_en_vez_de_romper(error: Exception) -> None:
    """**El comportamiento que hace cierta la frase de la historia.**

    Los dos errores significan lo mismo acá: no tenemos los bytes, así que se hacen. Que R2
    esté caído no puede convertirse en un usuario que no puede imprimir su factura — y
    tampoco en un `except Exception`, que `CLAUDE.md` §5 prohíbe: el adaptador los tipa,
    que es lo que permite nombrarlos.
    """
    almacen = AlmacenamientoQueFalla(error)
    documento = comprobante()

    contenido = await PdfDeComprobante(almacen).obtener(documento, 1)

    assert contenido.startswith(b"%PDF-")
    assert almacen.guardados[clave_de(documento)] == contenido
