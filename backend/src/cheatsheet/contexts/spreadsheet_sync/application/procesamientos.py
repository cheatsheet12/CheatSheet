"""The use cases of HU-E3-03, HU-E3-05 and HU-E3-06 — running a spreadsheet into the
catalogue, reading what happened, and retrying what failed.

**The whole unit turns on one loop**, and on the fact that a failure inside it never
escapes it. HU-E3-03 RN-02: «las filas con datos inválidos se marcan como error pero no
abortan el procesamiento del resto». Forty thousand rows and one malformed CUIT produce
39 999 customers and one line. That is why `_procesar_fila` catches `ErrorDeDominio` and
turns it into an `ErrorDeFila` instead of letting it out.

**The catalogue is written through `master_data`'s own application service**, never
through its repositories. Rule R3, and the Context Map edge `spreadsheet_sync →
master_data`. This context asks in its own words; that one decides what a `Cliente` is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    VinculoInexistente,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    FilaParaIngerir,
    PortIngestaDeCatalogo,
    PortLectorDePlanilla,
    PortRepositorioMapeo,
    PortRepositorioProcesamiento,
    PortRepositorioVinculo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import Mapeo
from cheatsheet.contexts.spreadsheet_sync.domain.procesamiento import (
    ErrorDeFila,
    EstadoProcesamiento,
    ProcesamientoDePlanilla,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, ErrorDeDominio, InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario


@dataclass(frozen=True, slots=True)
class ResumenDeProcesamiento:
    """What PAN-ING-01 and PAN-ING-03 show (HU-E3-05 RN-01)."""

    procesamiento: ProcesamientoDePlanilla

    @property
    def hubo_errores(self) -> bool:
        return self.procesamiento.filas_error > 0


class ProcesarPlanilla:
    """HU-E3-03 — read the file, map each row, write the catalogue, count everything.

    Runs inside a Celery task on the `spreadsheet_processing` queue, so nothing here
    blocks a request (RN-01). What it guarantees is the counting: `filas_totales`,
    `filas_ok` and `filas_error` are maintained by the aggregate on every row, so the
    three can never disagree with each other or with the list of errors.
    """

    def __init__(
        self,
        *,
        procesamientos: PortRepositorioProcesamiento,
        vinculos: PortRepositorioVinculo,
        mapeos: PortRepositorioMapeo,
        lector: PortLectorDePlanilla,
        catalogo: PortIngestaDeCatalogo,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._procesamientos = procesamientos
        self._vinculos = vinculos
        self._mapeos = mapeos
        self._lector = lector
        self._catalogo = catalogo
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        vinculo_id: UUID,
        contenido: bytes,
        nombre_de_archivo: str,
        ahora: datetime,
        duracion_ms: int = 0,
        solo_filas: tuple[int, ...] | None = None,
        origen_id: UUID | None = None,
    ) -> ResumenDeProcesamiento:
        vinculo = await self._vinculos.buscar_por_id(vinculo_id)
        if vinculo is None:
            raise VinculoInexistente("La planilla vinculada no existe")
        if vinculo.mapeo_vigente_id is None:
            raise InvarianteViolada("No se puede procesar una planilla sin un mapeo confirmado")

        mapeo = await self._mapeos.buscar_por_id(vinculo.mapeo_vigente_id)
        if mapeo is None or not mapeo.esta_confirmado:
            # RN-01's precondition. Processing on a draft mapping would write forty
            # thousand rows through assignments nobody agreed to.
            raise InvarianteViolada("El mapeo de esta planilla todavia no fue confirmado")

        procesamiento = ProcesamientoDePlanilla(
            id=uuid4(),
            empresa_id=empresa_id,
            vinculo_id=vinculo_id,
            mapeo_id=mapeo.id,
            referencia_archivo=vinculo.archivo.clave if vinculo.archivo else None,
            origen_id=origen_id,
            created_at=ahora,
        )
        await self._procesamientos.agregar(procesamiento)

        try:
            planilla = self._lector.leer(contenido=contenido, nombre=nombre_de_archivo)
        except ErrorDeDominio as exc:
            # The file itself is unreadable: nothing was ingested and there is nothing to
            # correct row by row, which is a different ending from «con errores».
            procesamiento.abortar(motivo=str(exc), duracion_ms=duracion_ms, ahora=ahora)
            await self._procesamientos.actualizar(procesamiento)
            await self._auditar(procesamiento, ahora=ahora)
            return ResumenDeProcesamiento(procesamiento)

        objetivo = planilla.solo(solo_filas) if solo_filas is not None else planilla

        for fila in objetivo.filas:
            await self._procesar_fila(
                procesamiento, fila=fila, mapeo=mapeo, empresa_id=empresa_id, ahora=ahora
            )

        procesamiento.cerrar(duracion_ms=duracion_ms, ahora=ahora)
        await self._procesamientos.actualizar(procesamiento)

        vinculo.registrar_lectura(ahora=ahora)
        await self._vinculos.actualizar(vinculo)

        await self._auditar(procesamiento, ahora=ahora)
        return ResumenDeProcesamiento(procesamiento)

    async def _procesar_fila(
        self,
        procesamiento: ProcesamientoDePlanilla,
        *,
        fila: object,
        mapeo: Mapeo,
        empresa_id: EmpresaId,
        ahora: datetime,
    ) -> None:
        """One row. **Nothing raised in here reaches the caller** — that is RN-02.

        `ErrorDeDominio` covers every way a row can be wrong: a malformed CUIT, a price
        that is not a number, a missing name. Anything else is a bug of ours and is left
        to propagate, because a row silently swallowed by a `TypeError` would be counted
        as an error the user cannot fix.
        """
        numero = getattr(fila, "numero", 0)
        celdas: dict[str, str] = getattr(fila, "celdas", {})
        try:
            valores = _aplicar_mapeo(mapeo, celdas)
            if not valores:
                raise EntradaInvalida("La fila esta vacia despues de aplicar el mapeo")
            await self._catalogo.ingerir(
                empresa_id=empresa_id, fila=FilaParaIngerir(valores=valores), ahora=ahora
            )
        except ErrorDeDominio as exc:
            procesamiento.registrar_error(
                error=ErrorDeFila(id=uuid4(), numero_fila=numero, motivo=str(exc))
            )
        else:
            procesamiento.contar_fila_ok()

    async def _auditar(self, procesamiento: ProcesamientoDePlanilla, *, ahora: datetime) -> None:
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=procesamiento.empresa_id,
                ocurrido_en=ahora,
                # The scheduler ran this, not a person: HS-T5 models that as a null
                # initiator, even when somebody pressed a button minutes earlier.
                usuario_id=None,
                modulo=Modulo.SPREADSHEET_SYNC,
                accion="procesar_planilla",
                entidad_afectada=f"ProcesamientoDePlanilla:{procesamiento.id}",
                resultado=(
                    Resultado.ERROR
                    if procesamiento.estado is EstadoProcesamiento.FALLIDO
                    else Resultado.COMPLETADO
                ),
            )
        )


def _aplicar_mapeo(mapeo: Mapeo, celdas: dict[str, str]) -> dict[str, str]:
    """Turn one row's cells into the ingestion's vocabulary, using the confirmed mapping.

    Unassigned columns are dropped rather than passed through: `Sin asignar` means the
    user decided this column goes nowhere, and forwarding it under its spreadsheet name
    would make the ingestion guess again.
    """
    valores: dict[str, str] = {}
    for entrada in mapeo.entradas:
        if entrada.atributo_destino is None:
            continue
        valor = celdas.get(entrada.columna_origen, "").strip()
        if valor:
            valores[entrada.atributo_destino] = valor
    return valores


class ConsultarProcesamiento:
    """HU-E3-05 — the detail of one run. Every role reads it (RN-04)."""

    def __init__(self, procesamientos: PortRepositorioProcesamiento) -> None:
        self._procesamientos = procesamientos

    async def ejecutar(self, *, procesamiento_id: UUID) -> ResumenDeProcesamiento:
        procesamiento = await self._procesamientos.buscar_por_id(procesamiento_id)
        if procesamiento is None:
            raise EntradaInvalida("El procesamiento no existe")
        return ResumenDeProcesamiento(procesamiento)


class ListarProcesamientos:
    """`Cargas recientes` of PAN-ING-01, and the history of PAN-ING-03."""

    def __init__(self, procesamientos: PortRepositorioProcesamiento) -> None:
        self._procesamientos = procesamientos

    async def ejecutar(self, *, vinculo_id: UUID | None = None) -> list[ProcesamientoDePlanilla]:
        return await self._procesamientos.listar(vinculo_id=vinculo_id)


class PrepararReproceso:
    """HU-E3-06 — decide what a retry should read, and refuse when there is nothing to.

    It does not run the processing: it produces the row numbers the task will read, so the
    «no duplica las filas ya procesadas» of RN-02 is a decision taken once, here, instead
    of a condition inside the loop.
    """

    def __init__(self, procesamientos: PortRepositorioProcesamiento) -> None:
        self._procesamientos = procesamientos

    async def ejecutar(
        self, *, procesamiento_id: UUID, rol: RolUsuario
    ) -> tuple[ProcesamientoDePlanilla, tuple[int, ...]]:
        # RN-04 of HU-E3-05: Solo Lectura sees the result «sin la opcion de reprocesar».
        if rol is RolUsuario.SOLO_LECTURA:
            raise EntradaInvalida("Un usuario de Solo Lectura no puede reprocesar")

        original = await self._procesamientos.buscar_por_id(procesamiento_id)
        if original is None:
            raise EntradaInvalida("El procesamiento no existe")
        if not original.termino:
            raise InvarianteViolada("Ese procesamiento todavia esta en curso")

        filas = original.filas_a_reprocesar
        if not filas:
            # Not an error state worth a special screen: there is simply nothing to redo,
            # and saying so is better than starting a run that ingests nothing.
            raise EntradaInvalida("Ese procesamiento no dejo filas con error para reprocesar")
        return original, filas
