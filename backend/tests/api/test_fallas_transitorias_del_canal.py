"""La raíz marca qué fallas del canal son transitorias (U7, tramo ii, D-U7-3).

Solo `MensajeriaSaturada` (5xx, 429 o throttling tras los intentos del canal) vale un nuevo
intento. `MensajeRechazado` es un 4xx de Meta que no va a cambiar; `EnvioIncierto` es un timeout de
lectura (Meta pudo haberlo aceptado y no hay clave de idempotencia); `CanalNoConectado` no tocó la
red y tampoco se arregla esperando.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from cheatsheet.api.fallas_de_canal import CanalConFallasTraducidas
from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaSaturada,
)
from cheatsheet.contexts.payments.application.ports_envio import FallaDelCanal


class _Canal:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        raise self._error

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        raise self._error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "transitoria"),
    [
        (MensajeriaSaturada("no"), True),
        # Un código de Meta no dice si es transitorio: lo dice la clase del error.
        (MensajeriaSaturada("no", codigo=131056), True),
        (MensajeRechazado("no", codigo=131056), False),
        (MensajeRechazado("no", codigo=131026), False),
        (EnvioIncierto("no"), False),
        (CanalNoConectado("no"), False),
    ],
)
async def test_solo_la_saturacion_es_transitoria(error: Exception, transitoria: bool) -> None:
    canal = CanalConFallasTraducidas(_Canal(error), FallaDelCanal)

    with pytest.raises(FallaDelCanal) as texto:
        await canal.enviar(telefono="1", texto="hola")
    with pytest.raises(FallaDelCanal) as plantilla:
        await canal.enviar_plantilla(telefono="1", nombre="n", idioma="es_AR", parametros={})

    assert texto.value.transitoria is transitoria
    assert plantilla.value.transitoria is transitoria


def test_una_falla_es_permanente_salvo_que_se_diga_otra_cosa() -> None:
    assert FallaDelCanal("131026").transitoria is False
