"""El pedido HTTP a la Graph API de Meta con reintento, compartido (U5, U6).

Lo usan el envío de mensajes (`MensajeriaWhatsApp.enviar` y `enviar_plantilla`) y el cliente de
plantillas (`PlantillasDeMeta`): un solo bucle, una sola política, un solo lugar que clasifica.

- **Transitorio** (sin conexión, 5xx, 429, límites de tasa): hasta `INTENTOS` intentos con
  `ESPERAS` entre uno y otro; agotados, `MensajeriaSaturada`.
- **Permanente** (un 4xx, o un código que Meta no va a aceptar): un solo intento y
  `MensajeRechazado`.
- **Incierto** (timeout de lectura, conexión cortada): un solo intento y `EnvioIncierto`. El
  pedido pudo haber llegado y no hay clave de idempotencia: un duplicado es peor que un faltante.

`esperar` se inyecta para que los tests no duerman. El log lleva `estado`, `codigo` y
`fbtrace_id`; **nunca** `error.message`, `error_data`, el teléfono, el texto ni los parámetros.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping

import httpx

from cheatsheet.contexts.conversational.application.errors import (
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.infrastructure.canal_errores import (
    FALLAS_SIN_SALIDA,
    ErrorDeMeta,
    leer_error,
)
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Cuántas veces se reintenta un pedido. Dos reintentos sobre un 5xx alcanzan para un blip;
#: más sería tenerle a alguien el request abierto mientras Meta se recupera.
INTENTOS = 3

#: Segundos de espera antes del 2.º y del 3.er intento (exponencial, sin variable de entorno).
ESPERAS = (1.0, 2.0)

Esperar = Callable[[float], Awaitable[None]]


async def pedir_a_meta(
    cliente: httpx.AsyncClient,
    metodo: str,
    ruta: str,
    *,
    token: str,
    objeto: str = "el mensaje",
    cuerpo: Mapping[str, object] | None = None,
    parametros: Mapping[str, str] | None = None,
    esperar: Esperar = asyncio.sleep,
    con_mensaje: bool = False,
) -> httpx.Response:
    """La respuesta exitosa (< 300), o la excepción tipada que corresponda.

    `objeto` es solo para el texto de la excepción («el mensaje», «la plantilla»).
    `con_mensaje` hace que un rechazo lleve el `error_user_msg` de Meta (solo plantillas).
    """
    codigo: int | None = None
    for intento in range(INTENTOS):
        resultado = await _intentar(
            cliente, metodo, ruta, token, objeto, cuerpo, parametros, con_mensaje
        )
        if isinstance(resultado, httpx.Response):
            return resultado
        codigo = resultado.codigo
        if intento < INTENTOS - 1:
            logger.info("whatsapp_reintenta", intento=intento + 1)
            await esperar(ESPERAS[intento])
    raise MensajeriaSaturada("WhatsApp no respondió", codigo=codigo)


async def _intentar(
    cliente: httpx.AsyncClient,
    metodo: str,
    ruta: str,
    token: str,
    objeto: str,
    cuerpo: Mapping[str, object] | None,
    parametros: Mapping[str, str] | None,
    con_mensaje: bool,
) -> httpx.Response | ErrorDeMeta:
    """Un intento: la respuesta si salió, el error transitorio si conviene reintentar.

    Un error permanente o incierto sale como excepción y corta el bucle.
    """
    try:
        respuesta = await cliente.request(
            metodo,
            ruta,
            json=cuerpo,
            params=parametros,
            headers={"Authorization": f"Bearer {token}"},
        )
    except FALLAS_SIN_SALIDA:
        # El pedido no salió: reintentar no puede duplicar nada.
        logger.warning("whatsapp_sin_conexion")
        return ErrorDeMeta(estado=0, codigo=None, fbtrace_id=None)
    except httpx.HTTPError as exc:
        logger.warning("whatsapp_envio_incierto", causa=type(exc).__name__)
        raise EnvioIncierto(f"WhatsApp: resultado incierto ({type(exc).__name__})") from exc

    if respuesta.status_code < 300:
        return respuesta
    error = leer_error(respuesta, con_mensaje=con_mensaje)
    logger.warning(
        "whatsapp_rechazo_el_mensaje",
        estado=error.estado,
        codigo=error.codigo,
        fbtrace_id=error.fbtrace_id,
    )
    if error.es_transitorio:
        return error
    raise MensajeRechazado(
        f"WhatsApp rechazó {objeto} (HTTP {error.estado}, código {error.codigo})",
        codigo=error.codigo,
        subcodigo=error.subcodigo,
        mensaje_para_el_usuario=error.mensaje_para_el_usuario,
    )


__all__ = ["ESPERAS", "INTENTOS", "Esperar", "pedir_a_meta"]
