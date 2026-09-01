"""`cuit_desde` — la validación estructural, que bloquea siempre y no necesita red.

En un archivo aparte del resto del padrón por una razón mecánica: `test_padron.py` marca
el módulo entero con `pytest.mark.asyncio`, y estas tres pruebas son sincrónicas. Volver
async una prueba para que le entre una marca es peor que separarla.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.master_data.application.padron import MENSAJE_LARGO_INVALIDO, cuit_desde
from cheatsheet.shared.errors import EntradaInvalida

from tests.contexts.master_data.conftest import CUIT_DIGITO_MALO, CUIT_VALIDO


def test_normaliza_la_puntuacion() -> None:
    assert cuit_desde("30-71234567-1").valor == CUIT_VALIDO


def test_usa_el_mensaje_de_la_historia_para_el_largo() -> None:
    """El criterio de aceptación pide ese texto exacto, no el del Shared Kernel."""
    with pytest.raises(EntradaInvalida, match=MENSAJE_LARGO_INVALIDO):
        cuit_desde("3071234567")


def test_deja_pasar_el_mensaje_del_digito_verificador() -> None:
    """Un largo correcto con verificador malo no es «faltan digitos», y no lo dice."""
    with pytest.raises(EntradaInvalida, match="digito verificador"):
        cuit_desde(CUIT_DIGITO_MALO)
