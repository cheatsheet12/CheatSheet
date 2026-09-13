"""`ParametroFiscal` — the aggregate behind HS-T4.

**This is the only table in the system with no `empresa_id`, and that is the point.** It is
ARCA's catalogue: the list of document types, VAT rates and document codes is the same for
every company in Argentina. Giving it a company column would mean one copy per tenant of a
table that is identical in all of them, and a bug in the sync would produce companies whose
fiscal reality disagreed with each other's.

**Versioned by validity, never overwritten** (RN-02). When ARCA changes a value, the old row
gets a `fecha_hasta` and a new one is inserted. That is what makes it possible to explain, in
December, why a document issued in March said what it said — and a document issued in March
is exactly the thing somebody reprints, or reverses with a credit note, months later.

The invariant that lives here: **two rows for the same `(tipo, codigo)` may not be valid at
the same time.** Two rates in force at once means the issuing code picks whichever the
database happened to return first, and the wrong one is a wrong tax on a real invoice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


class TipoCatalogoFiscal(StrEnum):
    """The six catalogues of the DER's `tipo_catalogo_fiscal`, and no others."""

    TIPO_COMPROBANTE = "TIPO_COMPROBANTE"
    ALICUOTA_IVA = "ALICUOTA_IVA"
    CONDICION_IVA = "CONDICION_IVA"
    TIPO_DOCUMENTO = "TIPO_DOCUMENTO"
    MONEDA = "MONEDA"
    UNIDAD_MEDIDA = "UNIDAD_MEDIDA"

    @property
    def es_numerico(self) -> bool:
        """Whether `valor` is meant to be read as a number.

        Only the rates are. Everything else is a label — «Factura A», «Pesos» — and asking
        for a `Decimal` of those is a bug the caller should find immediately.
        """
        return self is TipoCatalogoFiscal.ALICUOTA_IVA


@dataclass(frozen=True, slots=True, kw_only=True)
class ParametroFiscal:
    """One catalogue entry, valid over a date range.

    Frozen: closing a validity range produces a new object rather than mutating this one.
    A parameter that could be edited in place is a parameter whose history is a lie, and
    the history is the entire reason this table exists.
    """

    id: UUID
    tipo: TipoCatalogoFiscal
    #: ARCA's own code, e.g. `1` for Factura A or `5` for the 21 % rate. Text, because
    #: ARCA's codes are not all numeric and none of them are arithmetic.
    codigo: str
    valor: str
    fecha_desde: date
    #: `None` means «still in force». Closing a range sets it to the day before the
    #: successor starts, so the two never overlap by a day.
    fecha_hasta: date | None = None

    def __post_init__(self) -> None:
        if not self.codigo.strip():
            raise EntradaInvalida("Un parametro fiscal necesita su codigo de ARCA")
        if not self.valor.strip():
            raise EntradaInvalida("Un parametro fiscal necesita un valor")
        if self.fecha_hasta is not None and self.fecha_hasta < self.fecha_desde:
            raise EntradaInvalida("La vigencia no puede terminar antes de empezar")

    @property
    def clave(self) -> tuple[TipoCatalogoFiscal, str]:
        """What identifies the *thing*, as opposed to this version of it."""
        return (self.tipo, self.codigo)

    def vigente_a(self, fecha: date) -> bool:
        """RN-03: in force **on a given date**, never «today».

        A default of today works ninety-nine times out of a hundred and fails on the
        hundredth, which is the reprint, the credit note issued months later, and the VAT
        book of epic 9.
        """
        if fecha < self.fecha_desde:
            return False
        return self.fecha_hasta is None or fecha <= self.fecha_hasta

    def se_solapa_con(self, otro: ParametroFiscal) -> bool:
        """Whether two versions of the same entry would both be in force at once."""
        if self.clave != otro.clave:
            return False
        fin_propio = self.fecha_hasta or date.max
        fin_ajeno = otro.fecha_hasta or date.max
        return self.fecha_desde <= fin_ajeno and otro.fecha_desde <= fin_propio

    def cerrar(self, *, hasta: date) -> ParametroFiscal:
        """Close this version's range, returning the closed copy (RN-02).

        Raises if the range would end before it began — which is what a sync running with
        a clock behind the previous one would produce, and silently accepting it would
        create a row that is in force on no day at all.
        """
        if self.fecha_hasta is not None:
            raise InvarianteViolada("Este parametro ya tiene su vigencia cerrada")
        if hasta < self.fecha_desde:
            raise EntradaInvalida("No se puede cerrar la vigencia antes de la fecha en que empezo")
        return ParametroFiscal(
            id=self.id,
            tipo=self.tipo,
            codigo=self.codigo,
            valor=self.valor,
            fecha_desde=self.fecha_desde,
            fecha_hasta=hasta,
        )

    def como_decimal(self) -> Decimal:
        """The value as a number, for the catalogues where that means something.

        `Decimal` from the stored **string**, never through a `float` (`CLAUDE.md` §3.5):
        this is the rate that multiplies the amount on a real invoice.
        """
        if not self.tipo.es_numerico:
            raise InvarianteViolada(
                f"El catalogo {self.tipo.value} no guarda numeros: su valor es una etiqueta"
            )
        try:
            return Decimal(self.valor)
        except InvalidOperation as exc:
            raise InvarianteViolada(
                f"El parametro {self.codigo} guarda '{self.valor}', que no es un numero"
            ) from exc
