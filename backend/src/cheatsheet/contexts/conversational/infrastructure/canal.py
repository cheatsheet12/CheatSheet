"""Por dónde entra y sale WhatsApp: mensajería, transcripción y embeddings.

Tres puertos, cada uno con su par real y su doble. Los tres dobles se niegan a arrancar en
producción, como el resto del sistema.

**`MensajeriaWhatsApp` es lo que el épico 6 y el 7 dejaron pendiente.** Los recordatorios de
cobro y los avisos de turno tienen su propio adaptador de consola desde entonces; éste es el
cliente real que los reemplaza, y por eso vive en `conversational`: es este contexto el que
sabe hablar por el canal. Los otros dos lo alcanzan por el composition root.

**El transcriptor baja el audio, lo transcribe y no lo guarda** (HS-T7 RN-03). El id de
Meta entra, el texto sale, y en el medio no hay ningún `write` — la minimización de datos
personales no es una política que alguien tenga que recordar, es que no hay código que persista
el audio.

**`EmbeddingsSimulados` es determinista y no es un modelo.** Hashea el texto en un vector
estable, así que la misma pregunta siempre da el mismo vector y dos preguntas parecidas dan
vectores **distintos**. Eso último es a propósito: un doble que fingiera entender significados
haría que los tests de HU-E8-03 RN-02 pasaran sin probar nada, y el día que el modelo real
fallara nadie se enteraría.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import struct
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import uuid4

import httpx

from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.application.ports import Transcripcion
from cheatsheet.contexts.conversational.domain.faq import DIMENSION_DEL_VECTOR
from cheatsheet.contexts.conversational.infrastructure.canal_errores import (
    FALLAS_SIN_SALIDA,
    ErrorDeMeta,
    leer_error,
)
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Cuántas veces se reintenta un envío. Dos reintentos sobre un 5xx alcanzan para un blip;
#: más sería tenerle a alguien el request abierto mientras Meta se recupera.
INTENTOS = 3

#: Segundos de espera antes del 2.º y del 3.er intento (exponencial, sin variable de entorno).
ESPERAS = (1.0, 2.0)


@dataclass(frozen=True, slots=True)
class ConfiguracionDeMensajeria:
    token: str
    phone_number_id: str
    graph_url: str
    graph_version: str
    timeout_segundos: float


class MensajeriaSimulada:
    """El doble: deja el mensaje en el log y devuelve un id inventado.

    **Rechazado en producción.** Una empresa cuyos mensajes salen a un log es una empresa cuyos
    clientes no reciben nada y cuyo panel dice que sí.

    No registra el teléfono: es un dato personal, y `CLAUDE.md` §5 lo prohíbe en un log aunque
    el log sea de desarrollo.
    """

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "La mensajería simulada no puede usarse en producción: los mensajes quedarían "
                "en un log y ningún cliente los recibiría"
            )
        self.enviados: list[str] = []

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono
        self.enviados.append(texto)
        logger.info("mensaje_simulado", largo=len(texto))
        # **Un id único por mensaje, no un contador de esta instancia.** El adaptador se
        # construye por request, así que un contador devolvía `simulado-1` siempre — y el
        # índice único de la migración 0021 lo atrapó al segundo mensaje saliente de la misma
        # empresa. Meta devuelve un `wamid` globalmente único; el doble tiene que parecerse a
        # eso, no a un contador.
        return f"simulado-{uuid4()}"


class MensajeriaWhatsApp:
    """El cliente real de la Cloud API de Meta.

    Timeout explícito, reintento con espera y manejo del fallo, como pide `CLAUDE.md` §5 para
    toda llamada externa. Los errores se clasifican en `canal_errores.py`:

    - **Transitorio** (sin conexión, 5xx, 429, límites de tasa): hasta `INTENTOS` intentos con
      `ESPERAS` entre uno y otro; agotados, `MensajeriaSaturada`.
    - **Permanente** (un 4xx, o un código que Meta no va a aceptar): un solo intento y
      `MensajeRechazado`. Reintentarlo es gastar el rate limit de la empresa contra un error
      propio.
    - **Incierto** (timeout de lectura, conexión cortada): un solo intento y `EnvioIncierto`.
      El pedido pudo haber llegado y no hay clave de idempotencia: **un duplicado es peor que
      un mensaje que falta**.

    `esperar` se inyecta para que los tests no duerman. Las excepciones llevan el `error.code`
    de Meta; el log, `estado`, `codigo` y `fbtrace_id` y **nunca** `error.message`,
    `error_data`, el teléfono ni el texto.
    """

    def __init__(
        self,
        configuracion: ConfiguracionDeMensajeria,
        *,
        transporte: httpx.AsyncBaseTransport | None = None,
        esperar: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._config = configuracion
        self._transporte = transporte
        self._esperar = esperar

    async def enviar(self, *, telefono: str, texto: str) -> str:
        cuerpo: dict[str, object] = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": texto},
        }
        ruta = (
            f"{self._config.graph_url.rstrip('/')}/{self._config.graph_version}/"
            f"{self._config.phone_number_id}/messages"
        )
        codigo: int | None = None
        async with httpx.AsyncClient(
            timeout=self._config.timeout_segundos, transport=self._transporte
        ) as cliente:
            for intento in range(INTENTOS):
                resultado = await self._intentar(cliente, ruta, cuerpo)
                if isinstance(resultado, str):
                    return resultado
                codigo = resultado.codigo
                if intento < INTENTOS - 1:
                    logger.info("whatsapp_reintenta", intento=intento + 1)
                    await self._esperar(ESPERAS[intento])
        raise MensajeriaSaturada("WhatsApp no respondió", codigo=codigo)

    async def _intentar(
        self, cliente: httpx.AsyncClient, ruta: str, cuerpo: dict[str, object]
    ) -> str | ErrorDeMeta:
        """Un intento: el `wamid` si salió, el error transitorio si conviene reintentar.

        Un error permanente o incierto sale como excepción y corta el bucle.
        """
        try:
            respuesta = await cliente.post(
                ruta, json=cuerpo, headers={"Authorization": f"Bearer {self._config.token}"}
            )
        except FALLAS_SIN_SALIDA:
            # El pedido no salió: reintentar no puede duplicar nada.
            logger.warning("whatsapp_sin_conexion")
            return ErrorDeMeta(estado=0, codigo=None, fbtrace_id=None)
        except httpx.HTTPError as exc:
            logger.warning("whatsapp_envio_incierto", causa=type(exc).__name__)
            raise EnvioIncierto(f"WhatsApp: resultado incierto ({type(exc).__name__})") from exc

        if respuesta.status_code < 300:
            return _id_del_mensaje(respuesta)
        error = leer_error(respuesta)
        logger.warning(
            "whatsapp_rechazo_el_mensaje",
            estado=error.estado,
            codigo=error.codigo,
            fbtrace_id=error.fbtrace_id,
        )
        if error.es_transitorio:
            return error
        raise MensajeRechazado(
            f"WhatsApp rechazó el mensaje (HTTP {error.estado}, código {error.codigo})",
            codigo=error.codigo,
        )


class SinCanal:
    """El canal de una empresa que no conectó WhatsApp, en producción (ADR-0011 §3).

    **Levanta `CanalNoConectado` y no toca la red.** El puerto devuelve un `str` —el id del
    mensaje— y devolver uno inventado daría por enviado lo que no salió: quien llama
    (recordatorio, aviso, agente, operador) registra el mensaje como **no enviado**.
    """

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        logger.info("whatsapp_sin_conectar_no_se_envia")
        raise CanalNoConectado("La empresa no conectó WhatsApp: el mensaje no se envió")


def _id_del_mensaje(respuesta: httpx.Response) -> str:
    """El `wamid` que Meta devuelve, o una cadena vacía si contestó algo raro.

    Vacío y no una excepción: el mensaje **salió**. Perder el id significa no poder atar los
    callbacks de entrega a esa fila, que es peor que nada pero mucho mejor que tratar un envío
    exitoso como un fracaso.
    """
    try:
        mensajes = respuesta.json().get("messages", [])
        return str(mensajes[0]["id"]) if mensajes else ""
    except (ValueError, KeyError, IndexError, TypeError):
        logger.warning("whatsapp_respondio_sin_id")
        return ""


class TranscriptorSimulado:
    """El doble: devuelve un texto fijo con calidad alta.

    **Rechazado en producción.** Un agente que cree que toda nota de voz dice lo mismo es peor
    que uno que no las acepta.
    """

    def __init__(
        self, entorno: Entorno = Entorno.LOCAL, *, texto: str = "", calidad: float = 0.9
    ) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El transcriptor simulado no puede usarse en producción: devuelve un texto fijo"
            )
        self._texto = texto or "Hola, quiero un turno"
        self._calidad = calidad

    async def transcribir(self, audio_id: str) -> Transcripcion:
        del audio_id
        return Transcripcion(texto=self._texto, calidad=self._calidad)


class EmbeddingsSimulados:
    """Vectores deterministas por hash. **No entiende significados, y no finge entenderlos.**

    Ver el docstring del módulo: es lo que hace que los tests de la búsqueda por significado
    prueben la mecánica —que el vector viaje, que la consulta ordene, que el umbral corte— sin
    afirmar una capacidad que este doble no tiene.

    No se niega en producción y es el único doble del sistema que no lo hace, porque **no hay
    adaptador real todavía**: el proveedor de embeddings se elige cuando se elija, y hasta
    entonces la búsqueda por significado degrada a «no encuentro nada», que el caso de uso
    convierte en ofrecer un asesor. Está anotado en los pendientes del épico.
    """

    @property
    def version(self) -> str:
        return "simulado-hash-v1"

    async def vectorizar(self, texto: str) -> list[float]:
        return _vector_por_hash(texto)


def _vector_por_hash(texto: str) -> list[float]:
    """Un vector unitario estable derivado del texto.

    Unitario porque la distancia coseno de `pgvector` compara direcciones: sin normalizar, la
    similitud de dos vectores idénticos seguiría dando 1, pero los intermedios se moverían por
    la magnitud y no por el contenido.
    """
    crudo = bytearray()
    semilla = texto.encode("utf-8")
    contador = 0
    while len(crudo) < DIMENSION_DEL_VECTOR * 4:
        crudo += hashlib.sha256(semilla + contador.to_bytes(4, "big")).digest()
        contador += 1
    valores = [
        struct.unpack_from(">i", crudo, posicion * 4)[0] / 2**31
        for posicion in range(DIMENSION_DEL_VECTOR)
    ]
    norma = math.sqrt(sum(uno * uno for uno in valores)) or 1.0
    return [uno / norma for uno in valores]


__all__ = [
    "ConfiguracionDeMensajeria",
    "EmbeddingsSimulados",
    "MensajeriaSimulada",
    "MensajeriaWhatsApp",
    "SinCanal",
    "TranscriptorSimulado",
]
