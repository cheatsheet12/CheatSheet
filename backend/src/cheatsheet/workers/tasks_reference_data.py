"""Syncing ARCA's fiscal catalogue, on a schedule (HS-T4).

**The least frequent sweep in the system**, and deliberately so: ARCA's catalogues move
once every several months, not several times a day. Daily is already generous; every half
hour would be a call per company per half hour to learn that nothing changed.

**It runs for one company and stores the result for everyone.** That asymmetry is the whole
shape of this task and it is worth stating plainly: the catalogue is ARCA's, identical for
every taxpayer, but *asking* needs a ticket and a ticket needs a company's certificate. So
the sweep picks a company that has ARCA connected, borrows its credential, and writes rows
that have no `empresa_id`.

The consequence, said out loud: **if no company has ARCA connected, the catalogue never
syncs.** That is correct — with nobody able to invoice, there is nothing to validate — but
it means an empty `parametro_fiscal` is a symptom of a missing certificate and not of a
broken task.
"""

from __future__ import annotations

from typing import Any

from celery import Celery

from cheatsheet.api.arca import armar_catalogos
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    empresas_con_integracion_de_arca,
)
from cheatsheet.contexts.reference_data.application.parametros import (
    SincronizarParametrosFiscales,
)
from cheatsheet.contexts.reference_data.infrastructure.ensamblado import ParametrosFiscales
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.workers.celery_app import Cola
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_SINCRONIZAR = "reference_data.sincronizar_parametros"


async def sincronizar_parametros(recursos: Recursos) -> int:
    """Sync once, borrowing the first available company's ARCA credential.

    **One company, not a fan-out.** Every other sweep in this system fans out because the
    work is per company; this one is not — the catalogue is global, and asking N times
    would write the same rows N times and burn N tickets to learn it.

    Which company is not important and is deliberately not chosen carefully: any of them
    can ask, and they all get the same answer.
    """
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_integracion_de_arca(sesion)

    if not empresas:
        # Not an error. Nobody can invoice yet, so there is nothing to validate against.
        logger.info("sin_empresas_con_arca_para_sincronizar_parametros")
        return 0

    empresa_id = empresas[0]
    cambios = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = ParametrosFiscales.armar(unidad)
        resultado = await SincronizarParametrosFiscales(
            parametros=piezas.parametros,
            catalogos=armar_catalogos(unidad, recursos.settings),
            publicador=unidad.publicador,
        ).ejecutar(empresa_id=empresa_id, ahora=unidad.reloj.ahora())
        cambios = resultado.nuevos + resultado.cerrados
        logger.info(
            "parametros_fiscales_sincronizados",
            nuevos=resultado.nuevos,
            cerrados=resultado.cerrados,
            fallo=resultado.fallo,
        )

    return cambios


def sincronizar_parametros_sync(settings: Settings) -> Any:
    """Celery's bridge into the async world. One loop and one set of resources per run."""
    return ejecutar_tarea(settings, sincronizar_parametros)


def registrar(app: Celery, settings: Settings) -> None:
    """Attach the task to a Celery application.

    One task and no fan-out, unlike every other sweep here: the catalogue is global, so
    there is nothing to enqueue per company.
    """

    @app.task(  # type: ignore[misc]
        name=NOMBRE_SINCRONIZAR,
        queue=Cola.INTEGRATIONS_SYNC.value,
        # No `autoretry_for`. HS-T4 RN-04 already decides what a failure means -- keep the
        # previous catalogue and log it -- so the use case returns normally and there is
        # nothing to retry. The next daily run is the retry.
    )
    def _sincronizar() -> Any:
        return sincronizar_parametros_sync(settings)
