"""`VinculoDePlanilla` — the aggregate behind HU-E2-04.

One invariant carries this file, and it is the reason the aggregate exists rather than a
row and a form: **only Google Sheets can be linked for writing.** Excel Online is
read-only through the integration HU-E3-07 describes, and an uploaded file is a snapshot
in R2 with nowhere to write back to. Enforcing that in the form would put the rule on the
wrong side of the door — HU-E3-07 RN-01 reads `direccion` before writing anything, and by
then the only thing standing between a wrong value and a write is this class.

The second one is quieter: **a link whose structure changed is paused, not broken**
(HU-E2-04 RN-04, HU-E3-04 RN-03). Pausing is a state of the link and not a deletion,
because the mapping is still valid for every row that came before and the company's
answer is usually to fix the header, not to start over.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    DireccionSync,
    ProveedorPlanilla,
    ReferenciaDeArchivo,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


@dataclass(slots=True, kw_only=True)
class VinculoDePlanilla:
    """One spreadsheet the company has connected, however it got here."""

    id: UUID
    empresa_id: EmpresaId
    proveedor: ProveedorPlanilla
    direccion: DireccionSync
    #: The sheet inside the workbook that belongs to the company. Never written to.
    hoja_empresa: str
    #: The system's own protected sheet, where write-back lands (HU-E3-07 RN-02). None
    #: until the write-back unit creates it, and forever None for read-only providers.
    hoja_cheatsheet: str | None = None
    #: Identifies the document for the provider. Google's file id, Microsoft's item id,
    #: or -- for `ARCHIVO` -- nothing, because the bytes are the document.
    identificador_externo: str | None = None
    #: Where the credential lives (`integrations`, ADR-0003). None for `ARCHIVO`.
    configuracion_integracion_id: UUID | None = None
    archivo: ReferenciaDeArchivo | None = None
    mapeo_vigente_id: UUID | None = None
    ultima_lectura: datetime | None = None
    ultima_escritura: datetime | None = None
    #: RN-04: a structural change stops the automatic sync until somebody reviews the
    #: mapping. Not an error state -- the link and its history stay entirely valid.
    pausado: bool = False
    motivo_de_pausa: str | None = None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.hoja_empresa.strip():
            raise EntradaInvalida("Hay que indicar la hoja de la planilla a leer")
        if (
            self.direccion is DireccionSync.LECTURA_Y_ESCRITURA
            and not self.proveedor.admite_escritura
        ):
            raise InvarianteViolada(
                f"{self.proveedor.value} no admite escritura de vuelta: "
                "solo Google Sheets puede vincularse para lectura y escritura"
            )
        if self.proveedor is ProveedorPlanilla.ARCHIVO and self.archivo is None:
            raise InvarianteViolada("Un vinculo de tipo ARCHIVO necesita el archivo cargado")
        if self.proveedor is not ProveedorPlanilla.ARCHIVO and self.identificador_externo is None:
            raise InvarianteViolada(
                f"Un vinculo de {self.proveedor.value} necesita el identificador del documento"
            )
        for momento, nombre in ((self.created_at, "created_at"), (self.updated_at, "updated_at")):
            if momento.tzinfo is None:
                raise EntradaInvalida(f"{nombre} debe tener zona horaria (UTC)")

    @property
    def escribe_de_vuelta(self) -> bool:
        """HU-E3-07 RN-01, asked as one question instead of two conditions at each site."""
        return (
            self.direccion is DireccionSync.LECTURA_Y_ESCRITURA and self.proveedor.admite_escritura
        )

    @property
    def admite_sincronizacion_incremental(self) -> bool:
        """HU-E3-04. A snapshot has nothing new to offer, and a paused link is not asked."""
        return self.proveedor.es_fuente_viva and not self.pausado

    def pausar(self, *, motivo: str, ahora: datetime) -> None:
        """RN-04: the structure changed, so the automatic sync stops until it is reviewed.

        Idempotent: pausing an already paused link refreshes the reason and nothing else.
        A sweep that finds the same changed header on two consecutive runs must not be a
        source of errors.
        """
        limpio = motivo.strip()
        if not limpio:
            raise EntradaInvalida("Una pausa tiene que decir por que")
        self.pausado = True
        self.motivo_de_pausa = limpio
        self.updated_at = ahora

    def reanudar(self, *, ahora: datetime) -> None:
        """The mapping was reviewed and confirmed, so the link goes back to work."""
        if self.mapeo_vigente_id is None:
            raise InvarianteViolada(
                "No se puede reanudar la sincronizacion sin un mapeo confirmado"
            )
        self.pausado = False
        self.motivo_de_pausa = None
        self.updated_at = ahora

    def asignar_mapeo(self, mapeo_id: UUID, *, ahora: datetime) -> None:
        self.mapeo_vigente_id = mapeo_id
        self.updated_at = ahora

    def registrar_lectura(self, *, ahora: datetime) -> None:
        self.ultima_lectura = ahora
        self.updated_at = ahora

    def registrar_escritura(self, *, ahora: datetime) -> None:
        """HU-E3-07 RN-04. Refuses on a link that must not be written to.

        The caller already checks `escribe_de_vuelta`; this refuses anyway, because a
        timestamp that says a read-only link was written to is worse than a crash — it is
        evidence of something that should be impossible, recorded as if it were routine.
        """
        if not self.escribe_de_vuelta:
            raise InvarianteViolada("Este vinculo es de solo lectura: no se le escribe de vuelta")
        self.ultima_escritura = ahora
        self.updated_at = ahora
