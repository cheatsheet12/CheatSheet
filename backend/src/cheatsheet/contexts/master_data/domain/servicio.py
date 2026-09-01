"""`Servicio` — what the company sells (HU-E4-02).

The second aggregate of `master_data`, and the one that brings **money into the system**:
`precio` is the first `Decimal` this codebase stores. What is decided here gets copied by
`billing` in epic 5, by `payments` in epic 6 and by the deposit of a `Turno` in epic 7, so
the rules of `docs/code-standards.md` §2.5 are applied literally rather than approximately.

**This module never multiplies.** It holds a net price and a VAT rate side by side and
that is all. Computing what a customer owes is issuance, it happens once per document
rather than once per line, and it belongs to `billing`. A helper here that returned "price
with VAT" would be the seed of two places rounding the same money differently.

**Two invariants live here and not in the form** (RN-02 and RN-03), because the agent of
epic 8 and the spreadsheet importer of epic 4 will create services too, and neither of
them is going to fill in a form.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

LARGO_MAXIMO_NOMBRE = 200

#: Prices are stored to the cent. Not an obvious choice, so it is written down: the peso
#: has cents, a small business enters list prices with them, and a unit price carrying
#: more precision than can be invoiced produces totals that do not add up against the
#: document. A trade that needs four decimals is a schema change with a story behind it.
CENTAVOS = Decimal("0.01")

#: The exact texts of HU-E4-02's acceptance criteria. Without accents, like every other
#: message in this system.
MENSAJE_PRECIO = "El precio debe ser mayor a cero."
MENSAJE_DURACION = "La duracion es obligatoria para servicios agendables."


@dataclass(slots=True)
class Servicio:
    """A service of one company. Mutable: it has a lifecycle."""

    id: UUID
    empresa_id: EmpresaId
    nombre: str
    precio: Decimal
    alicuota_iva: AlicuotaIVA
    origen: OrigenDato
    creado_en: datetime
    actualizado_en: datetime
    agendable: bool = False
    duracion_estandar_min: int | None = None
    #: ADR-006 and ADR-007 made columns, exactly as on `Cliente`. Epic 4 writes them.
    presente_en_planilla: bool = False
    activo: bool = True

    @classmethod
    def registrar(
        cls,
        *,
        id: UUID,
        empresa_id: EmpresaId,
        nombre: str,
        precio: Decimal,
        alicuota_iva: AlicuotaIVA,
        origen: OrigenDato,
        momento: datetime,
        agendable: bool = False,
        duracion_estandar_min: int | None = None,
    ) -> Servicio:
        """Create one, with both invariants checked before the object exists."""
        return cls(
            id=id,
            empresa_id=empresa_id,
            nombre=_nombre_valido(nombre),
            precio=precio_valido(precio),
            alicuota_iva=alicuota_iva,
            origen=origen,
            creado_en=momento,
            actualizado_en=momento,
            agendable=agendable,
            duracion_estandar_min=_duracion_valida(agendable, duracion_estandar_min),
        )

    def renombrar(self, nombre: str, momento: datetime) -> None:
        self.nombre = _nombre_valido(nombre)
        self.actualizado_en = momento

    def cambiar_precio(self, precio: Decimal, momento: datetime) -> None:
        """The new price applies to what happens next, and to nothing already issued.

        That second half is not enforced here because it cannot be: a `Comprobante` copies
        the price it was issued with (the DER denormalises it on purpose). This method
        simply has no way to reach a document, which is the property that makes the
        acceptance criterion true.
        """
        self.precio = precio_valido(precio)
        self.actualizado_en = momento

    def cambiar_alicuota(self, alicuota: AlicuotaIVA, momento: datetime) -> None:
        self.alicuota_iva = alicuota
        self.actualizado_en = momento

    def volver_agendable(self, duracion_estandar_min: int, momento: datetime) -> None:
        """RN-01: a bookable service declares how long it takes."""
        self.agendable = True
        self.duracion_estandar_min = _duracion_valida(True, duracion_estandar_min)
        self.actualizado_en = momento

    def dejar_de_ser_agendable(self, momento: datetime) -> None:
        """And it loses its duration in the same operation, deliberately.

        Keeping it "in case it comes back" leaves a number the screen does not show and
        nobody maintains — and epic 7 would read it as if it meant something.
        """
        self.agendable = False
        self.duracion_estandar_min = None
        self.actualizado_en = momento

    def desactivar(self, momento: datetime) -> None:
        """RN-04: hides it from the active catalogue and touches no history.

        There is no delete, for the same reason there is none on `Cliente`: `comprobante`
        and `turno` reference this id, and the migration grants the application no
        `DELETE` at all.
        """
        self.activo = False
        self.actualizado_en = momento

    def reactivar(self, momento: datetime) -> None:
        self.activo = True
        self.actualizado_en = momento


def precio_valido(precio: Decimal) -> Decimal:
    """Refuse what is not a finite number, quantise to the cent, then refuse what is not
    above zero.

    **Each of the three steps is in that order for a reason.**

    `is_finite` goes first because `Decimal("NaN").quantize(...)` does **not** raise — it
    returns `NaN` quietly, and the comparison two lines below is what would then blow up,
    with an `InvalidOperation` nobody catches and a 500 instead of a 422. (Infinity does
    raise on `quantize`, which is why only one of the two was ever visible.)

    Quantising before comparing means a price below half a cent — `Decimal("0.004")` —
    becomes `0.00` and is then refused, which is right: it is not a price. Comparing first
    and rounding after would let it through as a zero-peso service.
    """
    if not precio.is_finite():
        raise EntradaInvalida(MENSAJE_PRECIO)
    try:
        cuantizado = precio.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        # A number too large to fit the scale. Not money either.
        raise EntradaInvalida(MENSAJE_PRECIO) from exc
    if cuantizado <= 0:
        raise EntradaInvalida(MENSAJE_PRECIO)
    return cuantizado


def _duracion_valida(agendable: bool, duracion: int | None) -> int | None:
    """RN-03, and its mirror: a service that is not bookable carries no duration.

    The mirror is not in the story and follows from it. If a non-bookable service kept a
    duration, the two fields could disagree, and the screen that hides the field would be
    hiding a value that is still there.
    """
    if not agendable:
        return None
    if duracion is None or duracion <= 0:
        raise EntradaInvalida(MENSAJE_DURACION)
    return duracion


def _nombre_valido(nombre: str) -> str:
    limpio = nombre.strip()
    if not limpio:
        raise EntradaInvalida("El nombre del servicio es obligatorio")
    if len(limpio) > LARGO_MAXIMO_NOMBRE:
        raise EntradaInvalida(f"El nombre del servicio excede {LARGO_MAXIMO_NOMBRE} caracteres")
    return limpio


@dataclass(frozen=True, slots=True)
class FiltrosDeServicio:
    """What PAN-DM-02 can narrow the listing by."""

    texto: str | None = None
    agendable: bool | None = None
    solo_activos: bool = False

    def __post_init__(self) -> None:
        if self.texto is not None:
            limpio = self.texto.strip()
            object.__setattr__(self, "texto", limpio or None)


@dataclass(frozen=True, slots=True)
class ListadoDeServicios:
    """One page plus the total, because the screen shows «N servicios»."""

    servicios: tuple[Servicio, ...] = field(default_factory=tuple)
    total: int = 0
