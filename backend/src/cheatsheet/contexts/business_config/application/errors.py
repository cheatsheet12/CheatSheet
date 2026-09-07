"""Errores de `business_config`.

Derivan de `EntradaInvalida` y no de `InvarianteViolada`, y eso no es un accidente de la
herencia: `api/main.py` mapea el primero a **422 reenviando su texto**, y el segundo a un 409
genérico cuyo detalle el BFF descarta. Los mensajes de HU-E11-01 —«Los días de escalamiento
deben ser mayores a cero.»— son texto que la historia escribe para el usuario, así que tienen
que llegar a la pantalla.
"""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida


class ReglaInexistente(EntradaInvalida):
    """No es de esta empresa, o nunca existió. Bajo RLS son lo mismo."""


class ConfiguracionInvalida(EntradaInvalida):
    """La parametrizacion no tiene la forma que su tipo de regla exige (D24)."""


__all__ = ["ConfiguracionInvalida", "ReglaInexistente"]
