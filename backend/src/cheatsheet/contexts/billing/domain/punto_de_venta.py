"""`PuntoDeVenta` — the aggregate behind HU-E5-05.

A point of sale is a number ARCA gave the company and a counter per document type. That
counter is the whole risk of this file: **two documents may never carry the same number**.
ARCA rejects the second, or — worse — authorises both, and two authorised documents with
the same number is a fiscal inconsistency fixed with the AFIP and not with an `UPDATE`.

The aggregate keeps the counter honest for one caller. **It cannot keep it honest against
two**, and pretending otherwise would be the dangerous kind of wrong: `siguiente_numero`
raises the counter in memory, and what serialises two simultaneous callers is the
`SELECT … FOR UPDATE` in the repository (decision D14). Both are needed and neither is
sufficient — the same arrangement epic 1 used for «always at least one Administrador».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: ARCA numbers points of sale from 1 to 99 999. Zero is not a point of sale, and the
#: ceiling is the field width in WSFEv1's request.
NUMERO_MINIMO = 1
NUMERO_MAXIMO = 99_999


class TipoComprobante(StrEnum):
    """The DER's `tipo_comprobante`, and the ARCA code each one carries.

    **The code is what goes on the wire** (`CbteTipo` in WSFEv1) and the name is what goes
    on the screen. Keeping both here rather than looking the code up in `parametro_fiscal`
    is decision D16 applied one level down: the correspondence between «Factura A» and code
    1 is the structure of the regime, not a quarterly parameter. The catalogue is what
    tells us the type is *enabled*; this is what tells us what it is called.
    """

    FACTURA_A = "FACTURA_A"
    FACTURA_B = "FACTURA_B"
    FACTURA_C = "FACTURA_C"
    NOTA_CREDITO_A = "NOTA_CREDITO_A"
    NOTA_CREDITO_B = "NOTA_CREDITO_B"
    NOTA_CREDITO_C = "NOTA_CREDITO_C"

    @property
    def codigo_arca(self) -> int:
        return _CODIGOS[self]

    @property
    def es_nota_de_credito(self) -> bool:
        return self.name.startswith("NOTA_CREDITO")

    @property
    def letra(self) -> str:
        """A, B or C. What decides which credit note reverses which invoice (RN-02)."""
        return self.name[-1]

    @property
    def nota_de_credito(self) -> TipoComprobante:
        """The credit note that reverses this invoice (HU-E5-04 RN-02).

        Determined by the system and never chosen by the user: a B invoice is reversed by
        a B credit note, and offering the other two would be offering a document ARCA
        rejects.
        """
        if self.es_nota_de_credito:
            raise InvarianteViolada("Una nota de credito no se anula con otra nota de credito")
        return TipoComprobante(f"NOTA_CREDITO_{self.letra}")


#: ARCA's published codes. Written out rather than derived: they are not sequential and
#: guessing one wrong produces a document of the wrong type, authorised.
_CODIGOS: dict[TipoComprobante, int] = {
    TipoComprobante.FACTURA_A: 1,
    TipoComprobante.NOTA_CREDITO_A: 3,
    TipoComprobante.FACTURA_B: 6,
    TipoComprobante.NOTA_CREDITO_B: 8,
    TipoComprobante.FACTURA_C: 11,
    TipoComprobante.NOTA_CREDITO_C: 13,
}


@dataclass(slots=True, kw_only=True)
class PuntoDeVenta:
    """One point of sale, with a counter per document type (RN-02)."""

    id: UUID
    empresa_id: EmpresaId
    numero: int
    descripcion: str | None = None
    activo: bool = True
    #: `{tipo: ultimo_numero_usado}`. Absent means «none issued yet», which is not the same
    #: as zero for anybody reading the row, and is the same for the arithmetic.
    numerador_por_tipo: dict[str, int] = field(default_factory=dict)
    created_at: datetime

    def __post_init__(self) -> None:
        if not NUMERO_MINIMO <= self.numero <= NUMERO_MAXIMO:
            raise EntradaInvalida(
                f"El numero de punto de venta va de {NUMERO_MINIMO} a {NUMERO_MAXIMO}"
            )
        if self.created_at.tzinfo is None:
            raise EntradaInvalida("created_at debe tener zona horaria (UTC)")

    @property
    def puede_emitir(self) -> bool:
        """RN-04: deactivating stops new documents and touches none of the old ones."""
        return self.activo

    def ultimo_numero(self, tipo: TipoComprobante) -> int:
        """What ARCA last authorised for this type here. Zero when nothing has been."""
        return self.numerador_por_tipo.get(tipo.value, 0)

    def siguiente_numero(self, tipo: TipoComprobante) -> int:
        """Take the next number for this type, and record that it was taken.

        **This alone does not make the number unique.** It is correct for one caller; two
        callers reading the same row at the same time both get the same answer, and what
        stops that is the row lock in the repository (D14). The comment is here rather
        than only there because this is the method somebody will call from a new place.
        """
        if not self.activo:
            raise InvarianteViolada(
                f"El punto de venta {self.numero} esta desactivado: no puede emitir"
            )
        siguiente = self.ultimo_numero(tipo) + 1
        self.numerador_por_tipo[tipo.value] = siguiente
        return siguiente

    def sincronizar_con_arca(self, tipo: TipoComprobante, ultimo_en_arca: int) -> None:
        """Raise this counter to ARCA's if ARCA is ahead. **Decision D18.**

        WSFEv1 demands strictly correlative numbering per `(punto, tipo)`: send number 7
        when ARCA last authorised 4 and it rejects with «numero de comprobante no
        correlativo» — and it will keep rejecting until the two agree. So a gap is not a
        cosmetic blemish, it is an outage of the invoicing.

        Gaps happen for reasons this aggregate cannot prevent: a document rejected after a
        later one already drew its number, a row restored from a backup, a point of sale
        used from somewhere else. **ARCA's counter is the authority and ours is a cache**,
        so the number actually drawn is `max(ours, ARCA's) + 1`.

        It only ever goes **up**. Lowering it to match ARCA would hand out a number a
        document in flight may already be carrying, which is the one thing D14 exists to
        prevent -- and it would do it in the branch that looks like housekeeping.
        """
        if ultimo_en_arca > self.ultimo_numero(tipo):
            self.numerador_por_tipo[tipo.value] = ultimo_en_arca

    def devolver_numero(self, tipo: TipoComprobante, numero: int) -> bool:
        """Give a number back when ARCA never recorded it. Returns whether it could.

        Only the last one, and only if it is still the last one: giving back 5 when 6 has
        been drawn would hand 6 out twice. When it cannot, the sequence keeps a gap, and
        `sincronizar_con_arca` is what heals it on the next issue -- which is why this
        returns a bool instead of raising. A rejected document is not an error condition
        for the point of sale; it is the ordinary outcome of asking ARCA.
        """
        if self.ultimo_numero(tipo) != numero:
            return False
        self.numerador_por_tipo[tipo.value] = numero - 1
        return True

    def activar(self) -> None:
        """RN-03 is checked by the caller against ARCA; this only records the outcome.

        The aggregate cannot verify it — that needs a network call — and putting the check
        here would mean a domain object doing I/O. What it can do is refuse to be the place
        where the rule looks satisfied.
        """
        self.activo = True

    def desactivar(self) -> None:
        """RN-04. The counters are kept: reactivating must not restart the numbering."""
        self.activo = False
