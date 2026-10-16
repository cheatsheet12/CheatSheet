"""La conciliación de las plantillas de WhatsApp con Meta (U6, D-U6-9).

**Es la red de seguridad del webhook de estado de plantillas**, que no admite override por cuenta y
depende de una configuración de la app que no podemos verificar sin la app de prueba: si el evento
no llega, una plantilla quedaría `PENDIENTE` para siempre. Un fan-out y una tarea por empresa, en
la cola `integrations_sync`:

- `business_config.conciliar_plantillas` (Beat): una tarea por empresa con WhatsApp conectado.
- `business_config.conciliar_empresa`: `ConciliarPlantillasConMeta` de **esa** empresa, con el
  token y la WABA de **esa** empresa. Una sola llamada `GET` por corrida.

**Ninguna reintenta.** `autoretry_for` está ausente a propósito, igual que los barridos de cobros:
si una corrida falla, la siguiente lee lo mismo, porque las consultas son por estado. Y es
idempotente por construcción: aplicar el mismo estado dos veces no cambia nada, y una plantilla
creada cuya respuesta se perdió la encuentra la corrida siguiente **por nombre** antes de crearla
otra vez.
"""

from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mensajeria import armar_revision_de_meta
from cheatsheet.contexts.business_config.application.conciliacion import (
    ConciliarPlantillasConMeta,
    ResumenDeConciliacion,
)
from cheatsheet.contexts.business_config.infrastructure.ensamblado import ConfiguracionDeNegocio
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    empresas_con_whatsapp_conectado,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_BARRIDO = "business_config.conciliar_plantillas"
NOMBRE_EMPRESA = "business_config.conciliar_empresa"


async def conciliar_plantillas(recursos: Recursos) -> int:
    """Reparte una tarea por empresa con WhatsApp conectado. Devuelve cuántas.

    La sesión es **sin empresa**: la función `SECURITY DEFINER` que responde esta pregunta tiene
    que correr fuera de RLS, o contestaría siempre por el mismo inquilino.
    """
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_whatsapp_conectado(sesion)

    for empresa_id in empresas:
        _encolar_empresa(recursos.settings, empresa_id)
    if empresas:
        logger.info("conciliacion_de_plantillas_despachada", empresas=len(empresas))
    return len(empresas)


async def conciliar_empresa(recursos: Recursos, empresa_id: EmpresaId) -> ResumenDeConciliacion:
    """Siembra, manda lo que falta y aplica el estado de Meta de **una** empresa."""
    resumen = ResumenDeConciliacion()
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = ConfiguracionDeNegocio.armar(unidad)
        revision = await armar_revision_de_meta(unidad, recursos.settings, empresa_id=empresa_id)
        resumen = await ConciliarPlantillasConMeta(piezas.plantillas, revision).ejecutar(
            empresa_id=empresa_id, ahora=unidad.reloj.ahora()
        )
    if resumen.sembradas or resumen.enviadas or resumen.actualizadas or resumen.interrumpida:
        logger.info(
            "conciliacion_de_plantillas",
            empresa_id=str(empresa_id),
            sembradas=resumen.sembradas,
            enviadas=resumen.enviadas,
            actualizadas=resumen.actualizadas,
            divergentes=resumen.divergentes,
            interrumpida=resumen.interrumpida,
        )
    return resumen


@lru_cache(maxsize=1)
def _despachador(settings: Settings) -> Celery:
    """El cliente de Celery del barrido, armado una vez. `Settings` es inmutable: se cachea."""
    return crear_celery(settings)


def _encolar_empresa(settings: Settings, empresa_id: EmpresaId) -> None:
    """Un hipo del broker no puede abortar el reparto.

    Perder el mensaje de una empresa cuesta una corrida de espera; dejar que la excepción se
    escape cuesta todas las que venían después en el bucle.
    """
    try:
        _despachador(settings).send_task(
            NOMBRE_EMPRESA,
            kwargs={"empresa_id": str(empresa_id)},
            queue=Cola.INTEGRATIONS_SYNC.value,
        )
    except (KombuError, OSError):
        logger.exception(
            "no_se_pudo_encolar_conciliacion_de_plantillas", empresa_id=str(empresa_id)
        )


def conciliar_plantillas_sync(settings: Settings) -> Any:
    """El puente de Celery al mundo async. Un loop y un juego de recursos por corrida."""
    return ejecutar_tarea(settings, conciliar_plantillas)


def conciliar_empresa_sync(settings: Settings, *, empresa_id: str) -> dict[str, Any]:
    """The summary goes back as a dict: Celery stores results as JSON, and a dataclass is not."""
    identificador = EmpresaId(UUID(empresa_id))
    resumen = ejecutar_tarea(settings, lambda recursos: conciliar_empresa(recursos, identificador))
    return asdict(resumen)


def registrar(app: Celery, settings: Settings) -> None:
    """Ata las dos tareas a una aplicación de Celery."""

    @app.task(  # type: ignore[misc]
        name=NOMBRE_BARRIDO,
        queue=Cola.INTEGRATIONS_SYNC.value,
        # Sin `autoretry_for`. Ver el docstring del módulo: la corrida siguiente lee lo mismo.
    )
    def _barrido() -> Any:
        return conciliar_plantillas_sync(settings)

    @app.task(name=NOMBRE_EMPRESA, queue=Cola.INTEGRATIONS_SYNC.value)  # type: ignore[misc]
    def _empresa(**kwargs: str) -> Any:
        return conciliar_empresa_sync(settings, **kwargs)


__all__ = [
    "NOMBRE_BARRIDO",
    "NOMBRE_EMPRESA",
    "conciliar_empresa",
    "conciliar_plantillas",
    "registrar",
]
