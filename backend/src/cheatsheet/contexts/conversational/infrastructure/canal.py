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

import hashlib
import math
import struct
from dataclasses import dataclass
from uuid import uuid4

import httpx

from cheatsheet.contexts.conversational.application.errors import MensajeriaNoDisponible
from cheatsheet.contexts.conversational.application.ports import Transcripcion
from cheatsheet.contexts.conversational.domain.faq import DIMENSION_DEL_VECTOR
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Cuántas veces se reintenta un envío. Dos reintentos sobre un 5xx alcanzan para un blip;
#: más sería tenerle a alguien el request abierto mientras Meta se recupera.
INTENTOS = 3


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

    Timeout explícito, reintento con backoff y manejo del fallo, como pide `CLAUDE.md` §5 para
    toda llamada externa. **Un 4xx no se reintenta**: un número mal formado o una plantilla no
    aprobada van a fallar igual las tres veces, y reintentarlas es gastar el rate limit de la
    empresa contra un error propio.
    """

    def __init__(
        self,
        configuracion: ConfiguracionDeMensajeria,
        *,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = configuracion
        self._transporte = transporte

    async def enviar(self, *, telefono: str, texto: str) -> str:
        cuerpo = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": texto},
        }
        ruta = (
            f"{self._config.graph_url.rstrip('/')}/{self._config.graph_version}/"
            f"{self._config.phone_number_id}/messages"
        )
        async with httpx.AsyncClient(
            timeout=self._config.timeout_segundos, transport=self._transporte
        ) as cliente:
            for intento in range(INTENTOS):
                respuesta = await cliente.post(
                    ruta,
                    json=cuerpo,
                    headers={"Authorization": f"Bearer {self._config.token}"},
                )
                if respuesta.status_code < 300:
                    return _id_del_mensaje(respuesta)
                if respuesta.status_code < 500:
                    # Nuestro error, no de ellos. Ver el docstring.
                    logger.warning("whatsapp_rechazo_el_mensaje", estado=respuesta.status_code)
                    raise MensajeriaNoDisponible(
                        f"WhatsApp rechazó el mensaje ({respuesta.status_code})"
                    )
                if intento < INTENTOS - 1:
                    logger.info("whatsapp_reintenta", intento=intento + 1)
        raise MensajeriaNoDisponible("WhatsApp no respondió")


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
    "TranscriptorSimulado",
]
