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
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

import httpx

from cheatsheet.contexts.conversational.application.errors import CanalNoConectado
from cheatsheet.contexts.conversational.application.ports import Transcripcion
from cheatsheet.contexts.conversational.domain.faq import DIMENSION_DEL_VECTOR
from cheatsheet.contexts.conversational.infrastructure.canal_http import Esperar, pedir_a_meta
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.externo_id import LARGO_MAXIMO_EXTERNO_ID

logger = obtener_logger(__name__)


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
        self.plantillas_enviadas: list[tuple[str, Mapping[str, str]]] = []

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, idioma
        self.plantillas_enviadas.append((nombre, dict(parametros)))
        logger.info("plantilla_simulada", nombre=nombre, parametros=len(parametros))
        return f"simulado-{uuid4()}"

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
    toda llamada externa. La política (transitorio / permanente / incierto) vive en
    `canal_http.py` y es la misma para el mensaje de texto, la plantilla y el cliente de
    plantillas.

    `esperar` se inyecta para que los tests no duerman. Las excepciones llevan el `error.code`
    de Meta; el log, `estado`, `codigo` y `fbtrace_id` y **nunca** `error.message`,
    `error_data`, el teléfono, el texto ni los parámetros.
    """

    def __init__(
        self,
        configuracion: ConfiguracionDeMensajeria,
        *,
        transporte: httpx.AsyncBaseTransport | None = None,
        esperar: Esperar = asyncio.sleep,
    ) -> None:
        self._config = configuracion
        self._transporte = transporte
        self._esperar = esperar

    async def enviar(self, *, telefono: str, texto: str) -> str:
        return await self._publicar(
            {
                "messaging_product": "whatsapp",
                "to": telefono,
                "type": "text",
                "text": {"body": texto},
            },
            objeto="el mensaje",
        )

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        """Una plantilla aprobada, con los parámetros **por nombre** (`parameter_name`)."""
        plantilla: dict[str, object] = {"name": nombre, "language": {"code": idioma}}
        if parametros:
            plantilla["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "parameter_name": clave, "text": valor}
                        for clave, valor in parametros.items()
                    ],
                }
            ]
        return await self._publicar(
            {
                "messaging_product": "whatsapp",
                "to": telefono,
                "type": "template",
                "template": plantilla,
            },
            objeto="la plantilla",
        )

    async def _publicar(self, cuerpo: Mapping[str, object], *, objeto: str) -> str:
        ruta = (
            f"{self._config.graph_url.rstrip('/')}/{self._config.graph_version}/"
            f"{self._config.phone_number_id}/messages"
        )
        async with httpx.AsyncClient(
            timeout=self._config.timeout_segundos, transport=self._transporte
        ) as cliente:
            respuesta = await pedir_a_meta(
                cliente,
                "POST",
                ruta,
                token=self._config.token,
                objeto=objeto,
                cuerpo=cuerpo,
                esperar=self._esperar,
            )
        return _id_del_mensaje(respuesta)


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

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        logger.info("whatsapp_sin_conectar_no_se_envia")
        raise CanalNoConectado("La empresa no conectó WhatsApp: el mensaje no se envió")


def _id_del_mensaje(respuesta: httpx.Response) -> str:
    """El `wamid` que Meta devuelve, o una cadena vacía si contestó algo raro o demasiado largo.

    Vacío y no una excepción: el mensaje **salió**. Perder el id significa no poder atar los
    callbacks de entrega a esa fila, que es peor que nada pero mucho mejor que tratar un envío
    exitoso como un fracaso.
    """
    try:
        mensajes = respuesta.json().get("messages", [])
        externo_id = str(mensajes[0]["id"]) if mensajes else ""
    except (ValueError, KeyError, IndexError, TypeError):
        logger.warning("whatsapp_respondio_sin_id")
        return ""
    if len(externo_id) > LARGO_MAXIMO_EXTERNO_ID:
        # Un id nunca se corta (uno truncado coincidiría con otro mensaje) y tampoco se loguea.
        logger.warning("whatsapp_id_de_mensaje_demasiado_largo", largo=len(externo_id))
        return ""
    return externo_id


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
