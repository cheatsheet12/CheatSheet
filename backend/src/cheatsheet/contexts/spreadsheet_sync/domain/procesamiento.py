"""`ProcesamientoDePlanilla` and `ErrorDeFila` — the aggregates behind HU-E3-03/05/06.

One rule carries this file, and it is the story's own: **a bad row is marked, not fatal**
(HU-E3-03 RN-02). Forty thousand rows and one malformed CUIT must produce 39 999 customers
and one line saying which row and why — not zero customers and a traceback. Everything
here is arranged so that the failure of one row cannot reach the loop that reads the next.

`ErrorDeFila` records **the row number of the original file** (HU-E3-05 RN-02), not an
index into whatever we happened to iterate. The user is going to open their spreadsheet
and look for that line; an off-by-one here sends them to the wrong row, which is worse
than no number at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: A row's reason has to fit on a screen next to a row number. Longer than this is a
#: traceback, and a traceback is not what «CUIT invalido en la fila 42.» means.
MAX_LONGITUD_MOTIVO = 300


class EstadoProcesamiento(StrEnum):
    """The DER's `estado_procesamiento`, plus what the screen actually shows.

    The DER closes it at `EN_CURSO`, `COMPLETADO` and `FALLIDO`. HU-E3-03 has a fourth
    state on screen — «Con errores», the run that finished and left rows behind — and it
    is not `FALLIDO`: the processing worked, the catalogue was filled, and some rows need
    a person. Collapsing the two would make «se procesaron 39.999 de 40.000» look like a
    failed import.
    """

    EN_CURSO = "EN_CURSO"
    COMPLETADO = "COMPLETADO"
    CON_ERRORES = "CON_ERRORES"
    FALLIDO = "FALLIDO"

    @property
    def es_terminal(self) -> bool:
        return self is not EstadoProcesamiento.EN_CURSO


@dataclass(frozen=True, slots=True)
class ErrorDeFila:
    """One row that did not make it, and why (HU-E3-05 RN-01 and RN-02)."""

    id: UUID
    #: 1-based, as the spreadsheet numbers it, header included. See the module docstring.
    numero_fila: int
    motivo: str
    #: When a person corrected the row in the system. **The error is not deleted**: a
    #: processing is the record of an import, and «esta fila falló y se arregló el martes» is
    #: part of that record. A corrected error is history and no longer counts as pending.
    corregida_en: datetime | None = None

    @property
    def pendiente(self) -> bool:
        return self.corregida_en is None

    def __post_init__(self) -> None:
        if self.numero_fila < 1:
            raise EntradaInvalida("El numero de fila de una planilla arranca en 1")
        limpio = self.motivo.strip()
        if not limpio:
            raise EntradaInvalida("Un error de fila tiene que decir por que")
        object.__setattr__(self, "motivo", limpio[:MAX_LONGITUD_MOTIVO])


@dataclass(slots=True, kw_only=True)
class ProcesamientoDePlanilla:
    """One run over one spreadsheet, and what it left behind."""

    id: UUID
    empresa_id: EmpresaId
    vinculo_id: UUID
    mapeo_id: UUID
    estado: EstadoProcesamiento = EstadoProcesamiento.EN_CURSO
    filas_totales: int = 0
    filas_ok: int = 0
    filas_error: int = 0
    duracion_ms: int | None = None
    referencia_archivo: str | None = None
    #: HU-E3-06 RN-03: a reprocessing is a new run **linked to the original**, so the
    #: history reads as one story and not as two unrelated imports.
    origen_id: UUID | None = None
    errores: list[ErrorDeFila] = field(default_factory=list)
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise EntradaInvalida("created_at debe tener zona horaria (UTC)")

    @property
    def es_reproceso(self) -> bool:
        return self.origen_id is not None

    @property
    def termino(self) -> bool:
        return self.estado.es_terminal

    def contar_fila_ok(self) -> None:
        self._exigir_en_curso()
        self.filas_ok += 1
        self.filas_totales += 1

    def registrar_error(self, *, error: ErrorDeFila) -> None:
        """RN-02: the row is recorded and the run keeps going."""
        self._exigir_en_curso()
        self.errores.append(error)
        self.filas_error += 1
        self.filas_totales += 1

    def cerrar(self, *, duracion_ms: int, ahora: datetime) -> None:
        """Finish the run, and let the counters decide which ending it was.

        Not a parameter: a caller that could *say* «completado» while `filas_error` is 12
        is a caller that can lie about it, and the screen would show a green import over a
        table full of failures.
        """
        del ahora  # The DER gives a processing only `created_at`; the duration is the end.
        self._exigir_en_curso()
        if duracion_ms < 0:
            raise EntradaInvalida("La duracion no puede ser negativa")
        self.duracion_ms = duracion_ms
        self.estado = (
            EstadoProcesamiento.CON_ERRORES if self.filas_error else EstadoProcesamiento.COMPLETADO
        )

    def abortar(self, *, motivo: str, duracion_ms: int, ahora: datetime) -> None:
        """The run itself broke — the file was unreadable, the store was down.

        Different from `CON_ERRORES` in the one way that matters: nothing was ingested and
        there is nothing for the user to correct row by row.
        """
        del ahora
        self._exigir_en_curso()
        self.duracion_ms = duracion_ms
        self.estado = EstadoProcesamiento.FALLIDO
        self.errores.append(ErrorDeFila(id=self.id, numero_fila=1, motivo=motivo))

    @property
    def errores_pendientes(self) -> list[ErrorDeFila]:
        """The rows still waiting for a person. A corrected one is history."""
        return [e for e in self.errores if e.pendiente]

    def corregir_fila(self, *, numero_fila: int, ahora: datetime) -> None:
        """A person fixed one failed row and it went into the catalogue.

        **The counters move here and nowhere else**, for the reason `cerrar` gives: a caller
        that could set `filas_error` by hand is a caller that can make the screen lie. One
        row less in error and one more imported; the total does not change, because it is
        the same row.

        Only a run that finished **with errors** can be corrected. A `FALLIDO` one never
        ingested anything and its single error is the file itself, not a row to fix.
        """
        if self.estado is not EstadoProcesamiento.CON_ERRORES:
            raise InvarianteViolada(
                f"Solo se corrigen filas de una carga con errores, y esta termino {self.estado.value}"
            )
        for indice, error in enumerate(self.errores):
            if error.numero_fila == numero_fila and error.pendiente:
                self.errores[indice] = replace(error, corregida_en=ahora)
                break
        else:
            raise EntradaInvalida(f"La fila {numero_fila} no tiene un error pendiente de corregir")
        self.filas_error -= 1
        self.filas_ok += 1
        if self.filas_error == 0:
            self.estado = EstadoProcesamiento.COMPLETADO

    @property
    def filas_a_reprocesar(self) -> tuple[int, ...]:
        """HU-E3-06 RN-02: only the rows that failed, so nothing is duplicated.

        This is the whole of «no duplica las filas ya procesadas correctamente». A
        reprocessing that re-read the file from the top would create every customer twice,
        and the story would have to be about deduplication instead of about correcting
        four rows.
        """
        if self.estado is not EstadoProcesamiento.CON_ERRORES:
            return ()
        return tuple(sorted({e.numero_fila for e in self.errores_pendientes}))

    def _exigir_en_curso(self) -> None:
        if self.estado.es_terminal:
            raise InvarianteViolada(f"El procesamiento ya termino con estado {self.estado.value}")
