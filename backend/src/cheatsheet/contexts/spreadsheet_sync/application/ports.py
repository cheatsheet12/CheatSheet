"""Ports of `spreadsheet_sync`.

Three, and the split follows what can fail independently: the database, the object store,
and somebody else's API.

`PortProveedorDePlanilla` is an Anti-Corruption Layer (ADR-008): the application sees
`HojaDePlanilla` and `DocumentoVinculado`, never a Google payload. Google and Microsoft
model the same idea with different words, and the day a third one appears the difference
has to stop here rather than reaching a use case.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

# The DTO comes from `platform/`, where the adapter that produces it lives: two copies of
# the same two fields would be two types mypy considers unrelated, which is exactly the
# seam a wrong mapping hides in. The *port* below stays here -- a port is the consumer's
# contract, and `billing` declares its own with the same shape.
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import Mapeo
from cheatsheet.contexts.spreadsheet_sync.domain.procesamiento import ProcesamientoDePlanilla
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.platform.almacenamiento import ArchivoGuardado
from cheatsheet.shared.empresa import EmpresaId


@dataclass(frozen=True, slots=True)
class HojaDePlanilla:
    """One sheet inside a workbook, as the application understands it."""

    nombre: str
    filas_estimadas: int


@dataclass(frozen=True, slots=True)
class DocumentoVinculado:
    """What the provider hands back once the user has chosen a document and consented."""

    identificador_externo: str
    nombre: str
    hojas: tuple[HojaDePlanilla, ...]

    def __post_init__(self) -> None:
        if not self.hojas:
            raise ValueError("Un documento vinculado tiene al menos una hoja")


@dataclass(frozen=True, slots=True)
class TokensDePlanilla:
    """Short-lived access and offline renewal from one OAuth exchange."""

    acceso: str
    renovacion: str


@dataclass(frozen=True, slots=True)
class Asignacion:
    """One column, one destination attribute, one confidence (HU-E3-01 RN-01).

    Lives here and not beside the adapter because it is what the *application* receives:
    rule R2 forbids `application/` importing `infrastructure/`, and it is right to -- a
    use case that named a type from an adapter would be a use case bound to that adapter.
    """

    columna: str
    #: `None` is a real answer: «I do not know what this column is». RN-03 has a state for
    #: it, and it beats a guess that writes a CUIT into the phone field.
    atributo: str | None
    score: Decimal


class PortAlmacenamientoDeArchivos(Protocol):
    """Cloudflare R2. Bytes in, key out.

    Deliberately narrow: no listing, no signed URLs, no metadata. Everything this system
    needs to know about a stored workbook is already in `vinculo_de_planilla`, and an
    object store that can be asked to enumerate a bucket is one call away from being asked
    to enumerate somebody else's company.

    **`billing` declares a port of its own with the same shape**, and that duplication is
    the correct kind: a port is the *consumer's* contract, not the adapter's, and the two
    contexts happen to want the same three operations. What is shared is the adapter, which
    lives in `platform/almacenamiento.py` because object storage is platform infrastructure
    and rule R3 forbids either context reaching into the other's.
    """

    async def guardar(
        self, *, clave: str, contenido: bytes, tipo_de_contenido: str
    ) -> ArchivoGuardado: ...

    async def leer(self, clave: str) -> bytes: ...

    async def eliminar(self, clave: str) -> None: ...


class PortRepositorioVinculo(Protocol):
    """Persistence of links. `eliminar` exists, unlike the audit and task ports.

    Unlinking a spreadsheet is a legitimate Administrator operation and it destroys
    nothing that ADR-007 protects: the `Cliente` and `Servicio` rows already ingested
    survive, keeping `presente_en_planilla` as it was.
    """

    async def agregar(self, vinculo: VinculoDePlanilla) -> None: ...

    async def actualizar(self, vinculo: VinculoDePlanilla) -> None: ...

    async def buscar_por_id(self, vinculo_id: UUID) -> VinculoDePlanilla | None: ...

    async def listar(self) -> list[VinculoDePlanilla]: ...

    async def eliminar(self, vinculo_id: UUID) -> None: ...


class PortProveedorDePlanilla(Protocol):
    """The ACL against Google Sheets and Excel Online."""

    def url_de_autorizacion(self, *, estado: str) -> str:
        """Where to send the user so they can pick a file and consent (RN-01)."""
        ...

    async def canjear_codigo(self, codigo: str) -> TokensDePlanilla:
        """Trade the code for access and renewal. Raises on a declined consent."""
        ...

    async def describir_documento(self, *, token: str, identificador: str) -> DocumentoVinculado:
        """Read the document's structure. This is the call RN-01's read permission buys."""
        ...


class PortCredencialesDePlanilla(Protocol):
    """Persist a validated per-company renewal credential in integrations."""

    async def guardar(self, *, empresa_id: EmpresaId, renovacion: str, ahora: datetime) -> UUID: ...

    async def obtener(
        self, *, empresa_id: EmpresaId, configuracion_id: UUID, ahora: datetime
    ) -> str: ...


class PortRepositorioMapeo(Protocol):
    """Persistence of mappings and their entries.

    No `eliminar`: a mapping is what says how every row already ingested was interpreted.
    Deleting one turns the history of a processing into a set of columns nobody can read
    back. Superseding it is `nueva_version`, which keeps both.
    """

    async def agregar(self, mapeo: Mapeo) -> None: ...

    async def actualizar(self, mapeo: Mapeo) -> None: ...

    async def buscar_por_id(self, mapeo_id: UUID) -> Mapeo | None: ...

    async def buscar_por_huella(self, huella: str) -> Mapeo | None:
        """The stored mapping for a header structure, if any (HU-E3-01 RN-02)."""
        ...


class PortModeloDeLenguaje(Protocol):
    """The LLM (ADR-0007). Declared in `docs/architecture.md`; this is its first consumer.

    **It receives column names and the destination vocabulary. Never rows** -- decision
    D12 of the units map, and `CLAUDE.md` section 3.6.

    It returns an empty tuple when it cannot answer, rather than raising: a model outage
    degrades to «every column Sin asignar» and the user maps by hand. An exception here
    would make somebody else's downtime into a failed ingestion.
    """

    async def proponer_mapeo(
        self, *, columnas: tuple[str, ...], atributos: tuple[str, ...]
    ) -> tuple[Asignacion, ...]: ...


@dataclass(frozen=True, slots=True)
class FilaParaIngerir:
    """One mapped row, in this context's words, on its way to `master_data`.

    A plain dict of attribute name to text. It is deliberately not `master_data`'s own
    `FilaDeCatalogo`: naming that type here would make `spreadsheet_sync/application`
    depend on another context's application layer, and rule R3 has the edge going through
    an adapter instead. The translation happens once, in that adapter.
    """

    valores: dict[str, str]


class PortIngestaDeCatalogo(Protocol):
    """The edge `spreadsheet_sync -> master_data` of the Context Map.

    Declared here, implemented by an adapter that calls `master_data`'s own application
    service. That indirection is the rule R3 boundary made visible: this context knows
    that rows go somewhere and get written, and nothing about what a `Cliente` is.
    """

    async def ingerir(
        self, *, empresa_id: EmpresaId, fila: FilaParaIngerir, ahora: datetime
    ) -> None:
        """Write one row. Raises `ErrorDeDominio` when the row is the problem.

        That exception type is the contract: the processing turns it into an `ErrorDeFila`
        with the row's original number and keeps going (HU-E3-03 RN-02). Anything else
        raised here is a bug and is allowed to stop the run.
        """
        ...


@dataclass(frozen=True, slots=True)
class FilaLeida:
    """One row, as text, with the number the spreadsheet gives it.

    Text and not typed values on purpose: a spreadsheet cell *is* text, and deciding that
    `"1.234,50"` is a price is `master_data`'s job, at the point where getting it wrong
    becomes an `ErrorDeFila` with a row number instead of a silent 1.23450.
    """

    numero: int
    celdas: dict[str, str]


@dataclass(frozen=True, slots=True)
class PlanillaLeida:
    """A workbook reduced to what the ingestion needs: headers and rows.

    Lives here and not beside the adapter for the reason rule R2 gives, and that the
    architecture guard already enforced once in this unit: a use case that named a type
    from `infrastructure/` would be a use case bound to one reader.
    """

    columnas: tuple[str, ...]
    filas: tuple[FilaLeida, ...]

    def solo(self, numeros: tuple[int, ...]) -> PlanillaLeida:
        """The subset a reprocessing needs (HU-E3-06 RN-02): the rows that failed."""
        buscados = set(numeros)
        return PlanillaLeida(
            columnas=self.columnas, filas=tuple(f for f in self.filas if f.numero in buscados)
        )


class PortLectorDePlanilla(Protocol):
    """Turns bytes into headers and rows. Validates nothing -- see the adapter."""

    def leer(self, *, contenido: bytes, nombre: str) -> PlanillaLeida: ...


class PortRepositorioProcesamiento(Protocol):
    """Persistence of processings and their row errors.

    No `eliminar`: a processing is the record of an import that already wrote into the
    catalogue, and HU-E3-05 exists so somebody can read it afterwards. Deleting one leaves
    rows in `master_data` whose provenance nothing explains.
    """

    async def agregar(self, procesamiento: ProcesamientoDePlanilla) -> None: ...

    async def actualizar(self, procesamiento: ProcesamientoDePlanilla) -> None: ...

    async def buscar_por_id(self, procesamiento_id: UUID) -> ProcesamientoDePlanilla | None: ...

    async def listar(self, *, vinculo_id: UUID | None = None) -> list[ProcesamientoDePlanilla]:
        """Newest first. Without a link, every processing of the company."""
        ...


@dataclass(frozen=True, slots=True)
class FilaParaEscribir:
    """One record on its way back into the protected sheet (HU-E3-07).

    Text again, and in the sheet's own order: what goes into a cell is a string, and the
    order is what makes the columns line up with the header this context wrote.
    """

    valores: tuple[str, ...]


class PortRegistrosParaEscribir(Protocol):
    """The other direction of the `spreadsheet_sync -> master_data` edge.

    Implemented by an adapter that asks `master_data` for what the panel and the agent
    created. **The `origen` filter lives in the adapter, not here**: this port's contract
    is «what has to be written back», and which records those are is the other context's
    definition -- the same reasoning `PortIngestaDeCatalogo` follows going the other way.
    """

    async def pendientes_de_escritura(
        self, *, desde: datetime | None
    ) -> tuple[FilaParaEscribir, ...]:
        """Records created or changed since `desde`, never those whose origin is the sheet.

        `None` means «everything so far», which is what the first write-back on a link
        asks for.
        """
        ...


class PortEscrituraDePlanilla(Protocol):
    """Writing into the provider's document (HU-E3-07 RN-02).

    Deliberately narrow: it can write one named sheet and nothing else. There is no
    `borrar`, no `reemplazar_hoja` and no way to name the company's own sheet from a call
    site -- the only sheet this context ever passes is the one it created. An adapter that
    could overwrite an arbitrary sheet is one wrong argument away from deleting somebody's
    customer list.
    """

    async def escribir(
        self, *, identificador: str, hoja: str, filas: tuple[FilaParaEscribir, ...]
    ) -> None: ...
