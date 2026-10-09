"""El `wamid` del envío que no sirve se guarda como «sin id» en el mensaje saliente (U7, H3).

Un id vacío (Meta contestó algo raro) o más largo que `mensaje.externo_id` no puede llegar a la
base: la fila fallaría (`varchar(160)`) o, con `""`, ocuparía el lugar de otro en la idempotencia.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.domain.conversacion import Conversacion
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.externo_id import LARGO_MAXIMO_EXTERNO_ID

from .dobles import RepositorioMensajeEnMemoria

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
INVALIDOS = [
    pytest.param("", id="vacio"),
    pytest.param("w" * (LARGO_MAXIMO_EXTERNO_ID + 1), id="demasiado-largo"),
]


class _CanalConId:
    def __init__(self, externo_id: str) -> None:
        self._externo_id = externo_id

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        return self._externo_id


@pytest.mark.parametrize("externo_id", INVALIDOS)
async def test_el_agente_guarda_el_saliente_sin_id_si_el_wamid_no_sirve(externo_id: str) -> None:
    mensajes = RepositorioMensajeEnMemoria()
    salida = SalidaAlCliente(mensajes=mensajes, mensajeria=_CanalConId(externo_id))  # type: ignore[arg-type]
    hilo = Conversacion(id=uuid4(), empresa_id=EMPRESA, cliente_id=uuid4(), created_at=AHORA)

    await salida.responder(EMPRESA, hilo, "5491112345678", "Hola", AHORA)

    (guardado,) = mensajes.salientes
    assert guardado.externo_id is None


async def test_el_agente_conserva_un_wamid_valido() -> None:
    mensajes = RepositorioMensajeEnMemoria()
    salida = SalidaAlCliente(mensajes=mensajes, mensajeria=_CanalConId("wamid.OK"))  # type: ignore[arg-type]
    hilo = Conversacion(id=uuid4(), empresa_id=EMPRESA, cliente_id=uuid4(), created_at=AHORA)

    await salida.responder(EMPRESA, hilo, "5491112345678", "Hola", AHORA)

    (guardado,) = mensajes.salientes
    assert guardado.externo_id == "wamid.OK"
