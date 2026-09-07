"""Authorising documents against ARCA, off the request (HU-E5-03 RN-04).

Two tasks and one queue of their own, and the split is not the fan-out shape the other
sweeps use — it is the shape decision **D17** forces:

- **`billing.autorizar_comprobante`** — one document, enqueued by the request that created
  it. Sends the envelope once.
- **`billing.reconciliar_comprobantes`** — the Beat entry. Finds documents stuck in
  `ENVIADO_A_ARCA` past the flight window and **asks ARCA what happened** rather than
  sending anything again.

**`autoretry_for` is deliberately absent from the first one, and that is the whole point.**
Every other outbound task in this system retries on `ProveedorNoDisponible`. This one must
not: `FECAESolicitar` is not idempotent, so a retry after a timeout is how one sale becomes
two legally authorised documents, and the second one also carries a CAE. The retry for this
task is the reconciliation sweep, which asks before it acts.

The sweep is per company, like every other, because a document belongs to a company and RLS
scopes it. It fans out from the list of companies with something in flight.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError

from cheatsheet.api.arca import armar_autorizacion
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.billing.application.emision import (
    AutorizarComprobante,
    ReconciliarComprobante,
)
from cheatsheet.contexts.billing.application.errors import ArcaNoDisponible
from cheatsheet.contexts.billing.infrastructure.ensamblado import Facturacion
from cheatsheet.contexts.billing.infrastructure.repositorio_comprobante import (
    empresas_con_comprobantes_en_vuelo,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_AUTORIZAR = "billing.autorizar_comprobante"
NOMBRE_RECONCILIAR = "billing.reconciliar_comprobantes"
NOMBRE_RECONCILIAR_EMPRESA = "billing.reconciliar_empresa"


class ColaDeEmision:
    """`PortColaDeEmision`, backed by Celery.

    A broker failure here **raises**, unlike the fan-out sweeps that swallow one. The
    difference is what is lost: there, one company waits until the next run; here, a
    document sits in `ENVIADO_A_ARCA` that nothing ever sends. Raising rolls the request
    back, and the user is told to try again -- with nothing written and no number consumed.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def encolar(self, *, empresa_id: EmpresaId, comprobante_id: UUID) -> None:
        crear_celery(self._settings).send_task(
            NOMBRE_AUTORIZAR,
            kwargs={"empresa_id": str(empresa_id), "comprobante_id": str(comprobante_id)},
            queue=Cola.INTEGRATIONS_SYNC.value,
        )


async def autorizar(recursos: Recursos, empresa_id: EmpresaId, comprobante_id: UUID) -> str:
    """Send one document to ARCA and record what came back. Returns the resulting state."""
    estado = ""
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Facturacion.armar(unidad)
        resuelto = await AutorizarComprobante(
            comprobantes=piezas.comprobantes,
            puntos=piezas.puntos,
            arca=armar_autorizacion(unidad, recursos.settings),
            publicador=unidad.publicador,
        ).ejecutar(empresa_id=empresa_id, comprobante_id=comprobante_id, ahora=unidad.reloj.ahora())
        estado = resuelto.estado.value

    logger.info("comprobante_resuelto", comprobante_id=str(comprobante_id), estado=estado)
    return estado


async def reconciliar_empresa(recursos: Recursos, empresa_id: EmpresaId) -> int:
    """Decision D17 for one company. Returns how many documents it settled."""
    resueltos = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Facturacion.armar(unidad)
        settled = await ReconciliarComprobante(
            comprobantes=piezas.comprobantes,
            puntos=piezas.puntos,
            arca=armar_autorizacion(unidad, recursos.settings),
            publicador=unidad.publicador,
        ).ejecutar(empresa_id=empresa_id, ahora=unidad.reloj.ahora())
        resueltos = len(settled)

    if resueltos:
        logger.info("comprobantes_reconciliados", empresa_id=str(empresa_id), resueltos=resueltos)
    return resueltos


async def reconciliar(recursos: Recursos) -> int:
    """Fan out one message per company with something in flight. Returns how many."""
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_comprobantes_en_vuelo(sesion)

    for empresa_id in empresas:
        _encolar_reconciliacion(recursos.settings, empresa_id)
    if empresas:
        logger.info("reconciliacion_despachada", empresas=len(empresas))
    return len(empresas)


def _encolar_reconciliacion(settings: Settings, empresa_id: EmpresaId) -> None:
    """A broker hiccup must not abort the fan-out.

    Unlike `ColaDeEmision`, this one swallows: losing one company's message costs a delay
    of one sweep interval, and letting the exception escape would cost every company that
    came after it in the loop.
    """
    try:
        crear_celery(settings).send_task(
            NOMBRE_RECONCILIAR_EMPRESA,
            kwargs={"empresa_id": str(empresa_id)},
            queue=Cola.INTEGRATIONS_SYNC.value,
        )
    except KombuError:
        logger.exception("no_se_pudo_encolar_reconciliacion", empresa_id=str(empresa_id))


def autorizar_sync(settings: Settings, *, empresa_id: str, comprobante_id: str) -> Any:
    identificador = EmpresaId(UUID(empresa_id))
    documento = UUID(comprobante_id)
    return ejecutar_tarea(settings, lambda recursos: autorizar(recursos, identificador, documento))


def reconciliar_sync(settings: Settings) -> Any:
    return ejecutar_tarea(settings, reconciliar)


def reconciliar_empresa_sync(settings: Settings, *, empresa_id: str) -> Any:
    identificador = EmpresaId(UUID(empresa_id))
    return ejecutar_tarea(settings, lambda recursos: reconciliar_empresa(recursos, identificador))


def registrar(app: Celery, settings: Settings) -> None:
    """Attach the three tasks to a Celery application."""

    @app.task(  # type: ignore[misc]
        name=NOMBRE_AUTORIZAR,
        queue=Cola.INTEGRATIONS_SYNC.value,
        # **No `autoretry_for`.** See the module docstring: `FECAESolicitar` is not
        # idempotent, and a retry after an unknown outcome is how one sale becomes two
        # authorised documents. The reconciliation sweep is this task's retry.
    )
    def _autorizar(**kwargs: str) -> Any:
        try:
            return autorizar_sync(settings, **kwargs)
        except ArcaNoDisponible:
            # Logged and swallowed rather than raised: raising marks the task failed and
            # Celery's own machinery would redeliver it, which is the retry this task must
            # not have. The document stays in `ENVIADO_A_ARCA` and the sweep settles it.
            logger.warning("autorizacion_sin_respuesta_de_arca", **kwargs)
            return None

    @app.task(name=NOMBRE_RECONCILIAR, queue=Cola.INTEGRATIONS_SYNC.value)  # type: ignore[misc]
    def _reconciliar() -> Any:
        return reconciliar_sync(settings)

    @app.task(  # type: ignore[misc]
        name=NOMBRE_RECONCILIAR_EMPRESA, queue=Cola.INTEGRATIONS_SYNC.value
    )
    def _reconciliar_empresa(**kwargs: str) -> Any:
        return reconciliar_empresa_sync(settings, **kwargs)


__all__ = [
    "NOMBRE_AUTORIZAR",
    "NOMBRE_RECONCILIAR",
    "NOMBRE_RECONCILIAR_EMPRESA",
    "ColaDeEmision",
    "autorizar",
    "reconciliar",
    "reconciliar_empresa",
    "registrar",
]
