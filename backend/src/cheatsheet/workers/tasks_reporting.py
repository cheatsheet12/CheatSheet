"""El envío automático del paquete contable (HU-E10-04 RN-01 y RN-02).

Un barrido diario que casi todos los días no hace nada: pregunta qué empresas configuraron el
envío **para hoy** y reparte una tarea por cada una. Diario y no mensual porque el día es
configurable por empresa —del 1 al 28—, así que no hay un día del mes en el que corresponda
correr; lo que hay es un día por empresa.

**Cada empresa arma el paquete del mes cerrado, no del mes en curso.** Es lo que dice RN-01, y
la diferencia importa: un paquete armado el 5 con el mes corriente llevaría cinco días de datos
y se llamaría igual que el completo.

**No reintenta.** `autoretry_for` está ausente a propósito, igual que en el barrido de cobros y
en el de la DLQ: la corrida siguiente levanta exactamente las mismas empresas, porque la
consulta es por configuración y no por cursor. Y si el paquete ya se armó, `del_periodo` lo
encuentra y lo rehace en lugar de duplicarlo — el índice único garantiza que sea así.

**Un paquete armado no manda un mail.** El contador ya tiene su enlace (HU-E10-05) y lo que
hace el enlace es listar los paquetes disponibles; agregarle un correo por mes a este barrido
sería mandar una notificación que nadie pidió, con un adjunto de documentación fiscal, a una
casilla que puede haber cambiado de dueño. Está anotado en los pendientes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.reporteria import armar_bitacora, armar_cobranzas, armar_facturacion
from cheatsheet.contexts.reporting.application.paquete import (
    GenerarPaqueteContable,
    periodo_cerrado,
)
from cheatsheet.contexts.reporting.infrastructure.ensamblado import Reporteria
from cheatsheet.contexts.reporting.infrastructure.repositories import empresas_con_paquete_activo
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_BARRIDO = "reporting.barrer_paquetes"
NOMBRE_EMPRESA = "reporting.armar_paquete"


async def barrer_paquetes(recursos: Recursos) -> int:
    """Reparte una tarea por empresa que tenga el envío programado para hoy. Devuelve cuántas.

    La sesión es **sin empresa**: la función `SECURITY DEFINER` que contesta esta pregunta
    tiene que correr fuera de RLS, o contestaría siempre por el mismo inquilino.
    """
    dia = recursos.reloj.ahora().day
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_paquete_activo(sesion, dia)

    for empresa_id in empresas:
        _encolar_empresa(recursos.settings, empresa_id)
    if empresas:
        logger.info("barrido_de_paquetes_despachado", dia=dia, empresas=len(empresas))
    return len(empresas)


async def armar_paquete(recursos: Recursos, empresa_id: EmpresaId) -> bool:
    """El paquete del mes cerrado de una empresa. Devuelve si quedó con archivo.

    Usa el **mismo** caso de uso que el botón «generar paquete de prueba» de PAN-REP-02. Un
    camino distinto para el envío automático probaría otra cosa que la que se manda.
    """
    armado = False
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Reporteria.armar(unidad, recursos.settings)
        configuracion = await piezas.paquetes.configuracion()
        if configuracion is None or not configuracion.activo:
            # Alguien desactivó el envío entre el reparto y la ejecución. No es un error: es
            # exactamente lo que el interruptor promete.
            logger.info("paquete_omitido_envio_inactivo", empresa_id=str(empresa_id))
            continue
        ahora = unidad.reloj.ahora()
        paquete = await GenerarPaqueteContable(
            paquetes=piezas.paquetes,
            facturacion=armar_facturacion(unidad),
            cobranzas=armar_cobranzas(unidad),
            bitacora=armar_bitacora(unidad),
            archivos=piezas.archivos,
            publicador=unidad.publicador,
        ).ejecutar(
            empresa_id=empresa_id,
            # Sin usuario: lo armó el sistema, no una persona. Es la misma decisión que el
            # resto de los barridos, y `iniciador` en la bitácora es lo que lo distingue.
            usuario_id=None,
            periodo=periodo_cerrado(ahora),
            contenido=configuracion.contenido,
            formatos=configuracion.formatos,
            ahora=ahora,
        )
        armado = paquete.esta_disponible
        logger.info("paquete_contable_armado", empresa_id=str(empresa_id), periodo=paquete.etiqueta)
    return armado


def _encolar_empresa(settings: Settings, empresa_id: EmpresaId) -> None:
    """Un hipo del broker no puede abortar el reparto.

    Perder el mensaje de una empresa cuesta una corrida de espera; dejar que la excepción se
    escape cuesta todas las que venían después en el bucle.
    """
    try:
        crear_celery(settings).send_task(
            NOMBRE_EMPRESA,
            kwargs={"empresa_id": str(empresa_id)},
            queue=Cola.NOTIFICATIONS.value,
        )
    except KombuError:
        logger.exception("no_se_pudo_encolar_paquete", empresa_id=str(empresa_id))


def barrer_paquetes_sync(settings: Settings) -> Any:
    """El puente de Celery al mundo async. Un loop y un juego de recursos por corrida."""
    return ejecutar_tarea(settings, barrer_paquetes)


def armar_paquete_sync(settings: Settings, *, empresa_id: str) -> Any:
    identificador = EmpresaId(UUID(empresa_id))
    return ejecutar_tarea(settings, lambda recursos: armar_paquete(recursos, identificador))


def registrar(app: Celery, settings: Settings) -> None:
    """Ata las dos tareas a una aplicación de Celery."""

    @app.task(  # type: ignore[misc]
        name=NOMBRE_BARRIDO,
        queue=Cola.NOTIFICATIONS.value,
        # Sin `autoretry_for`. Ver el docstring del módulo.
    )
    def _barrido() -> Any:
        return barrer_paquetes_sync(settings)

    @app.task(name=NOMBRE_EMPRESA, queue=Cola.NOTIFICATIONS.value)  # type: ignore[misc]
    def _empresa(**kwargs: str) -> Any:
        return armar_paquete_sync(settings, **kwargs)


__all__ = [
    "NOMBRE_BARRIDO",
    "NOMBRE_EMPRESA",
    "armar_paquete",
    "barrer_paquetes",
    "registrar",
]
