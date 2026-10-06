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
#: (132001), 131048, 131049, 133010, 131042, 368, y token o permisos (0, 3, 190): no se reintentan.
CODIGOS_PERMANENTES = frozenset(
    {131047, 131026, 132001, 131048, 131049, 133010, 131042, 368, 0, 3, 190}
)

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

    @property
    def es_transitorio(self) -> bool:
        """Por código primero; por status sólo si el cuerpo no trae un código conocido."""
        if self.codigo in CODIGOS_TRANSITORIOS:
            return True
        if self.codigo in CODIGOS_PERMANENTES:
            return False
        return self.estado >= 500 or self.estado == 429


def leer_error(respuesta: httpx.Response) -> ErrorDeMeta:
    """`estado`, `error.code` y `fbtrace_id`. Un cuerpo ilegible da `codigo=None`."""
    try:
        error = respuesta.json()["error"]
        codigo = error.get("code")
        traza = error.get("fbtrace_id")
    except (ValueError, KeyError, TypeError, AttributeError):
        return ErrorDeMeta(estado=respuesta.status_code, codigo=None, fbtrace_id=None)
    return ErrorDeMeta(
        estado=respuesta.status_code,
        codigo=codigo if isinstance(codigo, int) and not isinstance(codigo, bool) else None,
        fbtrace_id=traza if isinstance(traza, str) else None,
    )


__all__ = [
    "CODIGOS_PERMANENTES",
    "CODIGOS_TRANSITORIOS",
    "FALLAS_SIN_SALIDA",
    "ErrorDeMeta",
    "leer_error",
]
