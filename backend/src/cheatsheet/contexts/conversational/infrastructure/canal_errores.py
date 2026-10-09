"""Cómo se clasifica lo que contesta (o no contesta) la Cloud API de Meta (U5, H2).

Meta pide **manejar los errores por `error.code` y no por status HTTP**, y su documentación no
dice con qué status llega cada código (`docs/aidlc/TODO.md` §22.31 y §22.33). Por eso la
clasificación mira el código primero y el status sólo cuando el cuerpo no trae código.

Tres clases, que son las tres cosas distintas que puede hacer quien llama:

- **Transitorio**: el mensaje no se aceptó y reintentar tiene sentido (límites de tasa, Meta
  caída, sin conexión).
- **Permanente**: Meta contestó y no lo va a aceptar aunque se reintente (fuera de la ventana de
  24 h, número que no es de WhatsApp, token inválido). Reintentar es gastar el rate limit de la
  empresa contra un error propio.
- **Incierto**: el pedido pudo haber llegado y no se sabe (timeout de lectura, conexión cortada
  a mitad de respuesta). **No se reintenta**: la Cloud API no ofrece clave de idempotencia y un
  duplicado es peor que un mensaje que falta.

Nada de esto lee ni devuelve `error.message` ni `error_data.details`: pueden traer el número.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

#: Límites de tasa (4, 80007, 130429, 131056), desconocido (131000) y servicio no disponible
#: (131016): reintentables.
CODIGOS_TRANSITORIOS = frozenset({4, 80007, 130429, 131056, 131000, 131016})

#: Fuera de ventana (131047), no entregable (131026), plantilla inexistente o no aprobada
#: (132001), cantidad de parámetros (132000), formato de parámetro (132012), plantilla pausada
#: (132015) o deshabilitada (132016), 131048, 131049, 133010, 131042, 368, y token o permisos
#: (0, 3, 190): no se reintentan.
CODIGOS_PERMANENTES = frozenset(
    {
        131047,
        131026,
        132000,
        132001,
        132012,
        132015,
        132016,
        131048,
        131049,
        133010,
        131042,
        368,
        0,
        3,
        190,
    }
)

#: «Ya existe una plantilla con ese nombre en ese idioma». **Sin verificar contra Meta**
#: (`docs/aidlc/TODO.md` §22.44): si el subcódigo real es otro, el versionado del nombre no se
#: dispara y la plantilla queda `SIN_ENVIAR` con el texto de Meta a la vista.
SUBCODIGOS_NOMBRE_EN_USO = frozenset({2388023})

#: Tope del texto que Meta devuelve para el usuario: cabe en `detalle_meta` (500).
LARGO_MAXIMO_DEL_DETALLE = 500

#: El pedido ni siquiera salió: reintentar no puede duplicar nada.
FALLAS_SIN_SALIDA: tuple[type[httpx.HTTPError], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)


@dataclass(frozen=True, slots=True)
class ErrorDeMeta:
    """Lo único que se conserva de un error de Meta: nada que sea dato personal."""

    estado: int
    codigo: int | None
    fbtrace_id: str | None
    subcodigo: int | None = None
    #: `error_user_msg`: **solo** lo puebla el cliente de plantillas, donde Meta habla de nuestro
    #: texto y no de datos personales. Nunca va a un log.
    mensaje_para_el_usuario: str | None = None

    @property
    def es_transitorio(self) -> bool:
        """Por código primero; por status sólo si el cuerpo no trae un código conocido."""
        if self.codigo in CODIGOS_TRANSITORIOS:
            return True
        if self.codigo in CODIGOS_PERMANENTES:
            return False
        return self.estado >= 500 or self.estado == 429


def _entero(valor: object) -> int | None:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def leer_error(respuesta: httpx.Response, *, con_mensaje: bool = False) -> ErrorDeMeta:
    """`estado`, `error.code` y `fbtrace_id`. Un cuerpo ilegible da `codigo=None`.

    `con_mensaje=True` agrega `error_subcode` y `error_user_msg`: lo pide solo el cliente de
    plantillas. El de mensajes no lo pide porque ese texto puede traer el número.
    """
    try:
        error = respuesta.json()["error"]
        codigo = error.get("code")
        traza = error.get("fbtrace_id")
        subcodigo = error.get("error_subcode")
        mensaje = error.get("error_user_msg")
    except (ValueError, KeyError, TypeError, AttributeError):
        return ErrorDeMeta(estado=respuesta.status_code, codigo=None, fbtrace_id=None)
    return ErrorDeMeta(
        estado=respuesta.status_code,
        codigo=_entero(codigo),
        fbtrace_id=traza if isinstance(traza, str) else None,
        subcodigo=_entero(subcodigo) if con_mensaje else None,
        mensaje_para_el_usuario=(
            mensaje[:LARGO_MAXIMO_DEL_DETALLE] if con_mensaje and isinstance(mensaje, str) else None
        ),
    )


__all__ = [
    "CODIGOS_PERMANENTES",
    "CODIGOS_TRANSITORIOS",
    "FALLAS_SIN_SALIDA",
    "LARGO_MAXIMO_DEL_DETALLE",
    "SUBCODIGOS_NOMBRE_EN_USO",
    "ErrorDeMeta",
    "leer_error",
]
