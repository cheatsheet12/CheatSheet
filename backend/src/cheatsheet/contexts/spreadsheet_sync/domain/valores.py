"""Value objects of `spreadsheet_sync` — how a spreadsheet identifies itself.

The DER (BC5) closes `proveedor_planilla` at two values. This module adds a third,
`ARCHIVO`, and that departure is argued in decision D10 of the units map rather than
here: HU-E3-03 has two acceptance criteria about uploading a file, the prototype has the
drop zone next to the link button, and `procesamiento_de_planilla.vinculo_id` is NOT NULL
— so a processing must hang off a link, and an uploaded file must therefore be one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cheatsheet.shared.errors import EntradaInvalida

#: HU-E3-03: what the drop zone accepts, and what its rejection message names.
EXTENSIONES_ACEPTADAS = (".xlsx", ".xls", ".csv")

#: HU-E3-03, in bytes. The acceptance criterion states the limit in megabytes, so it is
#: written that way here too — a reader checking the story against the code should not
#: have to do arithmetic.
LIMITE_TAMANO_MB = 25
LIMITE_TAMANO_BYTES = LIMITE_TAMANO_MB * 1024 * 1024

#: The exact texts of the acceptance criteria. Constants and not literals at the raise
#: site, because these travel to the screen and a test asserts on them: the story says
#: what the user reads, and paraphrasing it in the code is how the two drift apart.
MENSAJE_FORMATO_NO_ACEPTADO = "Formato no aceptado. Use .xlsx, .xls o .csv."
MENSAJE_ARCHIVO_DEMASIADO_GRANDE = f"El archivo supera el límite de {LIMITE_TAMANO_MB} MB."
MENSAJE_SIN_PERMISOS = "Se requieren permisos de lectura sobre la planilla para vincularla."


class ProveedorPlanilla(StrEnum):
    """Where a spreadsheet lives. See the module docstring on `ARCHIVO`."""

    GOOGLE_SHEETS = "GOOGLE_SHEETS"
    EXCEL_ONLINE = "EXCEL_ONLINE"
    #: A workbook uploaded through the panel. A snapshot, not a live source.
    ARCHIVO = "ARCHIVO"

    @property
    def admite_escritura(self) -> bool:
        """Whether write-back is even conceivable for this provider (HU-E3-07).

        Excel Online is read-only through the integration the story describes, and an
        uploaded file has nowhere to write back to — it is a copy sitting in R2, and
        writing into it would produce a file nobody ever opens again.
        """
        return self is ProveedorPlanilla.GOOGLE_SHEETS

    @property
    def es_fuente_viva(self) -> bool:
        """Whether re-reading it later can yield anything new (HU-E3-04).

        `ARCHIVO` is the one that cannot: incremental sync over a snapshot would compare
        a file against itself forever.
        """
        return self is not ProveedorPlanilla.ARCHIVO


class DireccionSync(StrEnum):
    """RN-02 of HU-E2-04, and the guard HU-E3-07 RN-01 reads before writing anything."""

    SOLO_LECTURA = "SOLO_LECTURA"
    LECTURA_Y_ESCRITURA = "LECTURA_Y_ESCRITURA"


@dataclass(frozen=True, slots=True)
class ReferenciaDeArchivo:
    """Where the bytes of an uploaded workbook are, and what they were called.

    The original name is kept because it is what the user recognises in `Cargas
    recientes`; the key is what R2 answers to. They are deliberately different: a
    company's file name is neither unique nor safe to use as an object key.
    """

    clave: str
    nombre_original: str
    tamano_bytes: int

    def __post_init__(self) -> None:
        if not self.clave.strip():
            raise EntradaInvalida("La clave del archivo no puede estar vacia")
        if not self.nombre_original.strip():
            raise EntradaInvalida("El nombre del archivo no puede estar vacio")
        if self.tamano_bytes <= 0:
            raise EntradaInvalida("El archivo esta vacio")
        if self.tamano_bytes > LIMITE_TAMANO_BYTES:
            raise EntradaInvalida(MENSAJE_ARCHIVO_DEMASIADO_GRANDE)

    @property
    def extension(self) -> str:
        _, punto, resto = self.nombre_original.rpartition(".")
        return f".{resto.lower()}" if punto else ""


def validar_extension(nombre_de_archivo: str) -> str:
    """HU-E3-03: reject anything that is not a workbook, by the message the story gives.

    Checked on the name rather than by sniffing the content, deliberately. The criterion
    is about what the user is told before the upload starts, and the real defence against
    a hostile file is that nothing here ever executes it — the parser of `carga-y-errores`
    reads cells and would fail on anything else regardless of its extension.
    """
    limpio = nombre_de_archivo.strip()
    if not limpio:
        raise EntradaInvalida(MENSAJE_FORMATO_NO_ACEPTADO)
    if not any(limpio.lower().endswith(ext) for ext in EXTENSIONES_ACEPTADAS):
        raise EntradaInvalida(MENSAJE_FORMATO_NO_ACEPTADO)
    return limpio
