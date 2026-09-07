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
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import Mapeo
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla


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


@dataclass(frozen=True, slots=True)
class ArchivoGuardado:
    """The result of putting bytes in the object store."""

    clave: str
    tamano_bytes: int


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


class PortAlmacenamientoDeArchivos(Protocol):
    """Cloudflare R2. Bytes in, key out.

    Deliberately narrow: no listing, no signed URLs, no metadata. Everything this system
    needs to know about a stored workbook is already in `vinculo_de_planilla`, and an
    object store that can be asked to enumerate a bucket is one call away from being asked
    to enumerate somebody else's company.
    """

    async def guardar(
        self, *, clave: str, contenido: bytes, tipo_de_contenido: str
    ) -> ArchivoGuardado: ...

    async def leer(self, clave: str) -> bytes: ...

    async def eliminar(self, clave: str) -> None: ...


class PortProveedorDePlanilla(Protocol):
    """The ACL against Google Sheets and Excel Online."""

    def url_de_autorizacion(self, *, estado: str) -> str:
        """Where to send the user so they can pick a file and consent (RN-01)."""
        ...

    async def canjear_codigo(self, codigo: str) -> str:
        """Trade the authorisation code for a token. Raises on a declined consent."""
        ...

    async def describir_documento(self, *, token: str, identificador: str) -> DocumentoVinculado:
        """Read the document's structure. This is the call RN-01's read permission buys."""
        ...


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
