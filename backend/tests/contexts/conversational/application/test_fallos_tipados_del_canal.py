"""Regresión (U5, caso 31): los fallos tipados del canal no cambian a quien ya los atrapaba.

`SalidaAlCliente` (que usan el agente y `fuera_de_horario`) guarda el saliente `FALLIDO` ante
cualquier excepción del canal, y el operador lo convierte en `MensajeriaNoDisponible`. Las
excepciones nuevas **heredan de `MensajeriaNoDisponible`**, así que ninguno de los dos cambia.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaNoDisponible,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.domain.conversacion import Conversacion, EstadoEntrega
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

from .dobles import RepositorioMensajeEnMemoria

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
TIPADAS = [MensajeRechazado, MensajeriaSaturada, EnvioIncierto, CanalNoConectado]


class CanalQueFalla:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        raise self._error


@pytest.mark.parametrize("clase", TIPADAS)
async def test_el_agente_guarda_fallido_y_no_levanta(clase: type[MensajeriaNoDisponible]) -> None:
    mensajes = RepositorioMensajeEnMemoria()
    salida = SalidaAlCliente(mensajes=mensajes, mensajeria=CanalQueFalla(clase("no salió")))
    hilo = Conversacion(id=uuid4(), empresa_id=EMPRESA, cliente_id=uuid4(), created_at=AHORA)

    resultado = await salida.responder(EMPRESA, hilo, "5491112345678", "Hola", AHORA)

    assert resultado is None
    (guardado,) = mensajes.salientes
    assert guardado.estado_entrega is EstadoEntrega.FALLIDO
    assert guardado.externo_id is None


@pytest.mark.parametrize("clase", TIPADAS)
def test_las_tipadas_siguen_siendo_mensajeria_no_disponible_y_entrada_invalida(
    clase: type[MensajeriaNoDisponible],
) -> None:
    # `api/main.py` mapea `EntradaInvalida` a 422 reenviando el texto: el operador sigue
    # recibiendo lo mismo con las subclases.
    assert issubclass(clase, MensajeriaNoDisponible)
    assert issubclass(clase, EntradaInvalida)
