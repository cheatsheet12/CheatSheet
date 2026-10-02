"""La pasarela simulada tiene que **recordar entre requests** para que las tres ramas se caminen.

`armar_pasarela` se llama por request. Con un doble nuevo en cada llamada, «rechazar» (que se
decide al crear el link), «demorar» (que se resuelve en «Actualizar estado», otro request) y la
misma clave de idempotencia entre T1 y T2 no se podrían demostrar en una laptop: cada request
empezaría de cero. El doble es de proceso; en producción se sigue negando a construirse.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.api.mercadopago import armar_pasarela
from cheatsheet.contexts.payments.infrastructure.pasarela_simulada import PasarelaSimulada
from cheatsheet.platform.settings import Entorno

from tests.conftest import settings_de_prueba


def _unidad() -> UnidadDeTrabajo:
    """Con el adaptador simulado la unidad no se toca: no hay token que resolver."""
    return cast(UnidadDeTrabajo, object())


def test_dos_requests_reciben_la_misma_pasarela_simulada() -> None:
    settings = settings_de_prueba()

    primera = armar_pasarela(_unidad(), settings)
    segunda = armar_pasarela(_unidad(), settings)

    assert isinstance(primera, PasarelaSimulada)
    assert primera is segunda


def test_la_pasarela_simulada_sigue_negandose_en_produccion() -> None:
    settings = replace(settings_de_prueba(), entorno=Entorno.PRODUCTION)

    with pytest.raises(RuntimeError):
        armar_pasarela(_unidad(), settings)
