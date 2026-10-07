"""El webhook de WhatsApp (HS-T2, HS-T7).

**La segunda ruta del sistema sin sesión**, y la más expuesta: acá entra texto que escribió
cualquiera con el número de una empresa. Todo lo que sigue está escrito para eso.

Cuatro decisiones se ven en este archivo:

- **La verificación de Meta (`GET`) compara el token con `compare_digest`.** Es una comparación
  de secretos, y una comparación normal filtra información por el tiempo que tarda.

- **La firma del `POST` es HMAC-SHA256 sobre el cuerpo crudo**, con la misma forma que el
  webhook de MercadoPago del épico 6: **sin secreto configurado, ninguna firma valida**. Es lo
  contrario de lo cómodo y es a propósito — lo cómodo convierte un despliegue mal configurado
  en un endpoint público que le habla a los clientes de una empresa.

- **Una firma inválida se registra y contesta 200** (decisión D22, la misma). Un 401 le diría a
  Meta «reintentá», y reintentaría durante horas algo que nunca va a validar.

- **Un mensaje ya procesado contesta 200 sin hacer nada.** Meta reintenta por diseño; la
  garantía es el índice único de la migración 0021, y esta ruta sólo la traduce a un 200.

**Una segunda URL, la de la app (U6).** El estado de una plantilla (`message_template_status_update`)
no admite override por cuenta [WH-OVR]: llega a `/webhooks/whatsapp`, la URL de la app, y **se
rutea por el WABA id** del `entry[].id` contra `integrations`, nunca por la URL. La ruta por
empresa acepta el mismo campo (una instalación con la URL de la app apuntando a una empresa
funciona igual) y tampoco confía en su `{empresa_id}` para esto: un evento de la WABA de A que
entra por la URL de B actualiza a A. Una WABA desconocida —o con dos dueñas— se registra y
contesta 200.

**Nada de lo que Meta manda decide nada por sí solo.** El texto entra al clasificador como
dato delimitado, la salida del modelo pasa por un esquema cerrado, y ninguna acción real —
reservar, cancelar— se ejecuta desde el modelo: las hace el motor determinista de `scheduling`
(decisión D38).
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cheatsheet.api.conversacional import (
    armar_agenda,
    armar_directorio,
    armar_embeddings,
    armar_horario_de_atencion,
    armar_interprete,
    armar_transcriptor,
)
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.entregas import aplicar_estados_de_entrega
from cheatsheet.api.mensajeria import armar_mensajeria
from cheatsheet.api.whatsapp_notificaciones import (
    EstadoDePlantillaNotificado,
    cuerpo_de,
    estados_de_entrega,
    estados_de_plantillas,
    hay_mensajes,
)
from cheatsheet.contexts.business_config.application.plantillas import ActualizarEstadoDesdeMeta
from cheatsheet.contexts.business_config.infrastructure.ensamblado import ConfiguracionDeNegocio
from cheatsheet.contexts.conversational.application.agente import ProcesarMensajeEntrante
from cheatsheet.contexts.conversational.application.errors import MensajeYaProcesado
from cheatsheet.contexts.conversational.application.ports import MensajeEntrante
from cheatsheet.contexts.conversational.infrastructure.ensamblado import Conversaciones
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    empresas_de_la_cuenta_de_whatsapp,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from fastapi import APIRouter, Query, Request, Response, status

logger = obtener_logger(__name__)

#: La cabecera con la que Meta firma: `sha256=<hex>`.
CABECERA_FIRMA = "x-hub-signature-256"
PREFIJO_DE_FIRMA = "sha256="

#: Con qué identidad actúa el agente. **Ninguna: el agente es el sistema.**
#:
#: La primera versión de este módulo le inventaba un UUID fijo, y la bitácora lo rechazó con
#: una violación de clave foránea — correctamente: `registro_de_auditoria.usuario_id` apunta a
#: `usuario`, y un id que no corresponde a ninguna persona no tiene lugar ahí.
#:
#: Lo que separa al agente de un barrido de Beat no es un usuario falso: es el **iniciador**
#: (`Iniciador.IA`), que la migración 0021 agregó a la bitácora justamente para eso. Es la
#: pregunta que alguien se hace después de una conversación rara, y ahora tiene respuesta sin
#: necesidad de una fila que miente.
USUARIO_DEL_AGENTE: UsuarioId | None = None


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["conversational"])
    router.include_router(_rutas_de_la_app(recursos), prefix="/webhooks/whatsapp")
    router.include_router(_rutas(recursos), prefix="/webhooks/whatsapp")
    return router


def _verificacion(recursos: Recursos, modo: str, token: str, desafio: str) -> Response:
    """El handshake de Meta al registrar una URL, la de la app o la de una empresa.

    Devuelve el `challenge` en texto plano si el token coincide, y **404 si no**: un 401
    le confirmaría a quien prueba tokens que la URL existe y que el token estaba cerca.
    """
    esperado = recursos.settings.whatsapp_webhook_verify_token
    if modo == "subscribe" and esperado and hmac.compare_digest(token, esperado):
        return Response(content=desafio, media_type="text/plain")
    logger.warning("whatsapp_verificacion_rechazada")
    return Response(status_code=status.HTTP_404_NOT_FOUND)


def _rutas_de_la_app(recursos: Recursos) -> APIRouter:
    """La URL de la **app** (U6): sin empresa, para lo que Meta no deja redirigir por cuenta."""
    router = APIRouter()

    @router.get("")
    async def verificar_la_app(
        modo: str = Query(alias="hub.mode", default=""),
        token: str = Query(alias="hub.verify_token", default=""),
        desafio: str = Query(alias="hub.challenge", default=""),
    ) -> Response:
        """La verificación de la **URL de la app** (U6): la misma comparación que la de empresa."""
        return _verificacion(recursos, modo, token, desafio)

    @router.post("", status_code=status.HTTP_200_OK)
    async def recibir_en_la_app(request: Request) -> Response:
        """El estado de las plantillas llega acá: la URL de la app no tiene empresa.

        Misma firma HMAC con el App Secret; **siempre 200** salvo que algo nuestro se rompa. Los
        mensajes entrantes no se procesan en esta ruta (no hay empresa a quién atribuirlos): si
        llegan, se anota y se contesta 200.
        """
        crudo = await request.body()
        if not _firma_valida(crudo, request.headers.get(CABECERA_FIRMA, ""), recursos):
            logger.warning("whatsapp_firma_invalida", empresa="app")
            return Response(status_code=status.HTTP_200_OK)
        cuerpo = cuerpo_de(crudo)
        if cuerpo is None:
            logger.warning("whatsapp_cuerpo_ilegible")
            return Response(status_code=status.HTTP_200_OK)
        if hay_mensajes(cuerpo):
            logger.warning("whatsapp_mensajes_en_la_url_de_la_app")
        await _aplicar_estados_de_plantillas(recursos, estados_de_plantillas(cuerpo))
        await aplicar_estados_de_entrega(recursos, estados_de_entrega(cuerpo))
        return Response(status_code=status.HTTP_200_OK)

    return router


def _rutas(recursos: Recursos) -> APIRouter:
    router = APIRouter()

    @router.get("/{empresa_id}")
    async def verificar(
        empresa_id: UUID,
        modo: str = Query(alias="hub.mode", default=""),
        token: str = Query(alias="hub.verify_token", default=""),
        desafio: str = Query(alias="hub.challenge", default=""),
    ) -> Response:
        """El handshake de Meta al registrar la URL de una empresa."""
        del empresa_id
        return _verificacion(recursos, modo, token, desafio)

    @router.post("/{empresa_id}", status_code=status.HTTP_200_OK)
    async def recibir(request: Request, empresa_id: UUID) -> Response:
        """Recibe un mensaje entrante y lo procesa (HS-T2).

        **Siempre 200**, salvo que algo nuestro se rompa. Una firma inválida, un mensaje
        repetido o una notificación que no trae mensajes son todos caminos previstos, y los
        tres significan lo mismo para Meta: recibido, no reintentes.
        """
        crudo = await request.body()
        if not _firma_valida(crudo, request.headers.get(CABECERA_FIRMA, ""), recursos):
            # D22: se registra y se contesta 200. Ver el docstring del módulo.
            logger.warning("whatsapp_firma_invalida", empresa=str(empresa_id))
            return Response(status_code=status.HTTP_200_OK)

        # El estado de una plantilla y los callbacks de entrega se rutean por la WABA, no por
        # `empresa_id` (ver el docstring).
        cuerpo = cuerpo_de(crudo)
        if cuerpo is not None:
            await _aplicar_estados_de_plantillas(recursos, estados_de_plantillas(cuerpo))
            await aplicar_estados_de_entrega(
                recursos, estados_de_entrega(cuerpo), empresa_de_la_url=EmpresaId(empresa_id)
            )

        entrantes = _mensajes_de(crudo)
        if not entrantes:
            # Meta manda también callbacks de estado de entrega y notificaciones de sistema.
            # No traer mensajes no es un error: es la mayoría del tráfico.
            return Response(status_code=status.HTTP_200_OK)

        empresa = EmpresaId(empresa_id)
        for entrante in entrantes:
            await _procesar(recursos, empresa, entrante)
        return Response(status_code=status.HTTP_200_OK)

    return router


async def _aplicar_estados_de_plantillas(
    recursos: Recursos, estados: list[EstadoDePlantillaNotificado]
) -> None:
    """Un cambio por transacción, en la empresa **dueña de la WABA** (nunca la de la URL).

    La resolución de la empresa es una lectura entre empresas (`SECURITY DEFINER`, solo ids). Una
    WABA sin dueña, o con dos, no se adivina: se registra y se sigue. Lo que sí se rompa de nuestro
    lado sube como 500, y Meta reintenta: aplicar el mismo estado dos veces es un solo efecto.
    """
    for estado in estados:
        async with sesion_sin_empresa(recursos.sesiones) as sesion:
            duenas = await empresas_de_la_cuenta_de_whatsapp(sesion, estado.waba_id)
        if len(duenas) != 1:
            logger.warning("plantilla_de_waba_sin_una_sola_empresa", empresas=len(duenas))
            continue
        async for unidad in unidad_de_trabajo(recursos, duenas[0]):
            plantillas = ConfiguracionDeNegocio.armar(unidad).plantillas
            await ActualizarEstadoDesdeMeta(plantillas).ejecutar(
                estado=estado.evento,
                momento=estado.momento or unidad.reloj.ahora(),
                es_evento=True,
                meta_plantilla_id=estado.meta_plantilla_id,
                nombre=estado.nombre,
                idioma=estado.idioma,
                motivo=estado.motivo,
                detalle=estado.detalle,
            )


async def _procesar(recursos: Recursos, empresa: EmpresaId, entrante: MensajeEntrante) -> None:
    """Una transacción por mensaje.

    Por mensaje y no por notificación: si el segundo falla, el primero ya quedó procesado y su
    reintento lo encuentra por `externo_id`. Una transacción para todo el lote haría que un
    fallo obligara a reprocesar mensajes que ya habían salido bien.
    """
    async for unidad in unidad_de_trabajo(recursos, empresa):
        piezas = Conversaciones.armar(unidad)
        caso = ProcesarMensajeEntrante(
            conversaciones=piezas.conversaciones,
            mensajes=piezas.mensajes,
            escalamientos=piezas.escalamientos,
            faqs=piezas.faqs,
            usos=piezas.usos,
            clientes=armar_directorio(
                unidad,
                recursos.settings,
                empresa_id=empresa,
                usuario_id=USUARIO_DEL_AGENTE,
            ),
            interprete=armar_interprete(recursos.settings),
            transcriptor=armar_transcriptor(recursos.settings),
            mensajeria=await armar_mensajeria(unidad, recursos.settings, empresa_id=empresa),
            embeddings=armar_embeddings(),
            agenda=armar_agenda(unidad, empresa_id=empresa, usuario_id=USUARIO_DEL_AGENTE),
            horario=armar_horario_de_atencion(unidad, empresa_id=empresa),
            publicador=unidad.publicador,
        )
        try:
            await caso.ejecutar(empresa_id=empresa, entrante=entrante, ahora=unidad.reloj.ahora())
        except MensajeYaProcesado:
            # La garantía funcionando. No es un error: Meta reintentó.
            logger.info("whatsapp_mensaje_repetido")


def _firma_valida(crudo: bytes, cabecera: str, recursos: Recursos) -> bool:
    """HMAC-SHA256 sobre el cuerpo crudo, comparado en tiempo constante.

    **Sin secreto configurado devuelve `False` siempre.** Ver el docstring del módulo.
    """
    secreto = recursos.settings.whatsapp_webhook_secret
    if not secreto or not cabecera.startswith(PREFIJO_DE_FIRMA):
        return False
    esperada = hmac.new(secreto.encode("utf-8"), crudo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(cabecera[len(PREFIJO_DE_FIRMA) :], esperada)


def _mensajes_de(crudo: bytes) -> list[MensajeEntrante]:
    """Traduce la notificación de Meta al vocabulario de este sistema.

    **Todo campo se lee defensivamente.** El cuerpo lo manda un tercero: una forma inesperada
    tiene que producir una lista vacía y un 200, no un 500 que Meta reintenta durante horas.

    Los `statuses` —los callbacks de entrega y lectura— los procesa `api/entregas.py` (U7).
    """
    import json

    try:
        cuerpo = json.loads(crudo or b"{}")
    except (ValueError, TypeError):
        logger.warning("whatsapp_cuerpo_ilegible")
        return []
    if not isinstance(cuerpo, dict):
        return []

    encontrados: list[MensajeEntrante] = []
    for entrada in _lista(cuerpo.get("entry")):
        for cambio in _lista(entrada.get("changes")):
            valor = cambio.get("value")
            if not isinstance(valor, dict):
                continue
            for mensaje in _lista(valor.get("messages")):
                traducido = _traducir(mensaje)
                if traducido is not None:
                    encontrados.append(traducido)
    return encontrados


def _lista(valor: Any) -> list[dict[str, Any]]:
    if not isinstance(valor, list):
        return []
    return [uno for uno in valor if isinstance(uno, dict)]


def _traducir(mensaje: dict[str, Any]) -> MensajeEntrante | None:
    externo_id = mensaje.get("id")
    telefono = mensaje.get("from")
    if not isinstance(externo_id, str) or not isinstance(telefono, str):
        # Sin id no hay idempotencia y sin número no hay a quién contestarle. Los dos hacen
        # que el mensaje sea imposible de procesar, no que el sistema esté roto.
        return None

    texto = None
    cuerpo = mensaje.get("text")
    if isinstance(cuerpo, dict) and isinstance(cuerpo.get("body"), str):
        texto = cuerpo["body"]

    audio_id = None
    audio = mensaje.get("audio")
    if isinstance(audio, dict) and isinstance(audio.get("id"), str):
        audio_id = audio["id"]

    if texto is None and audio_id is None:
        # Una imagen, un sticker, una ubicación. El sistema no los interpreta todavía; están
        # en los pendientes del épico.
        return None

    return MensajeEntrante(
        externo_id=externo_id,
        telefono=telefono,
        texto=texto,
        audio_id=audio_id,
        momento=_momento(mensaje.get("timestamp")),
    )


def _momento(crudo: Any) -> datetime | None:
    """El `timestamp` de Meta, que viene como segundos epoch en una cadena.

    `None` cuando no se puede leer, y el caso de uso usa el reloj de la unidad: una hora
    inventada es peor que una hora aproximada.
    """
    try:
        return datetime.fromtimestamp(int(crudo), tz=UTC)
    except (TypeError, ValueError):
        return None


__all__ = ["USUARIO_DEL_AGENTE", "crear_router"]
