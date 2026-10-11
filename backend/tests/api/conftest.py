"""Fixtures de los tests de `api` que arman los avisos de turno con el canal real.

No son autouse: cada módulo que los necesita los pide con `usefixtures` (o como parámetro).
"""

from __future__ import annotations

import pytest
from cheatsheet.api.avisos_de_turno import CanalDeAvisosViaConversacion
from cheatsheet.contexts.conversational.application.notificaciones import NotificarAlCliente

from tests.api.montaje_avisos_de_turno_reales import EnMemoria, RelojFijo, SinPlantillas
from tests.contexts.conversational.application.dobles import sin_savepoint


@pytest.fixture
def hilos(monkeypatch: pytest.MonkeyPatch) -> EnMemoria:
    """`armar_canal_de_avisos` escribe en la base: acá se respalda con repositorios en memoria."""
    en_memoria = EnMemoria()
    monkeypatch.setattr(
        "cheatsheet.api.agenda.armar_canal_de_avisos",
        lambda _unidad, *, empresa_id, canal: CanalDeAvisosViaConversacion(
            NotificarAlCliente(
                conversaciones=en_memoria.conversaciones,
                mensajes=en_memoria.mensajes,
                mensajeria=canal,
                aislar=sin_savepoint,
            ),
            empresa_id=empresa_id,
            reloj=RelojFijo(),
        ),
    )
    return en_memoria


@pytest.fixture
def sin_plantillas_aprobadas(monkeypatch: pytest.MonkeyPatch) -> None:
    """`armar_plantillas_aprobadas` lee `business_config`: acá no hay base, y U5 no usa plantillas."""
    monkeypatch.setattr(
        "cheatsheet.api.agenda.armar_plantillas_aprobadas", lambda _u: SinPlantillas()
    )
    monkeypatch.setattr(
        "cheatsheet.api.mercadopago.armar_plantillas_aprobadas", lambda _u: SinPlantillas()
    )
