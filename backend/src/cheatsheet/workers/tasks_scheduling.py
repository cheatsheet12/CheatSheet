"""El barrido de recordatorios de turno (U8, HU-E8-04): un fan-out y una tarea por empresa.

La forma de `tasks_payments.py`: `scheduling.recordar_turnos` pregunta, **fuera de RLS**, qué empresas
tienen un turno abierto por recordar o un recordatorio sin terminar, y reparte una tarea
`scheduling.recordar_empresa` a cada una. Las dos van por la cola `notifications`.

**Ninguna reintenta.** `autoretry_for` está ausente a propósito: si una corrida falla, la siguiente
reevalúa por estado (la fila de cada recordatorio dice qué falta), no por cursor. Un barrido que se
reintenta a sí mismo dentro de su propia cola es una forma que conviene no tener.

**Empresa sin WhatsApp (D-U8-13).** La tarea arma el canal una vez y, si es `SinCanal`, sale con el log
`recordatorios_de_turno_sin_canal` antes de crear ninguna fila: una empresa que no usa WhatsApp no se
llena de recordatorios `FALLIDO` ni de hilos vacíos.

**Regla de agenda malformada (D-U8-5).** La tarea de una empresa con la regla corrupta termina en
silencio con su log (lo atrapa el caso de uso): nunca aborta a las demás ni se vuelve un 422.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mensajeria import armar_mensajeria
from cheatsheet.api.recordatorios_de_turno import (
    armar_recordatorios_de_turno,
    sin_canal_conectado,
)
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import ANTICIPACION_MAXIMA_MIN
from cheatsheet.contexts.scheduling.infrastructure.repositorio_de_recordatorios import (
    empresas_con_turnos_por_recordar,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_BARRIDO = "scheduling.recordar_turnos"
NOMBRE_EMPRESA = "scheduling.recordar_empresa"

#: Hasta cuándo se mira hacia adelante: la máxima anticipación que la regla admite (168 h).
HORIZONTE = timedelta(minutes=ANTICIPACION_MAXIMA_MIN)


async def recordar_turnos(recursos: Recursos) -> int:
    """Reparte una tarea por empresa con algo por recordar. Devuelve cuántas.

    La sesión es **sin empresa**: la función `SECURITY DEFINER` que responde esta pregunta tiene que
    correr fuera de RLS, o contestaría siempre por el mismo inquilino.
    """
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_turnos_por_recordar(
            sesion, recursos.reloj.ahora() + HORIZONTE
        )
    # Sin repetidas y en orden estable: una empresa recibe una sola tarea.
    unicas = list(dict.fromkeys(empresas))
    for empresa_id in unicas:
        _encolar_empresa(recursos.settings, EmpresaId(empresa_id))
    if unicas:
        logger.info("recordatorios_de_turno_despachados", empresas=len(unicas))
    return len(unicas)


async def recordar_empresa(recursos: Recursos, empresa_id: EmpresaId) -> int:
    """Corre el barrido de una empresa. Devuelve cuántos recordatorios salieron."""
    enviados = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        # El canal se arma **una vez por empresa** (ADR-0011 §2) y antes que nada: sin WhatsApp
        # conectado no se crea ninguna fila.
        canal = await armar_mensajeria(unidad, recursos.settings, empresa_id=empresa_id)
        if sin_canal_conectado(canal):
            logger.info("recordatorios_de_turno_sin_canal", empresa_id=str(empresa_id))
            # Sin `return` acá: salir de un `async for` deja el generador suspendido, con la
            # conexión sacada del pool. Se termina el bucle y la unidad se cierra sola.
            continue
        resultado = await armar_recordatorios_de_turno(
            unidad, empresa_id=empresa_id, canal=canal
        ).ejecutar(empresa_id=empresa_id, ahora=unidad.reloj.ahora())
        enviados = resultado.enviados
        if resultado.hubo_actividad:
            logger.info(
                "recordatorios_de_turno",
                empresa_id=str(empresa_id),
                enviados=resultado.enviados,
                fallidos=resultado.fallidos,
                en_reintento=resultado.en_reintento,
                omitidos=resultado.omitidos,
                descartados=resultado.descartados,
            )
    return enviados


def _encolar_empresa(settings: Settings, empresa_id: EmpresaId) -> None:
    """Un hipo del broker no puede abortar el reparto: perder una empresa cuesta una corrida."""
    try:
        crear_celery(settings).send_task(
            NOMBRE_EMPRESA,
            kwargs={"empresa_id": str(empresa_id)},
            queue=Cola.NOTIFICATIONS.value,
        )
    except KombuError:
        logger.exception("no_se_pudo_encolar_recordatorios_de_turno", empresa_id=str(empresa_id))


def recordar_turnos_sync(settings: Settings) -> Any:
    """El puente de Celery al mundo async. Un loop y un juego de recursos por corrida."""
    return ejecutar_tarea(settings, recordar_turnos)


def recordar_empresa_sync(settings: Settings, *, empresa_id: str) -> Any:
    identificador = EmpresaId(UUID(empresa_id))
    return ejecutar_tarea(settings, lambda recursos: recordar_empresa(recursos, identificador))


def registrar(app: Celery, settings: Settings) -> None:
    """Ata las dos tareas a una aplicación de Celery."""

    @app.task(  # type: ignore[misc]
        name=NOMBRE_BARRIDO,
        queue=Cola.NOTIFICATIONS.value,
        # Sin `autoretry_for`. Ver el docstring del módulo: la corrida siguiente reevalúa por estado.
    )
    def _barrido() -> Any:
        return recordar_turnos_sync(settings)

    @app.task(name=NOMBRE_EMPRESA, queue=Cola.NOTIFICATIONS.value)  # type: ignore[misc]
    def _empresa(**kwargs: str) -> Any:
        return recordar_empresa_sync(settings, **kwargs)


__all__ = [
    "HORIZONTE",
    "NOMBRE_BARRIDO",
    "NOMBRE_EMPRESA",
    "recordar_empresa",
    "recordar_turnos",
    "registrar",
]
