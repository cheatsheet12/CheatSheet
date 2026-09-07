"""`Comprobante` — the aggregate behind HU-E5-03, and the riskiest file in the system.

A `Comprobante` documents a sale before the AFIP. Once ARCA authorises it and returns a
CAE it is **legally irreversible**: there is no `DELETE`, no rollback, no "we fix it in the
next deploy". A wrongly issued document is undone with a credit note, which also goes to
ARCA and also stays.

Three invariants live here and none of them is decoration:

1. **The money adds up by construction.** Rounding happens per item, with `quantize` and
   `ROUND_HALF_UP` (decision D15), and the totals are sums of already-rounded values. ARCA
   validates that the totals close against the sum of items and rejects with a code that
   says nothing about a missing centavo.
2. **The type must be legal for the pair of VAT conditions** (RN-01, decision D16). A
   Responsable Inscripto invoices A to another Responsable Inscripto and B to a Consumidor
   Final; the rest of the table is here and it is closed.
3. **The state machine only goes forward.** In particular `AUTORIZADO` is terminal: a
   document with a CAE never changes again. The one transition that looks like an exception
   -- `AUTORIZADO → ANULADO` -- is not the document changing, it is the credit note of
   epic 5's last unit recording that it was reversed.

The receptor's data is **denormalised on purpose** (DER, BC6): a document already issued
does not change because the client later edits their address.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.fiscal import CondicionIVA

#: Two decimal places, always, and the direction stated rather than left to the default.
#: `CLAUDE.md` §5: money is `Decimal` and rounding is explicit.
CENTAVOS = Decimal("0.01")

#: HU-E5-03, word for word. Constants because the story writes them and tests assert them.
MENSAJE_SIN_ITEMS = "Debe agregar al menos un ítem para emitir el comprobante."
MENSAJE_PRECIO_NO_POSITIVO = "El precio unitario debe ser mayor a cero."
MENSAJE_TIPO_INVALIDO = "El tipo de comprobante no es válido para la condición de IVA del receptor."
MENSAJE_CUIT_INVALIDO = "El CUIT ingresado no es válido. Debe contener 11 dígitos correctos."
MENSAJE_CUIT_NO_ENCONTRADO = "No se encontró el CUIT en el padrón de ARCA."


def redondear(monto: Decimal) -> Decimal:
    """Two decimals, `ROUND_HALF_UP`. The only place this system rounds money."""
    return monto.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


class AlicuotaIVA(StrEnum):
    """The VAT rate of an item, **with the code WSFEv1 wants** (`Id` in `Iva`).

    `master_data` has an enum by the same name and this is deliberately not it: rule R3
    forbids the import, and the reason is better than the rule. That one is the rate a
    service is *priced* at today; this one is the rate a document was *issued* at, which is
    a different fact that must never move again. A `Comprobante` copies the rate at issue
    time and validates the copy — it does not read the catalogue back.

    The value is the rate as a string so the `Decimal` is built from text, never from a
    float literal.
    """

    CERO = "0.00"
    REDUCIDA = "0.105"
    GENERAL = "0.21"

    @property
    def tasa(self) -> Decimal:
        return Decimal(self.value)

    @property
    def codigo_arca(self) -> int:
        """ARCA's `Id` for this rate. Published codes, written out and not derived."""
        return _CODIGOS_DE_ALICUOTA[self]

    @classmethod
    def desde_tasa(cls, tasa: Decimal) -> AlicuotaIVA:
        """Rebuild from the column, comparing numerically.

        `NUMERIC(5, 4)` comes back as `Decimal("0.1050")`, and `"0.1050" != "0.105"` while
        the two numbers are equal.
        """
        for miembro in cls:
            if miembro.tasa == tasa:
                return miembro
        raise EntradaInvalida(f"'{tasa}' no es una alicuota de IVA conocida")


_CODIGOS_DE_ALICUOTA: dict[AlicuotaIVA, int] = {
    AlicuotaIVA.CERO: 3,
    AlicuotaIVA.REDUCIDA: 4,
    AlicuotaIVA.GENERAL: 5,
}


class EstadoComprobante(StrEnum):
    """The DER's `estado_comprobante`.

    **`ENVIADO_A_ARCA` is the state that makes decision D17 possible**, and it is worth
    saying what it means: *we do not know*. The envelope left and no answer came back. A
    document sitting there may or may not carry a CAE at the AFIP, and the only way to find
    out is to ask (`FECompConsultar`) — never to send it again.
    """

    BORRADOR = "BORRADOR"
    VALIDADO = "VALIDADO"
    ENVIADO_A_ARCA = "ENVIADO_A_ARCA"
    AUTORIZADO = "AUTORIZADO"
    RECHAZADO = "RECHAZADO"
    ANULADO = "ANULADO"


#: Which transitions exist. Written as a table for the reason `TareaAsincrona` gives: a
#: state machine spread across ten `if`s is a state machine nobody can check.
#:
#: **`AUTORIZADO → AUTORIZADO` is absent, and that absence is load-bearing.** It is what
#: makes the reconciliation of D17 idempotent: a sweep that finds a document already
#: authorised cannot overwrite its CAE with a second one.
#:
#: `RECHAZADO → VALIDADO` exists because a rejection is an *answer*: ARCA said no, the
#: number was returned, and the user may fix the document and try again.
TRANSICIONES_LEGALES: dict[EstadoComprobante, frozenset[EstadoComprobante]] = {
    EstadoComprobante.BORRADOR: frozenset({EstadoComprobante.VALIDADO}),
    EstadoComprobante.VALIDADO: frozenset(
        {EstadoComprobante.ENVIADO_A_ARCA, EstadoComprobante.BORRADOR}
    ),
    EstadoComprobante.ENVIADO_A_ARCA: frozenset(
        {EstadoComprobante.AUTORIZADO, EstadoComprobante.RECHAZADO}
    ),
    EstadoComprobante.AUTORIZADO: frozenset({EstadoComprobante.ANULADO}),
    EstadoComprobante.RECHAZADO: frozenset({EstadoComprobante.VALIDADO}),
    EstadoComprobante.ANULADO: frozenset(),
}


#: RN-01 and decision D16: which document types are legal for which pair of VAT conditions.
#:
#: **This is the structure of the regime, not a quarterly parameter.** A Responsable
#: Inscripto invoices A to another Responsable Inscripto — because the buyer can compute
#: the VAT — and B to everybody else. A Monotributista or an Exento invoices C to anyone,
#: because they do not discriminate VAT at all. Modelling this as a versioned parameter
#: would invite somebody to "update" it by syncing, and a document issued yesterday would
#: then validate against today's table.
#:
#: Keys are `(emisor, receptor)`. Absent pair means the combination is not offered.
TIPOS_VALIDOS: dict[tuple[CondicionIVA, CondicionIVA], frozenset[TipoComprobante]] = {
    (CondicionIVA.RESPONSABLE_INSCRIPTO, CondicionIVA.RESPONSABLE_INSCRIPTO): frozenset(
        {TipoComprobante.FACTURA_A, TipoComprobante.NOTA_CREDITO_A}
    ),
    (CondicionIVA.RESPONSABLE_INSCRIPTO, CondicionIVA.MONOTRIBUTO): frozenset(
        {TipoComprobante.FACTURA_B, TipoComprobante.NOTA_CREDITO_B}
    ),
    (CondicionIVA.RESPONSABLE_INSCRIPTO, CondicionIVA.EXENTO): frozenset(
        {TipoComprobante.FACTURA_B, TipoComprobante.NOTA_CREDITO_B}
    ),
    (CondicionIVA.RESPONSABLE_INSCRIPTO, CondicionIVA.CONSUMIDOR_FINAL): frozenset(
        {TipoComprobante.FACTURA_B, TipoComprobante.NOTA_CREDITO_B}
    ),
}
# Monotributo and Exento issue C to everyone, including each other. Written as a loop
# rather than twelve literal rows: the rule really is "the receptor does not matter", and
# spelling out twelve identical entries would hide that.
for _emisor in (CondicionIVA.MONOTRIBUTO, CondicionIVA.EXENTO):
    for _receptor in CondicionIVA:
        TIPOS_VALIDOS[(_emisor, _receptor)] = frozenset(
            {TipoComprobante.FACTURA_C, TipoComprobante.NOTA_CREDITO_C}
        )


def tipos_permitidos(*, emisor: CondicionIVA, receptor: CondicionIVA) -> frozenset[TipoComprobante]:
    """What RN-01 allows for this pair. Empty when the combination is not invoiceable."""
    return TIPOS_VALIDOS.get((emisor, receptor), frozenset())


@dataclass(frozen=True, slots=True)
class Receptor:
    """Who the document is issued to, **copied at issue time** (DER, BC6).

    Denormalised on purpose: a document already issued does not change because the client
    later edits their name. The `cliente_id` still points at the catalogue for navigation;
    these fields are what was true the day it was issued.
    """

    nombre: str
    cuit: str
    condicion_iva: CondicionIVA
    domicilio: str | None = None


@dataclass(frozen=True, slots=True)
class CAE:
    """ARCA's authorisation code and the date it stops being usable.

    Frozen, and there is no method to change it. A CAE that could be overwritten is a CAE
    that a retry could replace with a second one — which is the failure D17 exists to
    prevent, expressed as a type.
    """

    codigo: str
    vence_el: date


@dataclass(slots=True)
class ItemDeComprobante:
    """One line. **The only place in the system where money is multiplied.**

    `subtotal` and `iva` are computed and rounded here, per item, and never recomputed
    downstream: the totals of the document are sums of these already-rounded values. That
    is decision D15, and it is what makes `subtotal + total_iva == total` true by
    construction rather than by luck.
    """

    id: UUID
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    alicuota_iva: AlicuotaIVA

    def __post_init__(self) -> None:
        if not self.descripcion.strip():
            raise EntradaInvalida("El item necesita una descripcion")
        if self.cantidad <= 0:
            raise EntradaInvalida("La cantidad debe ser mayor a cero")
        if self.precio_unitario <= 0:
            # HU-E5-03's own sentence, so it reaches the screen unchanged.
            raise EntradaInvalida(MENSAJE_PRECIO_NO_POSITIVO)

    @property
    def subtotal(self) -> Decimal:
        """Net of VAT, rounded here and nowhere else."""
        return redondear(self.cantidad * self.precio_unitario)

    @property
    def iva(self) -> Decimal:
        """VAT over the **already rounded** subtotal, not over the raw product.

        Rounding twice from the raw product and from the subtotal can differ by a centavo,
        and a centavo is what ARCA rejects the document for.
        """
        return redondear(self.subtotal * self.alicuota_iva.tasa)

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.iva


@dataclass(slots=True)
class Comprobante:
    """A document, from draft to CAE.

    Construction does **not** validate: a `BORRADOR` is allowed to be incomplete, which is
    what the screen edits. `validar()` is the gate, and nothing reaches the wire without
    passing it.
    """

    id: UUID
    empresa_id: EmpresaId
    cliente_id: UUID
    punto_de_venta_id: UUID
    tipo: TipoComprobante
    receptor: Receptor
    #: The issuer's VAT condition, copied like the receptor's and for the same reason: it
    #: is what made this type legal, and a company that later changes condition must not
    #: retroactively invalidate what it already issued.
    emisor_condicion_iva: CondicionIVA
    created_at: datetime
    items: list[ItemDeComprobante] = field(default_factory=list)
    estado: EstadoComprobante = EstadoComprobante.BORRADOR
    #: Drawn from the point of sale when the document is sent, never before: a number
    #: reserved for a draft that is never sent is a hole in the numbering.
    numero: int | None = None
    cae: CAE | None = None
    fecha_emision: datetime | None = None
    #: What ARCA answered when it said no. Shown on PAN-FAC-02 as it came — «Error 10016:
    #: el comprobante no cumple la resolución general vigente.» is ARCA's sentence, not
    #: ours, and paraphrasing it would make it unsearchable.
    motivo_de_rechazo: str | None = None
    comprobante_origen_id: UUID | None = None
    #: Referenced by id and without a foreign key (DER hallazgo H4): `turno` belongs to
    #: another context. Nothing produces it until epic 7.
    turno_id: UUID | None = None
    #: HU-E5-03 RN-06. Registered here; epic 6 is what consumes it.
    saldo_pendiente: Decimal = Decimal("0.00")

    # ------------------------------------------------------------------ the money

    @property
    def subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.items), Decimal("0.00"))

    @property
    def total_iva(self) -> Decimal:
        return sum((item.iva for item in self.items), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.total_iva

    # ------------------------------------------------------------------ editing

    def agregar_item(self, item: ItemDeComprobante) -> None:
        self._exigir_editable()
        self.items.append(item)
        self.saldo_pendiente = self.total

    def quitar_item(self, item_id: UUID) -> None:
        self._exigir_editable()
        self.items = [item for item in self.items if item.id != item_id]
        self.saldo_pendiente = self.total

    def _exigir_editable(self) -> None:
        """RN-01 of HU-E5-02, enforced rather than described.

        An authorised document is immutable. So is one in flight: changing the items of a
        document ARCA may already have authorised would make our copy disagree with the
        legal one.
        """
        if self.estado not in (EstadoComprobante.BORRADOR, EstadoComprobante.VALIDADO):
            raise InvarianteViolada(
                f"Un comprobante en estado {self.estado.value} no se puede modificar"
            )
        if self.estado is EstadoComprobante.VALIDADO:
            # Editing sends it back to draft: what was validated is no longer what is here.
            self.estado = EstadoComprobante.BORRADOR

    # ------------------------------------------------------------------ the states

    def validar(self) -> None:
        """The gate. Nothing reaches WSFEv1 without passing it.

        Checks the three things that get a document rejected, in the order in which the
        user can fix them.
        """
        if not self.items:
            raise EntradaInvalida(MENSAJE_SIN_ITEMS)

        permitidos = tipos_permitidos(
            emisor=self.emisor_condicion_iva, receptor=self.receptor.condicion_iva
        )
        if self.tipo not in permitidos:
            raise EntradaInvalida(MENSAJE_TIPO_INVALIDO)

        # True by construction (D15), asserted anyway. If it ever stops being true, the
        # place to find out is here and not in ARCA's rejection code.
        if self.subtotal + self.total_iva != self.total:  # pragma: no cover - by construction
            raise InvarianteViolada("Los totales del comprobante no cierran")

        self._transicionar(EstadoComprobante.VALIDADO)

    def enviar_a_arca(self, numero: int, ahora: datetime) -> None:
        """Take the number and record that the envelope is about to leave.

        **Persisted before the call, in its own transaction.** That ordering is the whole
        of decision D17: a document in `ENVIADO_A_ARCA` means "we do not know", and not
        knowing is recoverable. Sending first and recording afterwards is not.
        """
        self._transicionar(EstadoComprobante.ENVIADO_A_ARCA)
        self.numero = numero
        self.fecha_emision = ahora

    def autorizar(self, cae: CAE) -> None:
        """ARCA said yes. Terminal, and the transition table is what makes it terminal."""
        self._transicionar(EstadoComprobante.AUTORIZADO)
        self.cae = cae
        self.motivo_de_rechazo = None

    def rechazar(self, motivo: str) -> None:
        """ARCA said no — which is an **answer**, not an unknown.

        That distinction is why the number can be returned to the point of sale here and
        must not be returned on a timeout: a rejection means ARCA has nothing recorded
        under that number.
        """
        self._transicionar(EstadoComprobante.RECHAZADO)
        self.motivo_de_rechazo = motivo

    def anular(self) -> None:
        """Reversed by a credit note (HU-E5-04). The document itself does not change."""
        self._transicionar(EstadoComprobante.ANULADO)

    def _transicionar(self, destino: EstadoComprobante) -> None:
        if destino not in TRANSICIONES_LEGALES[self.estado]:
            raise InvarianteViolada(
                f"Un comprobante no pasa de {self.estado.value} a {destino.value}"
            )
        self.estado = destino

    # ------------------------------------------------------------------ queries

    @property
    def esta_en_vuelo(self) -> bool:
        """Sent and unanswered: the state decision D17 reconciles."""
        return self.estado is EstadoComprobante.ENVIADO_A_ARCA

    @property
    def es_descargable(self) -> bool:
        """HU-E5-02: the PDF is offered only for an authorised document."""
        return self.estado in (EstadoComprobante.AUTORIZADO, EstadoComprobante.ANULADO)


def nota_de_credito_para(
    original: Comprobante,
    *,
    nota_id: UUID,
    items: list[ItemDeComprobante],
    ahora: datetime,
) -> Comprobante:
    """Build the credit note that reverses `original` (HU-E5-04 RN-01, RN-02).

    **The type is determined, never chosen** (RN-02): a B invoice is reversed by a B credit
    note, and offering the other two would be offering a document ARCA rejects. So is the
    receptor -- copied from the original rather than re-read from the client catalogue,
    because what is being reversed is what was issued, and the client may have edited their
    name since.

    The amount is *not* checked here. It needs the other credit notes already authorised
    against the same original, which is a repository question, so it lives in the use case
    -- and this function stays a pure construction that cannot be wrong about the database.
    """
    if original.estado is not EstadoComprobante.AUTORIZADO:
        raise InvarianteViolada("Solo se puede anular un comprobante autorizado por ARCA")

    nota = Comprobante(
        id=nota_id,
        empresa_id=original.empresa_id,
        cliente_id=original.cliente_id,
        # The same point of sale as the original. ARCA keeps a separate counter per type
        # there, so the credit note gets its own sequence without any special handling.
        punto_de_venta_id=original.punto_de_venta_id,
        tipo=original.tipo.nota_de_credito,
        receptor=original.receptor,
        emisor_condicion_iva=original.emisor_condicion_iva,
        created_at=ahora,
        comprobante_origen_id=original.id,
    )
    for item in items:
        nota.agregar_item(item)
    return nota


def monto_anulado(notas: list[Comprobante]) -> Decimal:
    """How much of an original has been reversed. **Decision D19: derived, not stored.**

    Only authorised notes count. One that ARCA rejected reversed nothing, and one still in
    flight has not reversed anything *yet* -- counting it would let somebody reverse the
    same amount twice while the first attempt is unresolved.
    """
    return sum(
        (nota.total for nota in notas if nota.estado is EstadoComprobante.AUTORIZADO),
        Decimal("0.00"),
    )


__all__ = [
    "CAE",
    "CENTAVOS",
    "MENSAJE_CUIT_INVALIDO",
    "MENSAJE_CUIT_NO_ENCONTRADO",
    "MENSAJE_PRECIO_NO_POSITIVO",
    "MENSAJE_SIN_ITEMS",
    "MENSAJE_TIPO_INVALIDO",
    "TIPOS_VALIDOS",
    "TRANSICIONES_LEGALES",
    "AlicuotaIVA",
    "Comprobante",
    "EstadoComprobante",
    "ItemDeComprobante",
    "Receptor",
    "monto_anulado",
    "nota_de_credito_para",
    "redondear",
    "tipos_permitidos",
]
