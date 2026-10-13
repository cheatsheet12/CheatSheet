"""HU-E3-04 and HU-E3-07 — keeping a live spreadsheet and the panel in step.

Two directions, and the second one is the dangerous one.

**Reading (HU-E3-04).** The sweep re-reads a linked sheet and processes what changed since
`ultima_lectura`. If the header structure changed, it **pauses** the link and asks for the
mapping to be reviewed (RN-03) instead of ingesting rows through assignments that no longer
mean what they meant.

**Writing back (HU-E3-07).** This is where a system can eat its own tail. Three guards, and
each one alone is insufficient:

1. **Only links whose `direccion` is `LECTURA_Y_ESCRITURA`** (RN-01), which the aggregate
   already refuses to set on anything but Google Sheets.
2. **Only into the system's own protected sheet**, never the company's (RN-02, ADR-007).
   That is what makes the loop impossible rather than unlikely: what we write lands
   somewhere we never read.
3. **Only records whose `origen` is PANEL or AGENTE** (RN-03). A record that came from the
   spreadsheet is not written back into it.

Guard 2 is the structural one and guards 1 and 3 are the intent. Keeping all three means a
bug in any single one does not produce an infinite sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.spreadsheet_sync.application.errors import VinculoInexistente
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import huella_de
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    FilaParaEscribir,
    PortEscrituraDePlanilla,
    PortRegistrosParaEscribir,
    PortRepositorioMapeo,
    PortRepositorioVinculo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

#: The name of the sheet CheatSheet writes into (RN-02). One per link, created on the
#: first write-back. Prefixed so it is recognisable in a workbook a person owns, and so a
#: company that already has a sheet called «CheatSheet» is not overwritten.
HOJA_DE_CHEATSHEET = "CheatSheet (no editar)"

#: What a structural change is told to the user as. RN-03's exact sentence.
MENSAJE_ESTRUCTURA_CAMBIO = (
    "La estructura de la planilla cambió. Revise el mapeo para reanudar la sincronización."
)


@dataclass(frozen=True, slots=True)
class ResultadoDeSincronizacion:
    """What one sweep over one link did."""

    vinculo_id: UUID
    #: True when the sweep stopped because the headers moved (RN-03).
    pausado_por_estructura: bool = False
    filas_escritas: int = 0

    @property
    def hubo_escritura(self) -> bool:
        return self.filas_escritas > 0


class DetectarCambioDeEstructura:
    """RN-03 — compare the sheet's current headers against the confirmed mapping.

    Pausing rather than failing, and pausing rather than re-mapping automatically. The
    company renamed a column; what happens next is a decision they have to see, because
    the alternative is forty thousand rows landing in the wrong fields on a schedule
    nobody is watching.
    """

    def __init__(
        self,
        *,
        vinculos: PortRepositorioVinculo,
        mapeos: PortRepositorioMapeo,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._vinculos = vinculos
        self._mapeos = mapeos
        self._publicador = publicador

    async def ejecutar(
        self, *, vinculo_id: UUID, columnas: tuple[str, ...], ahora: datetime
    ) -> bool:
        """Returns whether the link was paused."""
        vinculo = await self._vinculos.buscar_por_id(vinculo_id)
        if vinculo is None:
            raise VinculoInexistente("La planilla vinculada no existe")
        if vinculo.mapeo_vigente_id is None:
            return False

        mapeo = await self._mapeos.buscar_por_id(vinculo.mapeo_vigente_id)
        if mapeo is None:
            return False
        if mapeo.huella_encabezado == huella_de(columnas):
            return False

        vinculo.pausar(motivo=MENSAJE_ESTRUCTURA_CAMBIO, ahora=ahora)
        await self._vinculos.actualizar(vinculo)

        # The mapping goes back to draft with its entries intact: most of a changed
        # spreadsheet is the same spreadsheet, and making somebody redo forty assignments
        # over one renamed column is how a pause becomes an abandonment.
        mapeo.nueva_version(ahora=ahora)
        await self._mapeos.actualizar(mapeo)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=vinculo.empresa_id,
                ocurrido_en=ahora,
                usuario_id=None,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="pausar_sincronizacion",
                entidad_afectada=f"VinculoDePlanilla:{vinculo.id}",
                # RN-02 of HU-E3-04: the failure is logged and the Administrator notified.
                # This is the log half; the notification rides the same event.
                resultado=Resultado.ERROR,
            )
        )
        return True


class EscribirDeVueltaEnPlanilla:
    """HU-E3-07 — push what the panel and the agent created into the protected sheet.

    The three guards of the module docstring are applied here, in order, and the first two
    are checked **before** anything is read: asking `master_data` for records to write and
    then discovering the link is read-only would be a query nobody needed.
    """

    def __init__(
        self,
        *,
        vinculos: PortRepositorioVinculo,
        registros: PortRegistrosParaEscribir,
        escritura: PortEscrituraDePlanilla,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._vinculos = vinculos
        self._registros = registros
        self._escritura = escritura
        self._publicador = publicador

    async def ejecutar(
        self, *, empresa_id: EmpresaId, vinculo_id: UUID, ahora: datetime
    ) -> ResultadoDeSincronizacion:
        vinculo = await self._vinculos.buscar_por_id(vinculo_id)
        if vinculo is None:
            raise VinculoInexistente("La planilla vinculada no existe")

        # Guards 1 and 2, as one question the aggregate already knows how to answer.
        # `escribe_de_vuelta` is False for a read-only link, for Excel Online and for an
        # uploaded file -- the fourth acceptance criterion of HU-E3-07 is this line.
        if not vinculo.escribe_de_vuelta:
            return ResultadoDeSincronizacion(vinculo_id=vinculo_id)

        # Guard 3: only what the panel or the agent produced. A record whose `origen` is
        # PLANILLA came from this sheet, and writing it back is the loop.
        pendientes = await self._registros.pendientes_de_escritura(desde=vinculo.ultima_escritura)
        if not pendientes:
            return ResultadoDeSincronizacion(vinculo_id=vinculo_id)
        # The adapter rewrites its own sheet from A1. Send a complete snapshot: sending
        # only the changes would silently replace the oldest records with the newest.
        filas = (
            pendientes
            if vinculo.ultima_escritura is None
            else await self._registros.pendientes_de_escritura(desde=None)
        )

        # A link owns a unique sheet. Reusing a fixed title could overwrite a sheet the
        # company had already created with that name.
        hoja = vinculo.hoja_cheatsheet or f"{HOJA_DE_CHEATSHEET} {vinculo.id.hex[:8]}"
        await self._escritura.escribir(
            identificador=_exigir_identificador(vinculo), hoja=hoja, filas=filas
        )

        vinculo.hoja_cheatsheet = hoja
        vinculo.registrar_escritura(ahora=ahora)
        await self._vinculos.actualizar(vinculo)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=None,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="escribir_en_planilla",
                entidad_afectada=f"VinculoDePlanilla:{vinculo.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return ResultadoDeSincronizacion(vinculo_id=vinculo_id, filas_escritas=len(filas))


def _exigir_identificador(vinculo: VinculoDePlanilla) -> str:
    if vinculo.identificador_externo is None:  # pragma: no cover - the aggregate forbids it
        raise VinculoInexistente("El vinculo no tiene identificador de documento")
    return vinculo.identificador_externo


__all__ = [
    "HOJA_DE_CHEATSHEET",
    "MENSAJE_ESTRUCTURA_CAMBIO",
    "DetectarCambioDeEstructura",
    "EscribirDeVueltaEnPlanilla",
    "FilaParaEscribir",
    "ResultadoDeSincronizacion",
]
