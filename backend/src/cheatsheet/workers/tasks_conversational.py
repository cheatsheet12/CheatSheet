"""El barrido que reindexa las FAQ marcadas obsoletas.

Existe por dos motivos, y los dos están en el DER:

1. **Recuperar lo que se guardó sin indexar.** Una FAQ creada mientras el proveedor de
   embeddings estaba caído existe, se puede editar y se puede leer — lo único que no puede es
   encontrarse por significado. Este barrido cierra esa ventana sin que nadie tenga que
   acordarse de volver a guardarla.

2. **Migrar de modelo sin recalcular todo de golpe.** `embedding_modelo_version` dice con qué
   modelo se calculó cada vector; marcarlos obsoletos en lote y dejar que el barrido los
   alcance permite cambiar de modelo sin una ventana en la que la búsqueda no responde.

**No reintenta.** `autoretry_for` está ausente a propósito, igual que en los barridos de cobros
y de la DLQ: si una corrida falla, la siguiente levanta exactamente las mismas filas, porque la
consulta es por `embedding_obsoleto` y no por cursor.

**Cada FAQ falla sola.** Un error del proveedor sobre una salta a la siguiente en lugar de
cortar la corrida: la alternativa es que una pregunta con un carácter raro bloquee la
reindexación de todas las demás.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.api.conversacional import armar_embeddings
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.conversational.application.faqs import ReindexarFAQs
from cheatsheet.contexts.conversational.infrastructure.ensamblado import Conversaciones
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_BARRIDO = "conversational.barrer_faqs"
NOMBRE_EMPRESA = "conversational.reindexar_empresa"

#: La octava función `SECURITY DEFINER` del sistema, y la misma forma que las siete anteriores:
#: **devuelve ids de empresa y nada más**. La pregunta «quién tiene FAQ sin indexar» no se puede
#: hacer desde adentro de RLS, porque el barrido no es de ninguna empresa.
EMPRESAS_CON_FAQS_PENDIENTES = text("SELECT empresa_id FROM empresas_con_faqs_pendientes()")


async def empresas_con_faqs_pendientes(sesion: AsyncSession) -> list[EmpresaId]:
    """Qué empresas tienen FAQ esperando su vector.

    La sesión tiene que ser una **sin** empresa (`sesion_sin_empresa`): con una puesta, la
    política acotaría al llamador a un solo inquilino y el barrido reindexaría siempre las
    mismas.
    """
    filas = await sesion.execute(EMPRESAS_CON_FAQS_PENDIENTES)
    return [EmpresaId(fila[0]) for fila in filas]


async def barrer_faqs(recursos: Recursos) -> int:
    """Reparte una tarea por empresa con FAQ pendientes. Devuelve cuántas."""
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_faqs_pendientes(sesion)

    for empresa_id in empresas:
        _encolar_empresa(recursos.settings, empresa_id)
    if empresas:
        logger.info("barrido_de_faqs_despachado", empresas=len(empresas))
    return len(empresas)


async def reindexar_empresa(recursos: Recursos, empresa_id: EmpresaId) -> int:
    """Recalcula los vectores pendientes de una empresa. Devuelve cuántos pudo."""
    indexadas = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Conversaciones.armar(unidad)
        indexadas = await ReindexarFAQs(piezas.faqs, armar_embeddings()).ejecutar(
            ahora=unidad.reloj.ahora()
        )
        if indexadas:
            logger.info("faqs_reindexadas", empresa_id=str(empresa_id), cuantas=indexadas)
    return indexadas


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
        logger.exception("no_se_pudo_encolar_barrido_de_faqs", empresa_id=str(empresa_id))


def barrer_faqs_sync(settings: Settings) -> Any:
    """El puente de Celery al mundo async. Un loop y un juego de recursos por corrida."""
    return ejecutar_tarea(settings, barrer_faqs)


def reindexar_empresa_sync(settings: Settings, *, empresa_id: str) -> Any:
    identificador = EmpresaId(UUID(empresa_id))
    return ejecutar_tarea(settings, lambda recursos: reindexar_empresa(recursos, identificador))


def registrar(app: Celery, settings: Settings) -> None:
    """Ata las dos tareas a una aplicación de Celery."""

    @app.task(  # type: ignore[misc]
        name=NOMBRE_BARRIDO,
        queue=Cola.NOTIFICATIONS.value,
        # Sin `autoretry_for`. Ver el docstring del módulo.
    )
    def barrido() -> Any:
        return barrer_faqs_sync(settings)

    @app.task(name=NOMBRE_EMPRESA, queue=Cola.NOTIFICATIONS.value)  # type: ignore[misc]
    def de_empresa(empresa_id: str) -> Any:
        return reindexar_empresa_sync(settings, empresa_id=empresa_id)


__all__ = [
    "NOMBRE_BARRIDO",
    "NOMBRE_EMPRESA",
    "barrer_faqs",
    "empresas_con_faqs_pendientes",
    "registrar",
    "reindexar_empresa",
]
