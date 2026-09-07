"""Writing into the catalogue from a spreadsheet (HU-E3-03), for `spreadsheet_sync`.

**Why this lives in `master_data` and not in the context that calls it.** Rule R3 forbids
`spreadsheet_sync` from reaching into `master_data/domain` or its repositories; the Context
Map declares the edge `spreadsheet_sync → master_data`, and an edge like that is travelled
through an application service. So the ingestion asks for what it wants in this context's
own words, and this context decides what that means for a `Cliente`.

**It is not `RegistrarCliente` with a parameter.** That use case *is* the panel: it hard-
codes `origen = PANEL`, consults the ARCA registry on every write, and refuses a duplicate
CUIT. All three are wrong here:

- `origen` must be `PLANILLA` (HU-E4-01 RN-01), which is what later tells a write-back that
  this row came from the sheet and must not be written back into it (HU-E3-07 RN-03).
- **The registry is not consulted.** A forty-thousand-row import would make forty thousand
  calls to ARCA, and ARCA would stop answering long before the end.
- **A repeated CUIT is an update, not a rejection.** The spreadsheet is the source of truth
  for master data (ADR-006), so a row whose CUIT we already know is the same customer with
  newer data — refusing it would make the second sync of every company fail entirely.

**Nothing is ever deleted** (ADR-007). A customer who disappears from the spreadsheet is
marked `presente_en_planilla = False` by the sync unit; this one only ever writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from cheatsheet.contexts.master_data.application.ports import (
    PortRepositorioCliente,
    PortRepositorioServicio,
)
from cheatsheet.contexts.master_data.domain.cliente import Cliente, FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.servicio import Servicio
from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.shared.contacto import Email, Telefono
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import ErrorDeDominio
from cheatsheet.shared.fiscal import CUIT, CondicionIVA


@dataclass(frozen=True, slots=True)
class FilaDeCatalogo:
    """One spreadsheet row, already mapped to this context's vocabulary.

    Every field is text, because that is what a spreadsheet cell is. Turning `"21"` into an
    `AlicuotaIVA` and `"1.234,50"` into a `Decimal` is this module's job, and it is exactly
    where a row earns its place in `ErrorDeFila` instead of in the catalogue.
    """

    nombre: str | None = None
    cuit: str | None = None
    condicion_iva: str | None = None
    contacto_whatsapp: str | None = None
    contacto_email: str | None = None
    precio: str | None = None
    alicuota_iva: str | None = None
    agendable: str | None = None
    duracion_estandar_min: str | None = None


@dataclass(frozen=True, slots=True)
class ResultadoDeIngesta:
    """What happened to one row. `creado` False means an existing record was updated."""

    creado: bool


class IngerirClienteDesdePlanilla:
    """Create or update one `Cliente` from a spreadsheet row (HU-E3-03)."""

    def __init__(self, clientes: PortRepositorioCliente) -> None:
        self._clientes = clientes

    async def ejecutar(
        self, *, empresa_id: EmpresaId, fila: FilaDeCatalogo, ahora: datetime
    ) -> ResultadoDeIngesta:
        nombre = (fila.nombre or "").strip()
        if not nombre:
            # The one field with no sensible default. A catalogue of customers with no
            # names is worse than a row that failed and says why.
            raise ErrorDeDominio("La fila no tiene nombre")

        cuit = CUIT(fila.cuit.strip()) if fila.cuit and fila.cuit.strip() else None
        condicion = _condicion_iva(fila.condicion_iva)
        whatsapp = Telefono(fila.contacto_whatsapp) if fila.contacto_whatsapp else None
        email = Email(fila.contacto_email) if fila.contacto_email else None

        existente = await self._clientes.buscar_por_cuit(str(cuit)) if cuit else None
        if existente is not None:
            # The spreadsheet wins for master data (ADR-006), so the sheet's values
            # overwrite ours -- except `origen`, which records where the record was born
            # and never changes.
            existente.renombrar(nombre, ahora)
            existente.actualizar_contacto(
                contacto_whatsapp=whatsapp, contacto_email=email, momento=ahora
            )
            existente.presente_en_planilla = True
            await self._clientes.guardar(existente)
            return ResultadoDeIngesta(creado=False)

        cliente = Cliente.registrar(
            id=uuid4(),
            empresa_id=empresa_id,
            nombre=nombre,
            origen=OrigenDato.PLANILLA,
            momento=ahora,
            cuit=cuit,
            condicion_iva=condicion,
            contacto_whatsapp=whatsapp,
            contacto_email=email,
        )
        cliente.presente_en_planilla = True
        await self._clientes.agregar(cliente)
        return ResultadoDeIngesta(creado=True)


class IngerirServicioDesdePlanilla:
    """Create one `Servicio` from a spreadsheet row (HU-E3-03).

    **It always creates; it never matches an existing service.** That is not an omission:
    `PortRepositorioServicio` deliberately has no `buscar_por_nombre`, and its docstring
    says why — services have no uniqueness rule, because two branches may both sell a
    «Corte». Adding a lookup here would quietly overturn an epic 3 decision from inside the
    context that consumes it.

    The consequence, stated so nobody discovers it: **running a full initial load twice
    duplicates every service.** Nothing in HU-E3-03 or HU-E3-06 asks for that to be
    prevented — a reprocessing only revisits the rows that failed (RN-02), and the
    incremental sync of HU-E3-04 only reads what changed. It becomes a real problem the day
    somebody re-runs a completed initial load, and the answer then is a decision about
    service identity, taken with `master_data`, not a lookup smuggled in here.
    """

    def __init__(self, servicios: PortRepositorioServicio) -> None:
        self._servicios = servicios

    async def ejecutar(
        self, *, empresa_id: EmpresaId, fila: FilaDeCatalogo, ahora: datetime
    ) -> ResultadoDeIngesta:
        nombre = (fila.nombre or "").strip()
        if not nombre:
            raise ErrorDeDominio("La fila no tiene nombre")

        servicio = Servicio.registrar(
            id=uuid4(),
            empresa_id=empresa_id,
            nombre=nombre,
            precio=_precio(fila.precio),
            alicuota_iva=_alicuota(fila.alicuota_iva),
            origen=OrigenDato.PLANILLA,
            momento=ahora,
        )
        servicio.presente_en_planilla = True
        await self._servicios.agregar(servicio)
        return ResultadoDeIngesta(creado=True)


def _condicion_iva(crudo: str | None) -> CondicionIVA | None:
    """A spreadsheet writes «Monotributo», «MONOTRIBUTO» and «monotributo ». All three
    are the same thing, and none of them is a reason to fail a row: the field is optional
    and an unrecognised value is better left empty than guessed."""
    if not crudo or not crudo.strip():
        return None
    try:
        return CondicionIVA(crudo.strip().upper().replace(" ", "_"))
    except ValueError:
        return None


def _precio(crudo: str | None) -> Decimal:
    """`Decimal`, never `float` (`CLAUDE.md` §3.5), and Argentine notation.

    A spreadsheet in es-AR writes `1.234,50`: dot for thousands, comma for decimals.
    Reading that with the C locale gives `1.23450` -- a price wrong by three orders of
    magnitude, silently, on every service in the catalogue.
    """
    if not crudo or not crudo.strip():
        raise ErrorDeDominio("La fila no tiene precio")
    limpio = crudo.strip().replace("$", "").replace(" ", "")
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpio)
    except InvalidOperation as exc:
        raise ErrorDeDominio(f"El precio '{crudo}' no es un numero") from exc


def _alicuota(crudo: str | None) -> AlicuotaIVA:
    """The three rates of HU-E4-02 RN-02, written the way a person writes them.

    `21`, `21%`, `0.21` and `21,00` all mean the general rate. Defaulting to it when the
    column is missing is deliberate: it is the rate of most sales in Argentina, and the
    alternative -- failing the row -- would reject a whole catalogue over a column the
    company never had.
    """
    if not crudo or not crudo.strip():
        return AlicuotaIVA.GENERAL
    limpio = crudo.strip().replace("%", "").replace(" ", "").replace(",", ".")
    try:
        valor = Decimal(limpio)
    except InvalidOperation as exc:
        raise ErrorDeDominio(f"La alicuota '{crudo}' no es un numero") from exc

    # Written as a percentage (21) or as a rate (0.21). Above 1 it can only be a
    # percentage: there is no 150% VAT.
    if valor > 1:
        valor = valor / Decimal("100")

    for alicuota in AlicuotaIVA:
        if Decimal(alicuota.value) == valor:
            return alicuota
    raise ErrorDeDominio(f"La alicuota '{crudo}' no es 0%, 10,5% ni 21%")


@dataclass(frozen=True, slots=True)
class RegistroParaPlanilla:
    """One catalogue record on its way back into the company's spreadsheet (HU-E3-07).

    Plain text, and no domain type: `spreadsheet_sync` may not import this context's
    `domain/` (rule R3), so what crosses the edge is this and the columns it names.
    """

    nombre: str
    cuit: str
    contacto_whatsapp: str
    contacto_email: str
    origen: str


class ListarClientesParaEscrituraDeVuelta:
    """The records the write-back is allowed to push (HU-E3-07 RN-03).

    **`PLANILLA` is excluded here, and that is guard 3 of the anti-loop mechanism.** A
    record that came from the spreadsheet is not written back into it; ADR-007 exists
    because a system that did would ingest its own output on the next sweep, forever.

    The filter lives in `master_data` rather than in the caller because `origen` is this
    context's concept: `spreadsheet_sync` asks «what should I write back», and the answer
    is a decision about the catalogue, not about spreadsheets.
    """

    #: Ours to write back. `PLANILLA` is deliberately absent -- see the docstring.
    ORIGENES = (OrigenDato.PANEL, OrigenDato.AGENTE)

    #: One write-back's worth. Google rejects very large bodies, and a sweep that pushed a
    #: whole catalogue in one call would fail as a unit instead of making progress.
    LIMITE = 500

    def __init__(self, clientes: PortRepositorioCliente) -> None:
        self._clientes = clientes

    async def ejecutar(
        self, *, empresa_id: EmpresaId, desde: datetime | None = None
    ) -> tuple[RegistroParaPlanilla, ...]:
        registros: list[RegistroParaPlanilla] = []
        for origen in self.ORIGENES:
            encontrados, _ = await self._clientes.listar(
                empresa_id=empresa_id,
                filtros=FiltrosDeCliente(origen=origen),
                pagina=Pagina(limite=self.LIMITE, desplazamiento=0),
            )
            for cliente in encontrados:
                # `desde` bounds the work, not the correctness: rewriting a record into
                # our own sheet overwrites the same row. That is why this filter may be
                # approximate while the `origen` one may not.
                if desde is not None and cliente.actualizado_en <= desde:
                    continue
                registros.append(
                    RegistroParaPlanilla(
                        nombre=cliente.nombre,
                        cuit=str(cliente.cuit) if cliente.cuit else "",
                        contacto_whatsapp=(
                            str(cliente.contacto_whatsapp) if cliente.contacto_whatsapp else ""
                        ),
                        contacto_email=(
                            str(cliente.contacto_email) if cliente.contacto_email else ""
                        ),
                        origen=cliente.origen.value,
                    )
                )
        return tuple(registros)
