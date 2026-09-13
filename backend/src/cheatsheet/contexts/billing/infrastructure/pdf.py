"""The printable representation of a document (HU-E5-02 RN-03).

**This is not the fiscal source of truth.** The story is explicit about it and it is worth
repeating where the code lives: what is legally the document is the row plus its CAE. This
is a rendering of that row, regenerated whenever it is missing, and nothing downstream may
treat it as authoritative — which is why it is cached rather than stored, and why losing
the bucket loses nothing.

**Only an authorised document is rendered.** A PDF of something ARCA rejected would be a
piece of paper that looks exactly like an invoice and is not one, and somebody would hand
it to a customer.

`reportlab` is imported lazily, inside the renderer, for the reason `almacenamiento.py`
gives about `boto3`: it is a real dependency of this module and importing it at module
scope would make the whole context unimportable wherever it is absent — including every
test that never renders anything. The failure it produces instead is a sentence naming the
package, at the moment somebody actually asks for a PDF.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from io import BytesIO
from typing import Protocol

from cheatsheet.contexts.billing.domain.comprobante import Comprobante
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.platform.almacenamiento import AlmacenamientoNoDisponible
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

TIPO_DE_CONTENIDO = "application/pdf"

#: How each type is named on the page. ARCA's letter is what a reader looks for first, so
#: it is printed on its own, large, the way a real invoice does it.
NOMBRES: dict[TipoComprobante, str] = {
    TipoComprobante.FACTURA_A: "FACTURA",
    TipoComprobante.FACTURA_B: "FACTURA",
    TipoComprobante.FACTURA_C: "FACTURA",
    TipoComprobante.NOTA_CREDITO_A: "NOTA DE CREDITO",
    TipoComprobante.NOTA_CREDITO_B: "NOTA DE CREDITO",
    TipoComprobante.NOTA_CREDITO_C: "NOTA DE CREDITO",
}


def clave_de(comprobante: Comprobante) -> str:
    """Where the rendering is cached.

    Keyed by company **and** document, so one company's bucket prefix never contains
    another's paperwork even by accident. The `.pdf` suffix is for whoever has to look at
    the bucket with a human eye.
    """
    return f"comprobantes/{comprobante.empresa_id}/{comprobante.id}.pdf"


class PortAlmacenamientoDeComprobantes(Protocol):
    """Where the rendering is cached.

    `billing`'s own port, structurally identical to the one `spreadsheet_sync` declares,
    and that duplication is the correct kind: a port is the *consumer's* contract. What is
    shared is the adapter — `platform/almacenamiento.py` — because object storage is
    platform infrastructure and R3 forbids either context reaching into the other's.
    """

    async def guardar(self, *, clave: str, contenido: bytes, tipo_de_contenido: str) -> object: ...

    async def leer(self, clave: str) -> bytes: ...

    async def eliminar(self, clave: str) -> None: ...


def _monto(valor: Decimal) -> str:
    """Two decimals, from the already-rounded value. Nothing here computes anything."""
    return f"{valor:.2f}"


#: What the page says, as a caption and a value. Split out from the drawing on purpose:
#: **the content is testable and the layout is not**. A test that compared the drawing
#: would break every time somebody moved a millimetre and would say nothing about whether
#: the document is right; this way the fields that must be on the paper are asserted
#: directly, and `renderizar` is left with only the part where being wrong is cosmetic.
def datos_del_encabezado(comprobante: Comprobante, punto_numero: int) -> list[tuple[str, str]]:
    """The document's own identifiers. `numero` is the form ARCA prints."""
    return [
        ("Numero", f"{punto_numero:04d}-{comprobante.numero or 0:08d}"),
        ("Fecha de emision", _fecha(comprobante)),
        ("CAE", comprobante.cae.codigo if comprobante.cae else "-"),
        ("Vencimiento del CAE", str(comprobante.cae.vence_el) if comprobante.cae else "-"),
    ]


def datos_del_receptor(comprobante: Comprobante) -> list[tuple[str, str]]:
    """Copied at issue time, so this is what was true the day it was issued."""
    return [
        ("Razon social", comprobante.receptor.nombre),
        ("CUIT", comprobante.receptor.cuit),
        ("Condicion de IVA", comprobante.receptor.condicion_iva.value.replace("_", " ")),
        ("Domicilio", comprobante.receptor.domicilio or "-"),
    ]


#: Printed at the foot of every page. It is what stops a PDF sitting in a folder from
#: looking as authoritative as the record, which it is not (RN-03).
PIE = "Representacion impresa. El comprobante fiscal es el registro electronico y su CAE."


def renderizar(comprobante: Comprobante, punto_numero: int) -> bytes:
    """Draw the document. Synchronous and CPU-bound; the caller offloads it.

    Deliberately plain: this is a representation, not a fiscal instrument, and every
    decorative element is one more thing that can make it *look* more official than it is.

    **What it says is decided above**, in the two functions that return caption/value
    pairs, so the content of the paper is testable without a PDF parser.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "Falta el paquete 'reportlab', que es el que dibuja el PDF del comprobante"
        ) from exc

    buffer = BytesIO()
    pagina = canvas.Canvas(buffer, pagesize=A4)
    ancho, alto = A4
    y = alto - 25 * mm

    pagina.setFont("Helvetica-Bold", 18)
    pagina.drawString(20 * mm, y, NOMBRES[comprobante.tipo])
    # The letter on its own, boxed, the way a real invoice prints it: it is what a reader
    # looks for first and what decides whether they can compute the VAT.
    pagina.setFont("Helvetica-Bold", 24)
    pagina.drawCentredString(ancho / 2, y, comprobante.tipo.letra)
    pagina.rect(ancho / 2 - 8 * mm, y - 3 * mm, 16 * mm, 12 * mm)

    pagina.setFont("Helvetica", 10)
    y -= 12 * mm
    for etiqueta, valor in datos_del_encabezado(comprobante, punto_numero):
        pagina.drawString(20 * mm, y, f"{etiqueta}: {valor}")
        y -= 6 * mm

    y -= 4 * mm
    pagina.setFont("Helvetica-Bold", 11)
    pagina.drawString(20 * mm, y, "Receptor")
    pagina.setFont("Helvetica", 10)
    y -= 6 * mm
    for etiqueta, valor in datos_del_receptor(comprobante):
        pagina.drawString(20 * mm, y, f"{etiqueta}: {valor}")
        y -= 6 * mm

    y -= 6 * mm
    pagina.setFont("Helvetica-Bold", 10)
    for texto, x in (("Descripcion", 20), ("Cant.", 110), ("P. unitario", 130), ("Subtotal", 165)):
        pagina.drawString(x * mm, y, texto)
    y -= 5 * mm
    pagina.line(20 * mm, y, 190 * mm, y)
    y -= 6 * mm

    pagina.setFont("Helvetica", 9)
    for item in comprobante.items:
        # Truncated rather than wrapped: a description long enough to wrap would push the
        # totals off the page, and the totals are what the document is for.
        pagina.drawString(20 * mm, y, item.descripcion[:55])
        pagina.drawRightString(122 * mm, y, _monto(item.cantidad))
        pagina.drawRightString(158 * mm, y, _monto(item.precio_unitario))
        pagina.drawRightString(190 * mm, y, _monto(item.subtotal))
        y -= 5 * mm
        if y < 40 * mm:  # pragma: no cover - only for very long documents
            pagina.showPage()
            pagina.setFont("Helvetica", 9)
            y = alto - 25 * mm

    y -= 4 * mm
    pagina.line(120 * mm, y, 190 * mm, y)
    y -= 6 * mm
    pagina.setFont("Helvetica", 10)
    # Written from the aggregate's already-rounded values. This file does not add anything
    # up: a second implementation of the arithmetic is a second chance to print a total
    # that disagrees with the one ARCA authorised.
    pagina.drawRightString(158 * mm, y, "Subtotal:")
    pagina.drawRightString(190 * mm, y, _monto(comprobante.subtotal))
    y -= 6 * mm
    pagina.drawRightString(158 * mm, y, "IVA:")
    pagina.drawRightString(190 * mm, y, _monto(comprobante.total_iva))
    y -= 6 * mm
    pagina.setFont("Helvetica-Bold", 12)
    pagina.drawRightString(158 * mm, y, "TOTAL:")
    pagina.drawRightString(190 * mm, y, _monto(comprobante.total))

    pagina.setFont("Helvetica-Oblique", 7)
    pagina.drawString(20 * mm, 15 * mm, PIE)

    pagina.showPage()
    pagina.save()
    return buffer.getvalue()


def _fecha(comprobante: Comprobante) -> str:
    momento = comprobante.fecha_emision or comprobante.created_at
    return momento.date().isoformat()


class PdfDeComprobante:
    """Render on demand, cache in the object store, regenerate when missing (RN-03).

    The cache is a cache and behaves like one: a miss costs a render, and **a read failure
    is not an error** — it means regenerate. That is what makes the story's «regenerándolo
    si fuese necesario» true rather than aspirational, and what makes the bucket disposable.
    """

    def __init__(self, almacenamiento: PortAlmacenamientoDeComprobantes) -> None:
        self._almacenamiento = almacenamiento

    async def obtener(self, comprobante: Comprobante, punto_numero: int) -> bytes:
        clave = clave_de(comprobante)
        try:
            return await self._almacenamiento.leer(clave)
        except (FileNotFoundError, AlmacenamientoNoDisponible):
            # Two exceptions, one meaning **here**: we do not have the cached bytes, so
            # make them. The store keeps them apart because for its other caller they are
            # different — a missing workbook is a bug and an outage is not — and this
            # caller flattens them on purpose, because a transient S3 error must not become
            # a user who cannot print their invoice.
            logger.info("pdf_de_comprobante_regenerado", comprobante_id=str(comprobante.id))

        contenido = await asyncio.to_thread(renderizar, comprobante, punto_numero)
        await self._almacenamiento.guardar(
            clave=clave, contenido=contenido, tipo_de_contenido=TIPO_DE_CONTENIDO
        )
        return contenido


__all__ = [
    "PIE",
    "TIPO_DE_CONTENIDO",
    "PdfDeComprobante",
    "PortAlmacenamientoDeComprobantes",
    "clave_de",
    "datos_del_encabezado",
    "datos_del_receptor",
    "renderizar",
]
