"""`Cliente` — who the company sells to (HU-E4-01).

The first aggregate of `master_data`, and the one four other contexts will read:
`billing` puts it on a `Comprobante`, `payments` charges it, `scheduling` books it and
`conversational` talks to it (Context Map §4, C/S). That is why the rules live here and
not in the form.

**Only `nombre` is mandatory.** The DER leaves `cuit` and `condicion_iva` nullable and
this unit's plan keeps them that way, against a reading of HU-E4-01 RN-02 that assumes
every client has a tax id. The argument is not in this story but in HU-E8-01: the agent
registers clients from WhatsApp knowing nothing but a phone number, and a mandatory CUIT
would force it to invent one — the exact dirty data this context exists to keep out.

**`origen` has no setter.** RN-01 says it is assigned automatically and is not editable,
and the way to say that in a domain model is that the operation does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cheatsheet.contexts.master_data.domain.normalizacion import normalizar_nombre_de_cliente
from cheatsheet.contexts.master_data.domain.valores import OrigenDato
from cheatsheet.shared.contacto import Email, Telefono
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CUIT, CondicionIVA

LARGO_MAXIMO_NOMBRE = 200


@dataclass(slots=True)
class Cliente:
    """A customer of one company. Mutable: it has a lifecycle."""

    id: UUID
    empresa_id: EmpresaId
    nombre: str
    origen: OrigenDato
    creado_en: datetime
    actualizado_en: datetime
    cuit: CUIT | None = None
    condicion_iva: CondicionIVA | None = None
    contacto_whatsapp: Telefono | None = None
    contacto_email: Email | None = None
    #: ADR-006 and ADR-007 made columns. Epic 4 writes them; the panel never does.
    presente_en_planilla: bool = False
    referencia_fila_planilla: str | None = None
    activo: bool = True

    @classmethod
    def registrar(
        cls,
        *,
        id: UUID,
        empresa_id: EmpresaId,
        nombre: str,
        origen: OrigenDato,
        momento: datetime,
        cuit: CUIT | None = None,
        condicion_iva: CondicionIVA | None = None,
        contacto_whatsapp: Telefono | None = None,
        contacto_email: Email | None = None,
    ) -> Cliente:
        """Create one. `origen` is stated by the caller and never again."""
        return cls(
            id=id,
            empresa_id=empresa_id,
            nombre=_nombre_valido(nombre, cuit),
            origen=origen,
            creado_en=momento,
            actualizado_en=momento,
            cuit=cuit,
            condicion_iva=condicion_iva,
            contacto_whatsapp=contacto_whatsapp,
            contacto_email=contacto_email,
        )

    def renombrar(self, nombre: str, momento: datetime) -> None:
        self.nombre = _nombre_valido(nombre, self.cuit)
        self.actualizado_en = momento

    def actualizar_contacto(
        self,
        *,
        contacto_whatsapp: Telefono | None,
        contacto_email: Email | None,
        momento: datetime,
    ) -> None:
        """Both at once, and `None` clears. A contact detail can legitimately be removed."""
        self.contacto_whatsapp = contacto_whatsapp
        self.contacto_email = contacto_email
        self.actualizado_en = momento

    def actualizar_datos_fiscales(
        self,
        *,
        cuit: CUIT | None,
        condicion_iva: CondicionIVA | None,
        momento: datetime,
    ) -> None:
        """The pair moves together, because that is how ARCA's registry answers.

        Setting a CUIT while leaving the VAT condition behind would produce exactly the
        half-filled record that epic 5 cannot issue a Factura A against, without saying
        so at the moment somebody could still fix it.
        """
        self.cuit = cuit
        self.condicion_iva = condicion_iva
        self.actualizado_en = momento

    def desactivar(self, momento: datetime) -> None:
        """Hide from the active catalogue. **There is no delete.**

        ADR-007 says what leaves the spreadsheet is marked absent, never removed, and
        `comprobante`, `cobro` and `turno` reference this id **without a declared foreign
        key** (DER gap H4) — so nothing in the database would stop a physical delete from
        leaving tax documents pointing at nothing.
        """
        self.activo = False
        self.actualizado_en = momento

    def reactivar(self, momento: datetime) -> None:
        self.activo = True
        self.actualizado_en = momento

    @property
    def facturable_con_cuit(self) -> bool:
        """Whether epic 5 will be able to issue a Factura A to this client.

        Derived, never stored, and exposed here so `billing` does not have to rediscover
        the rule — it will still revalidate against ARCA, which is a different question.
        """
        return self.cuit is not None and self.condicion_iva is not None


def _nombre_valido(nombre: str, cuit: CUIT | None) -> str:
    """HU-E4-05: normalized first, validated after, so the length is the stored length.

    The CUIT decides whether the name is a person's or a company's (RN-03), which is why
    it must be set before a rename that comes with a new CUIT.
    """
    limpio = normalizar_nombre_de_cliente(nombre, cuit)
    if not limpio:
        raise EntradaInvalida("El nombre del cliente es obligatorio")
    if len(limpio) > LARGO_MAXIMO_NOMBRE:
        raise EntradaInvalida(f"El nombre del cliente excede {LARGO_MAXIMO_NOMBRE} caracteres")
    return limpio


@dataclass(frozen=True, slots=True)
class FiltrosDeCliente:
    """What PAN-DM-01 can narrow the listing by.

    A value object rather than five parameters threaded through the repository port: the
    listing gains filters as the epic advances — the category filter arrived with
    `categorias-y-clasificacion` and cost one field here instead of three signatures.
    """

    texto: str | None = None
    origen: OrigenDato | None = None
    solo_activos: bool = False
    #: HU-E4-04: «el cliente queda clasificado y es filtrable por esa categoria».
    categoria_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.texto is not None:
            limpio = self.texto.strip()
            object.__setattr__(self, "texto", limpio or None)


@dataclass(frozen=True, slots=True)
class Pagina:
    """Offset paging, which is what a catalogue screen with page numbers needs."""

    limite: int = 50
    desplazamiento: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limite <= 200:
            raise EntradaInvalida("El limite de la pagina debe estar entre 1 y 200")
        if self.desplazamiento < 0:
            raise EntradaInvalida("El desplazamiento de la pagina no puede ser negativo")


@dataclass(frozen=True, slots=True)
class ListadoDeClientes:
    """One page plus the total, because the screen shows «N clientes»."""

    clientes: tuple[Cliente, ...] = field(default_factory=tuple)
    total: int = 0
