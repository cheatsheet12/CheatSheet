"""Lo que Meta le notifica a la app, leído defensivamente por **campo** (U6).

Una notificación trae `entry[]`, y cada entrada trae `changes[]` con un `field` que dice de qué se
trata: `messages` (mensajes entrantes y estados de entrega) o `message_template_status_update`
(el estado de una plantilla). Este módulo sabe leer el segundo y los `statuses[]` del primero (U7).

**Todo campo se lee defensivamente.** El cuerpo lo manda un tercero: una forma inesperada tiene que
producir una lista vacía y un 200, no un 500 que Meta reintenta durante horas. Y **nada de lo que
trae se usa para decidir a qué empresa pertenece** salvo el `entry[].id`, el WABA id, que la raíz
resuelve contra `integrations`: la URL por la que llegó no decide nada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cheatsheet.contexts.business_config.domain.plantilla import (
    LARGO_MAXIMO_DETALLE,
    LARGO_MAXIMO_ID_EN_META,
    LARGO_MAXIMO_MOTIVO,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    LARGO_MAXIMO_MOTIVO_DE_FALLA,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.externo_id import LARGO_MAXIMO_EXTERNO_ID

logger = obtener_logger(__name__)

#: El campo de la suscripción de la app a Meta que trae el estado de una plantilla.
CAMPO_ESTADO_DE_PLANTILLA = "message_template_status_update"

#: Meta manda «NONE» cuando no hay motivo de rechazo.
SIN_MOTIVO = "NONE"

#: El campo que trae mensajes entrantes y callbacks de estado de entrega.
CAMPO_MENSAJES = "messages"

#: `status` de Meta → nuestro vocabulario (el valor de `EstadoEntrega` de los dos contextos).
#: `played` (una nota de voz reproducida) y lo que Meta agregue mañana se ignoran.
ESTADOS_DE_META = {
    "sent": "ENVIADO",
    "delivered": "ENTREGADO",
    "read": "LEIDO",
    "failed": "FALLIDO",
}


@dataclass(frozen=True, slots=True)
class EstadoDePlantillaNotificado:
    """Un `message_template_status_update`, en nuestro vocabulario."""

    waba_id: str
    evento: str
    meta_plantilla_id: str | None
    nombre: str | None
    idioma: str | None
    motivo: str | None
    detalle: str | None
    #: El `entry[].time` (epoch en segundos): cuándo lo dijo Meta. Sirve para no retroceder.
    momento: datetime | None


@dataclass(frozen=True, slots=True)
class EstadoDeEntregaNotificado:
    """Un `statuses[]` de Meta, en nuestro vocabulario.

    **Nada de `recipient_id`** (es un teléfono) ni del `title` del error (texto de un tercero): solo
    el `wamid`, el estado y el código. `estado` es el valor del `EstadoEntrega` de cada contexto;
    quien lo aplica lo convierte a su propio enum.
    """

    waba_id: str
    externo_id: str
    estado: str
    codigo_de_error: str | None


def cuerpo_de(crudo: bytes) -> dict[str, Any] | None:
    """El JSON de la notificación, o `None` si no es un objeto legible."""
    try:
        cuerpo = json.loads(crudo or b"{}")
    except (ValueError, TypeError):
        return None
    return cuerpo if isinstance(cuerpo, dict) else None


def estados_de_plantillas(cuerpo: dict[str, Any]) -> list[EstadoDePlantillaNotificado]:
    """Los cambios de estado de plantillas de la notificación. Lo que no se entiende se saltea."""
    encontrados: list[EstadoDePlantillaNotificado] = []
    for entrada in _objetos(cuerpo.get("entry")):
        waba_id = entrada.get("id")
        if not isinstance(waba_id, str) or not waba_id:
            continue
        momento = _momento(entrada.get("time"))
        for cambio in _objetos(entrada.get("changes")):
            if cambio.get("field") != CAMPO_ESTADO_DE_PLANTILLA:
                continue
            valor = cambio.get("value")
            if not isinstance(valor, dict):
                continue
            estado = _leer_estado(waba_id, momento, valor)
            if estado is not None:
                encontrados.append(estado)
    return encontrados


def estados_de_entrega(cuerpo: dict[str, Any]) -> list[EstadoDeEntregaNotificado]:
    """Los `statuses[]` de la notificación. Lo que no se entiende se saltea (nunca levanta).

    Un `id` demasiado largo se descarta en vez de cortarse: uno truncado coincidiría con otro
    mensaje. El `code` de `errors[0]` solo se lee en un `failed`.
    """
    encontrados: list[EstadoDeEntregaNotificado] = []
    for entrada in _objetos(cuerpo.get("entry")):
        waba_id = entrada.get("id")
        if not isinstance(waba_id, str) or not waba_id:
            continue
        for cambio in _objetos(entrada.get("changes")):
            valor = cambio.get("value")
            if cambio.get("field") != CAMPO_MENSAJES or not isinstance(valor, dict):
                continue
            for crudo in _objetos(valor.get("statuses")):
                leido = _leer_estado_de_entrega(waba_id, crudo)
                if leido is not None:
                    encontrados.append(leido)
    return encontrados


def _leer_estado_de_entrega(
    waba_id: str, crudo: dict[str, Any]
) -> EstadoDeEntregaNotificado | None:
    externo_id = crudo.get("id")
    status = crudo.get("status")
    if not isinstance(externo_id, str) or not externo_id:
        return None
    if len(externo_id) > LARGO_MAXIMO_EXTERNO_ID or not isinstance(status, str):
        return None
    estado = ESTADOS_DE_META.get(status)
    if estado is None:
        return None
    codigo = _codigo_de_error(crudo.get("errors")) if estado == "FALLIDO" else None
    return EstadoDeEntregaNotificado(
        waba_id=waba_id, externo_id=externo_id, estado=estado, codigo_de_error=codigo
    )


def _codigo_de_error(errores: Any) -> str | None:
    """El `code` de `errors[0]` como texto, o `None`. Un código largo se descarta, no se corta."""
    primero = _objetos(errores)[:1]
    if not primero:
        return None
    crudo = primero[0].get("code")
    if isinstance(crudo, bool):
        return None
    codigo = str(crudo) if isinstance(crudo, int) else _texto(crudo)
    if codigo is None or len(codigo) > LARGO_MAXIMO_MOTIVO_DE_FALLA:
        return None
    return codigo


def hay_mensajes(cuerpo: dict[str, Any]) -> bool:
    """Si la notificación trae **mensajes entrantes** (`messages[]`), no solo estados (`statuses[]`)."""
    return any(
        cambio.get("field") == CAMPO_MENSAJES
        and isinstance(cambio.get("value"), dict)
        and bool(_objetos(cambio["value"].get("messages")))
        for entrada in _objetos(cuerpo.get("entry"))
        for cambio in _objetos(entrada.get("changes"))
    )


def _leer_estado(
    waba_id: str, momento: datetime | None, valor: dict[str, Any]
) -> EstadoDePlantillaNotificado | None:
    evento = valor.get("event")
    if not isinstance(evento, str) or not evento:
        return None
    rechazo = valor.get("rejection_info")
    otro = valor.get("other_info")
    return EstadoDePlantillaNotificado(
        waba_id=waba_id,
        evento=evento,
        meta_plantilla_id=_identificador(valor.get("message_template_id")),
        nombre=_texto(valor.get("message_template_name")),
        idioma=_texto(valor.get("message_template_language")),
        motivo=_motivo(valor.get("reason"), rechazo),
        detalle=_detalle(rechazo, otro),
        momento=momento,
    )


def _identificador(crudo: Any) -> str | None:
    """Meta manda el id como número; se compara como texto, que es como lo guardamos."""
    if isinstance(crudo, bool):
        return None
    texto = str(crudo) if isinstance(crudo, int) else _texto(crudo)
    if texto is not None and len(texto) > LARGO_MAXIMO_ID_EN_META:
        # Un id nunca se corta: uno truncado coincidiría con la fila equivocada.
        logger.warning("plantilla_meta_id_demasiado_largo", largo=len(texto))
        return None
    return texto


def _texto(crudo: Any) -> str | None:
    return crudo if isinstance(crudo, str) and crudo else None


def _motivo(razon: Any, rechazo: Any) -> str | None:
    candidato = _texto(razon)
    if candidato is None and isinstance(rechazo, dict):
        candidato = _texto(rechazo.get("reason"))
    if candidato is None or candidato == SIN_MOTIVO:
        return None
    return candidato[:LARGO_MAXIMO_MOTIVO]


def _detalle(rechazo: Any, otro: Any) -> str | None:
    """La recomendación de Meta ante un rechazo, o la descripción de un aviso (`FLAGGED`)."""
    candidato = None
    if isinstance(rechazo, dict):
        candidato = _texto(rechazo.get("recommendation"))
    if candidato is None and isinstance(otro, dict):
        candidato = _texto(otro.get("description"))
    return candidato[:LARGO_MAXIMO_DETALLE] if candidato else None


def _momento(crudo: Any) -> datetime | None:
    """El `time` de la entrada, en segundos epoch. `None` si no se puede leer."""
    try:
        return datetime.fromtimestamp(int(crudo), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _objetos(valor: Any) -> list[dict[str, Any]]:
    if not isinstance(valor, list):
        return []
    return [uno for uno in valor if isinstance(uno, dict)]


__all__ = [
    "CAMPO_ESTADO_DE_PLANTILLA",
    "EstadoDeEntregaNotificado",
    "EstadoDePlantillaNotificado",
    "cuerpo_de",
    "estados_de_entrega",
    "estados_de_plantillas",
    "hay_mensajes",
]
