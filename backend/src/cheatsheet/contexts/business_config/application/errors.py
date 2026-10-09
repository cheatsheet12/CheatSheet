"""Errores de `business_config`.

Derivan de `EntradaInvalida` y no de `InvarianteViolada`, y eso no es un accidente de la
herencia: `api/main.py` mapea el primero a **422 reenviando su texto**, y el segundo a un 409
genérico cuyo detalle el BFF descarta. Los mensajes de HU-E11-01 —«Los días de escalamiento
deben ser mayores a cero.»— son texto que la historia escribe para el usuario, así que tienen
que llegar a la pantalla.
"""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida, ErrorDeDominio


class ReglaInexistente(EntradaInvalida):
    """No es de esta empresa, o nunca existió. Bajo RLS son lo mismo."""


class ConfiguracionInvalida(EntradaInvalida):
    """La parametrizacion no tiene la forma que su tipo de regla exige (D24)."""


class MetaRechazoLaPlantilla(EntradaInvalida):
    """Meta contestó y no acepta el texto (U6). **Lleva el texto de Meta** para la pantalla.

    `EntradaInvalida` porque `api/main.py` la mapea a 422 reenviando el texto: lo que Meta dice de
    la plantilla (nuestro texto, no datos personales) tiene que llegar al administrador.
    `nombre_en_uso` es el caso que se arregla solo, con un nombre versionado.
    """

    def __init__(self, detalle: str, *, nombre_en_uso: bool = False) -> None:
        super().__init__(detalle or "Meta rechazó la plantilla.")
        self.nombre_en_uso = nombre_en_uso


class MetaNoDisponible(ErrorDeDominio):
    """Meta no contestó (transitorio, o tras un timeout de lectura). **No se guardó nada.**

    `incierto` distingue «no llegó» de «pudo haber llegado»: tras un timeout de lectura Meta puede
    haber aceptado la edición, y la conciliación detecta el texto divergente (D-U6-5). La API la
    mapea a 503.
    """

    def __init__(self, mensaje: str, *, incierto: bool = False) -> None:
        super().__init__(mensaje)
        self.incierto = incierto


class MetaNoConectada(ErrorDeDominio):
    """La empresa no conectó WhatsApp (o su credencial no se puede leer): no hay a quién mandarle."""


__all__ = [
    "ConfiguracionInvalida",
    "MetaNoConectada",
    "MetaNoDisponible",
    "MetaRechazoLaPlantilla",
    "ReglaInexistente",
]
