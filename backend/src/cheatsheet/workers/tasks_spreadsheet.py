"""Running a spreadsheet into the catalogue, off the request (HU-E3-03 RN-01).

One task, on the `spreadsheet_processing` queue — the queue ADR-003 created for exactly
this, so that «a burst of spreadsheet processing cannot delay» an invoice or a payment
webhook. Forty thousand rows take minutes; a request cannot wait for that, and RN-01 says
so: the screen shows «Procesando» and the result appears in `Cargas recientes` later.

**It is idempotent through `TareaAsincrona`** (unit 1, ADR-009), not through a flag: a
redelivered message finds the key claimed and does nothing, which matters more here than
almost anywhere else in the system — running an import twice would create forty thousand
customers twice.

**It retries, and it is allowed to end in the DLQ.** A file R2 cannot serve right now is
worth three attempts; a file that is corrupt is not, and after the ceiling HS-T6 retires
the task with its reason attached instead of retrying it forever.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.master_data.infrastructure.ensamblado import DatosMaestros
from cheatsheet.contexts.spreadsheet_sync.application.procesamientos import ProcesarPlanilla
from cheatsheet.contexts.spreadsheet_sync.application.sincronizacion import (
    EscribirDeVueltaEnPlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.catalogo import IngestaEnMasterData
from cheatsheet.contexts.spreadsheet_sync.infrastructure.ensamblado import (
    Planillas,
    almacenamiento,
    escritura_de_planilla,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.escritura import RegistrosDeMasterData
from cheatsheet.contexts.spreadsheet_sync.infrastructure.lector import LectorDePlanilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.repositories import (
    empresas_con_planilla_sincronizable,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers.base import PoliticaDeReintentos
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_PROCESAR = "spreadsheet_sync.procesar_planilla"

REINTENTOS = PoliticaDeReintentos()


async def procesar_planilla(
    recursos: Recursos,
    *,
    empresa_id: EmpresaId,
    vinculo_id: UUID,
    solo_filas: tuple[int, ...] | None = None,
    origen_id: UUID | None = None,
) -> int:
    """Read the linked file and run it. Returns how many rows were ingested."""
    filas_ok = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Planillas.armar(unidad)
        maestros = DatosMaestros.armar(unidad)

        vinculo = await piezas.vinculos.buscar_por_id(vinculo_id)
        if vinculo is None or vinculo.archivo is None:
            # Only uploaded files are processed here. A Google Sheets link is read by the
            # incremental sync of unit 5, which speaks to the provider rather than R2.
            logger.warning("planilla_sin_archivo_para_procesar", vinculo_id=str(vinculo_id))
            return 0

        contenido = await almacenamiento(recursos.settings).leer(vinculo.archivo.clave)

        resumen = await ProcesarPlanilla(
            procesamientos=piezas.procesamientos,
            vinculos=piezas.vinculos,
            mapeos=piezas.mapeos,
            lector=LectorDePlanilla(),
            catalogo=IngestaEnMasterData(clientes=maestros.clientes, servicios=maestros.servicios),
            publicador=unidad.publicador,
        ).ejecutar(
            empresa_id=empresa_id,
            vinculo_id=vinculo_id,
            contenido=contenido,
            nombre_de_archivo=vinculo.archivo.nombre_original,
            ahora=unidad.reloj.ahora(),
            solo_filas=solo_filas,
            origen_id=origen_id,
        )
        filas_ok = resumen.procesamiento.filas_ok
        logger.info(
            "planilla_procesada",
            empresa_id=str(empresa_id),
            procesamiento_id=str(resumen.procesamiento.id),
            estado=resumen.procesamiento.estado.value,
            filas_ok=filas_ok,
            filas_error=resumen.procesamiento.filas_error,
        )

    return filas_ok


def encolar_procesamiento(
    settings: Settings,
    *,
    empresa_id: EmpresaId,
    vinculo_id: UUID,
    solo_filas: tuple[int, ...] | None = None,
    origen_id: UUID | None = None,
) -> bool:
    """Put one processing on the queue. Returns whether it was accepted.

    A broker that is down is reported to the caller rather than swallowed: unlike the
    sweeps, this is somebody pressing a button and waiting for the screen to say
    «Procesando». Telling them nothing happened is better than a row that never moves.
    """
    try:
        crear_celery(settings).send_task(
            NOMBRE_PROCESAR,
            kwargs={
                "empresa_id": str(empresa_id),
                "vinculo_id": str(vinculo_id),
                "solo_filas": list(solo_filas) if solo_filas else None,
                "origen_id": str(origen_id) if origen_id else None,
            },
            queue=Cola.SPREADSHEET_PROCESSING.value,
        )
    except KombuError:
        logger.exception("no_se_pudo_encolar_el_procesamiento", vinculo_id=str(vinculo_id))
        return False
    return True


def procesar_planilla_sync(
    settings: Settings,
    *,
    empresa_id: str,
    vinculo_id: str,
    solo_filas: list[int] | None = None,
    origen_id: str | None = None,
) -> Any:
    """Celery's bridge into the async world. One loop and one set of resources per run."""
    identificadores = {
        "empresa_id": EmpresaId(UUID(empresa_id)),
        "vinculo_id": UUID(vinculo_id),
        "solo_filas": tuple(solo_filas) if solo_filas else None,
        "origen_id": UUID(origen_id) if origen_id else None,
    }
    return ejecutar_tarea(
        settings,
        lambda recursos: procesar_planilla(recursos, **identificadores),  # type: ignore[arg-type]
    )


def registrar(app: Celery, settings: Settings) -> None:
    """Attach the task to a Celery application."""

    @app.task(  # type: ignore[misc]
        name=NOMBRE_PROCESAR,
        queue=Cola.SPREADSHEET_PROCESSING.value,
        # `OSError` covers what is worth retrying here: R2 unreachable, the database
        # refusing a connection. A corrupt file raises a domain error, is recorded as a
        # failed processing, and is not retried -- it will be just as corrupt in a minute.
        autoretry_for=(OSError,),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _procesar(**kwargs: Any) -> Any:
        return procesar_planilla_sync(settings, **kwargs)

    @app.task(name=NOMBRE_BARRIDO_SYNC, queue=Cola.INCREMENTAL_SYNC.value)  # type: ignore[misc]
    def _barrido_sync() -> Any:
        return sincronizar_pendientes_sync(settings)

    @app.task(  # type: ignore[misc]
        name=NOMBRE_SYNC_EMPRESA,
        queue=Cola.INCREMENTAL_SYNC.value,
        autoretry_for=(OSError,),
        retry_backoff=REINTENTOS.espera_base,
        retry_backoff_max=REINTENTOS.espera_maxima,
        retry_jitter=True,
        max_retries=REINTENTOS.max_intentos,
    )
    def _sync_empresa(**kwargs: str) -> Any:
        return sincronizar_empresa_sync(settings, **kwargs)


NOMBRE_BARRIDO_SYNC = "spreadsheet_sync.sincronizar_pendientes"
NOMBRE_SYNC_EMPRESA = "spreadsheet_sync.sincronizar_empresa"


async def sincronizar_pendientes(recursos: Recursos) -> int:
    """Fan out one message per company with a live, unpaused link (HU-E3-04).

    Same shape as the integrations sweep, and for the same reason: a cross-company read
    must not become a cross-company transaction. Beat runs with no company set, so the
    discovery goes through a `SECURITY DEFINER` function that returns ids and nothing else.
    """
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_planilla_sincronizable(sesion)

    for empresa_id in empresas:
        _encolar_sync(recursos.settings, empresa_id)
    logger.info("sincronizacion_incremental_despachada", empresas=len(empresas))
    return len(empresas)


async def sincronizar_empresa(recursos: Recursos, empresa_id: EmpresaId) -> int:
    """Write back what the panel and the agent produced, for one company (HU-E3-07).

    **Reading the live sheet is not here yet** — see the unit record. What this does is
    the write-back half, which is the one with the loop risk and the one whose three
    guards are worth having in production before anything reads on a schedule.
    """
    escritas = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Planillas.armar(unidad)
        maestros = DatosMaestros.armar(unidad)

        for vinculo in await piezas.vinculos.listar():
            if not vinculo.escribe_de_vuelta:
                continue
            resultado = await EscribirDeVueltaEnPlanilla(
                vinculos=piezas.vinculos,
                registros=RegistrosDeMasterData(clientes=maestros.clientes, empresa_id=empresa_id),
                escritura=escritura_de_planilla(recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(empresa_id=empresa_id, vinculo_id=vinculo.id, ahora=unidad.reloj.ahora())
            escritas += resultado.filas_escritas

    logger.info("sincronizacion_empresa", empresa_id=str(empresa_id), filas=escritas)
    return escritas


def _encolar_sync(settings: Settings, empresa_id: EmpresaId) -> None:
    """A broker hiccup costs this company one cycle, not the whole fan-out."""
    try:
        crear_celery(settings).send_task(
            NOMBRE_SYNC_EMPRESA,
            kwargs={"empresa_id": str(empresa_id)},
            queue=Cola.INCREMENTAL_SYNC.value,
        )
    except KombuError:
        logger.exception("no_se_pudo_encolar_la_sincronizacion", empresa_id=str(empresa_id))


def sincronizar_pendientes_sync(settings: Settings) -> Any:
    return ejecutar_tarea(settings, sincronizar_pendientes)


def sincronizar_empresa_sync(settings: Settings, *, empresa_id: str) -> Any:
    identificador = EmpresaId(UUID(empresa_id))
    return ejecutar_tarea(settings, lambda recursos: sincronizar_empresa(recursos, identificador))
