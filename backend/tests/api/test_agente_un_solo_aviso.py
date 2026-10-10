"""Pregunta 1 del Gate 1: una reserva o cancelación del agente produce **un solo** mensaje.

`ReservarTurno` y `CancelarTurno` avisan siempre al cliente. Cuando el que opera es el agente, la
confirmación ya sale en la conversación: un segundo aviso igual, seguido, parece un error. El
composition root le arma al agente un `Avisador` con un notificador que no envía; el panel sigue
avisando porque arma el suyo.

El test del mensaje único **de punta a punta** vive en `tests/integracion/test_api_conversacional.py`
(un mensaje saliente por paso, contra la base). Acá se fija la pieza: el notificador del agente.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.api.conversacional import _NotificadorSilencioso
from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso, PortNotificadorDeTurnos

pytestmark = pytest.mark.asyncio

DATOS = DatosDeAviso(
    cliente_id=uuid4(),
    telefono="5491112345678",
    nombre_del_cliente="Ana",
    servicio="Corte",
    recurso="Sillón 1",
    inicio=datetime(2026, 10, 14, 13, 30, tzinfo=UTC),
)


async def test_el_notificador_del_agente_no_manda_ni_guarda_nada() -> None:
    notificador: PortNotificadorDeTurnos = _NotificadorSilencioso()

    await notificador.avisar_reserva(DATOS)
    await notificador.avisar_cancelacion(DATOS)
    await notificador.avisar_reprogramacion(DATOS)

    # Sin estado: no hay dónde acumular un aviso que otro pudiera mandar después.
    assert vars(notificador) == {}
