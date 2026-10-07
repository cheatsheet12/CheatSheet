"""Los callbacks de estado de entrega de Meta (`statuses[]`) llegan a su mensaje (U7, HU-E8-04 RN-04).

Un `statuses[]` dice qué pasó con un `wamid`. **Se rutea por la empresa dueña de la WABA** del
`entry[].id`, nunca por la URL: en la ruta de la app la empresa sale de la WABA, y en la ruta por
empresa se verifica que la WABA sea la de esa empresa (mismo modelo de confianza que el estado de
las plantillas, U6). Una WABA ajena, sin dueña o con dos se registra y se descarta.

Dentro de la empresa se prueba primero la tabla `mensaje` (agente y operador) y después
`recordatorio` (cobros). Bajo RLS un `wamid` de otra empresa **no existe**: nunca hay cruce de
inquilinos. Un `wamid` que no es de ninguna se registra **sin el id** y se contesta 200: el `sent` puede
llegar antes de que haga commit la transacción que mandó el mensaje, y los estados siguientes
(`delivered`, `read`) llegan después.

**Una transacción por estado**: si el segundo falla, el primero ya quedó aplicado, y el reintento
de Meta es idempotente. Vive acá y no en el router para que `routers/whatsapp.py` no crezca.
"""

from __future__ import annotations

from cheatsheet.api.dependencies import Recursos, UnidadDeTrabajo, unidad_de_trabajo
from cheatsheet.api.whatsapp_notificaciones import EstadoDeEntregaNotificado
from cheatsheet.contexts.conversational.application.entregas import RegistrarEstadoDeEntrega
from cheatsheet.contexts.conversational.domain.conversacion import EstadoEntrega as EstadoDeMensaje
from cheatsheet.contexts.conversational.infrastructure.ensamblado import Conversaciones
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    empresas_de_la_cuenta_de_whatsapp,
)
from cheatsheet.contexts.payments.application.entregas import RegistrarEntregaDeRecordatorio
from cheatsheet.contexts.payments.domain.recordatorio import (
    EstadoEntrega as EstadoDeRecordatorio,
)
from cheatsheet.contexts.payments.infrastructure.ensamblado import Cobros
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)


async def aplicar_estados_de_entrega(
    recursos: Recursos,
    estados: list[EstadoDeEntregaNotificado],
    *,
    empresa_de_la_url: EmpresaId | None = None,
) -> None:
    """Aplica cada `statuses[]` en la empresa dueña de su WABA, una transacción por estado.

    `empresa_de_la_url` es la de la ruta por empresa: si la WABA del cuerpo no es la suya, el
    estado se descarta. Es `None` en la ruta de la app, donde la WABA decide.
    """
    duenas_por_waba: dict[str, list[EmpresaId]] = {}
    for estado in estados:
        if estado.waba_id not in duenas_por_waba:
            async with sesion_sin_empresa(recursos.sesiones) as sesion:
                duenas_por_waba[estado.waba_id] = await empresas_de_la_cuenta_de_whatsapp(
                    sesion, estado.waba_id
                )
        duenas = duenas_por_waba[estado.waba_id]
        empresa = _empresa_de(duenas, empresa_de_la_url)
        if empresa is None:
            continue
        encontrado = False
        async for unidad in unidad_de_trabajo(recursos, empresa):
            encontrado = await _aplicar(unidad, empresa, estado)
        if not encontrado:
            # `warning` y no `info`: si el `wamid` de la respuesta del envío no coincidiera con el
            # de `statuses[]` (verificación 25.4), todos los estados caerían acá y se vería. Sin
            # el `wamid` ni el teléfono: es un id de Meta y se podría cruzar con un mensaje.
            logger.warning("whatsapp_estado_sin_destinatario", estado=estado.estado)


def _empresa_de(duenas: list[EmpresaId], empresa_de_la_url: EmpresaId | None) -> EmpresaId | None:
    """La empresa en la que se aplica el estado, o `None` si no hay que aplicarlo."""
    if empresa_de_la_url is None:
        if len(duenas) == 1:
            return duenas[0]
        logger.warning("whatsapp_estado_de_waba_sin_una_sola_empresa", empresas=len(duenas))
        return None
    if duenas != [empresa_de_la_url]:
        # La WABA del cuerpo no es la de la empresa de la URL: no se confía en la URL.
        logger.warning("whatsapp_estado_de_waba_ajena", empresas=len(duenas))
        return None
    return empresa_de_la_url


async def _aplicar(
    unidad: UnidadDeTrabajo, empresa: EmpresaId, estado: EstadoDeEntregaNotificado
) -> bool:
    """Prueba `mensaje` y después `recordatorio`. Devuelve si el `wamid` era de la empresa."""
    mensajes = Conversaciones.armar(unidad).mensajes
    if await RegistrarEstadoDeEntrega(mensajes).ejecutar(
        externo_id=estado.externo_id,
        estado=EstadoDeMensaje(estado.estado),
        codigo_de_error=estado.codigo_de_error,
    ):
        return True
    return await RegistrarEntregaDeRecordatorio(
        recordatorios=Cobros.armar(unidad).recordatorios, publicador=unidad.publicador
    ).ejecutar(
        empresa_id=empresa,
        externo_id=estado.externo_id,
        estado=EstadoDeRecordatorio(estado.estado),
        codigo_de_error=estado.codigo_de_error,
        ahora=unidad.reloj.ahora(),
    )


__all__ = ["aplicar_estados_de_entrega"]
