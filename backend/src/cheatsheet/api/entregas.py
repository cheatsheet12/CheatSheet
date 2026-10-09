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

**Una transacción por estado y cada estado aislado de los demás**: si el segundo falla, el primero
ya quedó aplicado y el tercero se aplica igual. Un estado que falla por algo suyo (un `wamid` que
rompe una consulta, una fila inconsistente) se registra con la clase de su excepción —nunca con el
`wamid`, el teléfono ni el texto— y se sigue: un 500 haría que Meta reintentara **el mismo estado
venenoso** durante horas, y en la ruta por empresa bloquearía los mensajes del cliente que vienen
en la misma notificación. Solo una falla **transitoria** de la base (conexión caída, tiempo agotado,
deadlock) se vuelve a levantar, **al final** y envuelta en `EstadosSinAplicarPorFallaTransitoria`:
ese 500 sí es lo que Meta debe reintentar, y el reintento es idempotente. Vive acá y no en el router
para que `routers/whatsapp.py` no crezca.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import cast

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as TiempoAgotadoDelPool

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

#: Las clases de error de PostgreSQL (los dos primeros caracteres del `SQLSTATE`) que son del
#: momento y no del estado: 08 conexión, 40 deadlock o serialización, 53 recursos agotados, 57
#: operador (reinicio, cancelación).
_CLASES_DE_SQLSTATE_TRANSITORIAS = ("08", "40", "53", "57")


class EstadosSinAplicarPorFallaTransitoria(Exception):
    """Al menos un estado no se aplicó porque la base falló por algo pasajero.

    Se levanta **después** de intentar todos los demás. Lleva la causa original en `__cause__`.
    """


def es_falla_transitoria(error: Exception) -> bool:
    """Si el error es de la base o la red **en este momento** y no del estado que se aplicaba.

    Transitorias: una conexión caída o inaccesible (`OperationalError`, `InterfaceError`,
    `ConnectionError`), un tiempo agotado (`TimeoutError`, el del pool de SQLAlchemy) y cualquier
    `DBAPIError` que la base clasifique como de conexión, deadlock, serialización o recursos
    (`SQLSTATE` 08, 40, 53, 57), porque el controlador asíncrono no siempre lo traduce a
    `OperationalError`. **No** lo son `IntegrityError`, `DataError`, `ProgrammingError` ni un error
    de nuestro código: reintentar el mismo estado fallaría igual, siempre.
    """
    if isinstance(
        error,
        OperationalError | InterfaceError | TiempoAgotadoDelPool | ConnectionError | TimeoutError,
    ):
        return True
    if isinstance(error, DBAPIError):
        sqlstate = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
        return error.connection_invalidated or (
            isinstance(sqlstate, str) and sqlstate.startswith(_CLASES_DE_SQLSTATE_TRANSITORIAS)
        )
    return False


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
    transitoria: Exception | None = None
    for estado in estados:
        try:
            if estado.waba_id not in duenas_por_waba:
                async with sesion_sin_empresa(recursos.sesiones) as sesion:
                    duenas_por_waba[estado.waba_id] = await empresas_de_la_cuenta_de_whatsapp(
                        sesion, estado.waba_id
                    )
            empresa = _empresa_de(duenas_por_waba[estado.waba_id], empresa_de_la_url)
            if empresa is not None:
                await _aplicar_en_su_transaccion(recursos, empresa, estado)
        except Exception as error:  # noqa: BLE001 — ver abajo
            # `Exception` es lo que `CLAUDE.md` §5 prohíbe en general, y acá está acotado por el
            # motivo: **un estado no puede tumbar a los demás ni a los mensajes del cliente**. Lo
            # que se levanta lo decide `es_falla_transitoria` (clases concretas de SQLAlchemy y
            # `SQLSTATE`), no un `pass`: lo transitorio se reintenta al final, lo demás se registra.
            # Solo la clase de la excepción: su texto puede traer el `wamid` o la consulta.
            if es_falla_transitoria(error):
                logger.warning("whatsapp_estado_con_falla_transitoria", causa=type(error).__name__)
                transitoria = transitoria or error
            else:
                logger.error(
                    "whatsapp_estado_sin_aplicar", causa=type(error).__name__, estado=estado.estado
                )
    if transitoria is not None:
        raise EstadosSinAplicarPorFallaTransitoria(
            "Un estado de entrega no se aplicó por una falla transitoria de la base"
        ) from transitoria


async def _aplicar_en_su_transaccion(
    recursos: Recursos, empresa: EmpresaId, estado: EstadoDeEntregaNotificado
) -> None:
    """Un estado, una transacción. `aclosing` cierra el generador si el cuerpo levanta.

    Sin él, una excepción en el `async for` dejaría la unidad de trabajo suspendida hasta que el
    recolector la cierre, y con ella la fila bloqueada (`FOR UPDATE`) y la conexión: el siguiente
    callback del mismo `wamid` esperaría por un estado que ya se descartó.
    """
    encontrado = False
    # Es un generador asíncrono (se anota como `AsyncIterator`): el `cast` es para `aclose`.
    generador = cast("AsyncGenerator[UnidadDeTrabajo, None]", unidad_de_trabajo(recursos, empresa))
    async with aclosing(generador) as unidades:
        async for unidad in unidades:
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


__all__ = [
    "EstadosSinAplicarPorFallaTransitoria",
    "aplicar_estados_de_entrega",
    "es_falla_transitoria",
]
