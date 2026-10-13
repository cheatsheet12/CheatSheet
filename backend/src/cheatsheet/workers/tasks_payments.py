"""Los dos barridos de cobros: vencer lo vencido (D23) y despachar recordatorios (HS-T3).

**Un solo fan-out para los dos.** Recorren la misma lista de empresas —las que tienen algo
abierto— y el segundo depende del primero: la cadena cuenta días desde el vencimiento, y un
cobro que nadie marcó vencido es un cobro que nadie sabe que está en mora. Despacharlos en dos
fan-outs independientes haría que un día el orden se invirtiera y los recordatorios salieran
con un día de atraso sin que nadie entendiera por qué.

**Ninguno reintenta.** `autoretry_for` está ausente a propósito, igual que en el barrido de la
DLQ: si una corrida falla, la siguiente levanta exactamente las mismas filas, porque las dos
consultas son por estado y no por cursor. Un barrido que se reintenta a sí mismo dentro de su
propia cola es una forma que conviene no tener.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mensajeria import armar_mensajeria
from cheatsheet.api.mercadopago import armar_cadena, armar_envio
from cheatsheet.contexts.payments.application.recordatorios import (
    DespacharRecordatorios,
    VencerCobros,
)
from cheatsheet.contexts.payments.infrastructure.ensamblado import Cobros
from cheatsheet.contexts.payments.infrastructure.repositories import (
    empresas_con_cobros_abiertos,
    empresas_con_recordatorios_en_espera,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.platform.transaccion import ConfirmacionDeLaUnidad
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_BARRIDO = "payments.barrer_cobros"
NOMBRE_EMPRESA = "payments.barrer_empresa"


async def barrer_cobros(recursos: Recursos) -> int:
    """Reparte una tarea por empresa con algo abierto. Devuelve cuántas.

    «Algo abierto» son los cobros abiertos **y** los recordatorios que esperan su reintento o
    tienen un envío en curso (U7): un cobro que se pagó mientras su recordatorio esperaba no deja
    a la empresa con nada abierto, y sin esta segunda pregunta la fila no se descartaría nunca.

    La sesión es **sin empresa**: las funciones `SECURITY DEFINER` que responden estas preguntas
    tienen que correr fuera de RLS, o contestarían siempre por el mismo inquilino.
    """
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        con_cobros = await empresas_con_cobros_abiertos(sesion)
        con_recordatorios = await empresas_con_recordatorios_en_espera(sesion)
    # Sin repetidas y en orden estable: una empresa con las dos cosas recibe una sola tarea.
    empresas = list(dict.fromkeys([*con_cobros, *con_recordatorios]))

    for empresa_id in empresas:
        _encolar_empresa(recursos.settings, empresa_id)
    if empresas:
        logger.info("barrido_de_cobros_despachado", empresas=len(empresas))
    return len(empresas)


async def barrer_empresa(recursos: Recursos, empresa_id: EmpresaId) -> int:
    """Vence y despacha, **en ese orden y en la misma transacción**.

    Cada cobro del despacho corre en su propio savepoint (`piezas.aislamiento`): un fallo en el
    cobro K no deshace las filas de los cobros 1..K-1, cuyos mensajes ya salieron.

    El orden importa: un cobro que vence hoy tiene que estar `VENCIDO` antes de que la cadena
    lo evalúe, o su primer recordatorio se atrasaría una corrida entera. La transacción los
    junta para que no exista un instante en que uno pasó y el otro no.
    """
    despachados = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Cobros.armar(unidad)
        ahora = unidad.reloj.ahora()
        # El canal se arma **una vez por empresa** (ADR-0011 §2): lee la integración de esa
        # empresa, y el barrido corre en el worker con el mismo `WHATSAPP_ADAPTADOR` que la API.
        canal = await armar_mensajeria(unidad, recursos.settings, empresa_id=empresa_id)

        vencidos = await VencerCobros(cobros=piezas.cobros, publicador=unidad.publicador).ejecutar(
            empresa_id=empresa_id, ahora=ahora
        )

        resultado = await DespacharRecordatorios(
            cobros=piezas.cobros,
            recordatorios=piezas.recordatorios,
            envio=armar_envio(unidad, canal=canal),
            cadena=armar_cadena(unidad),
            publicador=unidad.publicador,
            aislamiento=piezas.aislamiento,
            # Confirma cada recordatorio antes y después de hablar con Meta (U7, D-U7-3, H1).
            transaccion=ConfirmacionDeLaUnidad(unidad.sesion, empresa_id),
            # El reloj real, no el `ahora` del barrido: ventanas y fechas se miden al escribir (S2).
            reloj=unidad.reloj,
        ).ejecutar(empresa_id=empresa_id, ahora=ahora)
        despachados = resultado.procesados

        if vencidos.procesados or despachados or resultado.fallidos or resultado.reintentos:
            logger.info(
                "barrido_de_cobros",
                empresa_id=str(empresa_id),
                vencidos=vencidos.procesados,
                recordatorios=despachados,
                recordatorios_fallidos=resultado.fallidos,
                recordatorios_en_reintento=resultado.reintentos,
            )
    return despachados


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
        logger.exception("no_se_pudo_encolar_barrido_de_cobros", empresa_id=str(empresa_id))


def barrer_cobros_sync(settings: Settings) -> Any:
    """El puente de Celery al mundo async. Un loop y un juego de recursos por corrida."""
    return ejecutar_tarea(settings, barrer_cobros)


def barrer_empresa_sync(settings: Settings, *, empresa_id: str) -> Any:
    identificador = EmpresaId(UUID(empresa_id))
    return ejecutar_tarea(settings, lambda recursos: barrer_empresa(recursos, identificador))


def registrar(app: Celery, settings: Settings) -> None:
    """Ata las dos tareas a una aplicación de Celery."""

    @app.task(  # type: ignore[misc]
        name=NOMBRE_BARRIDO,
        queue=Cola.NOTIFICATIONS.value,
        # Sin `autoretry_for`. Ver el docstring del módulo: la corrida siguiente levanta las
        # mismas filas porque las consultas son por estado y no por cursor.
    )
    def _barrido() -> Any:
        return barrer_cobros_sync(settings)

    @app.task(name=NOMBRE_EMPRESA, queue=Cola.NOTIFICATIONS.value)  # type: ignore[misc]
    def _empresa(**kwargs: str) -> Any:
        return barrer_empresa_sync(settings, **kwargs)


__all__ = [
    "NOMBRE_BARRIDO",
    "NOMBRE_EMPRESA",
    "barrer_cobros",
    "barrer_empresa",
    "registrar",
]
