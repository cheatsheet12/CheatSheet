"""`Mapeo` and `EntradaDeMapeo` — the aggregates behind HU-E3-01 and HU-E3-02.

Two rules carry this file.

**A mapping cannot be confirmed while a required column is unassigned** (HU-E3-02 RN-02).
That lives in the aggregate and not in the form, because confirming is what unlocks the
processing of thousands of rows: a mapping missing `nombre` produces a catalogue of
customers with no name, and the row that discovers it is row one of forty thousand.

**Low confidence is `Sin asignar`, not a guess** (HU-E3-01 RN-03). The threshold is applied
here, once, rather than by whoever reads the score. A model that is unsure is more useful
saying so — the screen already has a state for it and the user already has to look.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: Below this, RN-03 says the column is `Sin asignar` and a person has to look at it.
#: `Decimal` and not `float` because the score is compared for equality against these
#: bounds, and 0.7 is not 0.7 in binary floating point.
UMBRAL_CONFIANZA_MEDIA = Decimal("0.75")
UMBRAL_CONFIANZA_ALTA = Decimal("0.90")


class NivelDeConfianza(StrEnum):
    """The three levels HU-E3-01 RN-01 names, in the words the screen uses."""

    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"

    @classmethod
    def desde_score(cls, score: Decimal) -> NivelDeConfianza:
        if score >= UMBRAL_CONFIANZA_ALTA:
            return cls.ALTA
        if score >= UMBRAL_CONFIANZA_MEDIA:
            return cls.MEDIA
        return cls.BAJA

    @property
    def requiere_revision(self) -> bool:
        """RN-03. `MEDIA` is shown for review but does not block; `BAJA` is unassigned."""
        return self is NivelDeConfianza.BAJA


class EstadoMapeo(StrEnum):
    """The DER's `estado_mapeo`, unchanged."""

    BORRADOR = "BORRADOR"
    VALIDADO = "VALIDADO"


@dataclass(slots=True, kw_only=True)
class EntradaDeMapeo:
    """One column of the spreadsheet and where it lands in our schema.

    `atributo_destino` being `None` is the `Sin asignar` of RN-03 — either the model was
    not confident enough, or the user cleared it on purpose. The two are indistinguishable
    on purpose: both mean a person has to decide.
    """

    id: UUID
    columna_origen: str
    atributo_destino: str | None
    score: Decimal
    #: Read from the sheet and shown in the review (HU-E3-02). **Never sent to the model**
    #: — decision D12: these are real customers' names, CUITs and phone numbers.
    ejemplo: str | None = None
    #: True when a person set this assignment, so a re-run of the model does not undo it.
    corregida_a_mano: bool = False

    def __post_init__(self) -> None:
        if not self.columna_origen.strip():
            raise EntradaInvalida("Una columna de la planilla tiene que tener nombre")
        if not Decimal("0") <= self.score <= Decimal("1"):
            raise EntradaInvalida("El score de una entrada de mapeo va de 0 a 1")

    @property
    def confianza(self) -> NivelDeConfianza:
        # A hand-corrected assignment is certain by construction: a person looked at it.
        # Leaving it at the model's score would keep showing «revisar» next to the answer
        # the user just gave.
        if self.corregida_a_mano:
            return NivelDeConfianza.ALTA
        return NivelDeConfianza.desde_score(self.score)

    @property
    def esta_asignada(self) -> bool:
        return self.atributo_destino is not None

    def asignar(self, atributo: str | None) -> None:
        """HU-E3-02 RN-01: the user can correct any assignment before confirming."""
        if atributo is not None and not atributo.strip():
            raise EntradaInvalida("El atributo de destino no puede ser una cadena vacia")
        self.atributo_destino = atributo
        self.corregida_a_mano = True


@dataclass(slots=True, kw_only=True)
class Mapeo:
    """What the columns of one spreadsheet mean, and whether anybody has agreed to it."""

    id: UUID
    empresa_id: EmpresaId
    #: RN-02: identifies the *structure*, so the mapping is reused while it holds and a
    #: changed header is detectable without storing the sheet.
    huella_encabezado: str
    estado: EstadoMapeo = EstadoMapeo.BORRADOR
    version: int = 1
    entradas: list[EntradaDeMapeo] = field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.huella_encabezado.strip():
            raise EntradaInvalida("Un mapeo necesita la huella de su encabezado")
        if self.version < 1:
            raise EntradaInvalida("La version de un mapeo arranca en 1")

    @property
    def esta_confirmado(self) -> bool:
        return self.estado is EstadoMapeo.VALIDADO

    def faltantes(self, obligatorios: frozenset[str]) -> tuple[str, ...]:
        """Which required attributes no column feeds. Sorted, so the message is stable."""
        asignados = {e.atributo_destino for e in self.entradas if e.atributo_destino is not None}
        return tuple(sorted(obligatorios - asignados))

    def entrada_de(self, columna: str) -> EntradaDeMapeo:
        for entrada in self.entradas:
            if entrada.columna_origen == columna:
                return entrada
        raise EntradaInvalida(f"La columna '{columna}' no esta en este mapeo")

    def corregir(self, *, columna: str, atributo: str | None, ahora: datetime) -> None:
        """HU-E3-02 RN-01. Refused once confirmed — that is what confirming means.

        Re-mapping a spreadsheet that is already feeding the catalogue is a different
        operation with different consequences, and it goes through a new version.
        """
        if self.esta_confirmado:
            raise InvarianteViolada(
                "Este mapeo ya fue confirmado: para cambiarlo hay que revisarlo de nuevo"
            )
        self.entrada_de(columna).asignar(atributo)
        self.updated_at = ahora

    def confirmar(self, *, obligatorios: frozenset[str], ahora: datetime) -> None:
        """HU-E3-02 RN-02 and RN-03: nothing is processed until this passes."""
        faltantes = self.faltantes(obligatorios)
        if faltantes:
            raise InvarianteViolada(
                "Debe asignar todas las columnas obligatorias antes de continuar. "
                f"Faltan: {', '.join(faltantes)}"
            )
        self.estado = EstadoMapeo.VALIDADO
        self.updated_at = ahora

    def nueva_version(self, *, ahora: datetime) -> None:
        """The structure changed, so the confirmed mapping goes back to review (RN-03).

        The entries are kept: most of a changed spreadsheet is the same spreadsheet, and
        making the user redo forty assignments because one column was renamed is how a
        pause becomes an abandonment.
        """
        self.estado = EstadoMapeo.BORRADOR
        self.version += 1
        self.updated_at = ahora
