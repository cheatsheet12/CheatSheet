"""`RegistrarEstadoDeEntrega`: lo que Meta dice de un mensaje del agente o del operador (U7).

Casos 1, 5, 6, 7, 8 y 13 en su capa de caso de uso: un callback `statuses[]` encuentra el mensaje
por su `wamid`, lo mueve sin retroceder y es idempotente.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.application.entregas import RegistrarEstadoDeEntrega
from cheatsheet.contexts.conversational.domain.conversacion import (
    DireccionMensaje,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.shared.empresa import EmpresaId

from .dobles import RepositorioMensajeEnMemoria

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


def _saliente(
    externo_id: str = "wamid-1", origen: OrigenDelMensaje = OrigenDelMensaje.AGENTE
) -> Mensaje:
    return Mensaje(
        id=uuid4(),
        conversacion_id=uuid4(),
        empresa_id=EMPRESA,
        direccion=DireccionMensaje.SALIENTE,
        tipo_contenido=TipoContenido.TEXTO,
        contenido="hola",
        momento=AHORA,
        origen=origen,
        estado_entrega=EstadoEntrega.ENVIADO,
        externo_id=externo_id,
    )


class _RepositorioQueCuentaGuardados(RepositorioMensajeEnMemoria):
    def __init__(self, *mensajes: Mensaje) -> None:
        super().__init__(*mensajes)
        self.guardados = 0

    async def guardar(self, mensaje: Mensaje) -> None:
        self.guardados += 1
        await super().guardar(mensaje)


@pytest.mark.parametrize("origen", [OrigenDelMensaje.AGENTE, OrigenDelMensaje.OPERADOR])
async def test_delivered_mueve_el_mensaje_a_entregado(origen: OrigenDelMensaje) -> None:
    mensaje = _saliente(origen=origen)
    caso = RegistrarEstadoDeEntrega(RepositorioMensajeEnMemoria(mensaje))

    encontrado = await caso.ejecutar(externo_id="wamid-1", estado=EstadoEntrega.ENTREGADO)

    assert encontrado is True
    assert mensaje.estado_entrega is EstadoEntrega.ENTREGADO


async def test_un_wamid_desconocido_devuelve_falso_y_no_levanta() -> None:
    caso = RegistrarEstadoDeEntrega(RepositorioMensajeEnMemoria(_saliente()))

    assert await caso.ejecutar(externo_id="otro", estado=EstadoEntrega.LEIDO) is False


async def test_el_mismo_callback_dos_veces_es_un_solo_cambio() -> None:
    mensaje = _saliente()
    mensajes = _RepositorioQueCuentaGuardados(mensaje)
    caso = RegistrarEstadoDeEntrega(mensajes)

    await caso.ejecutar(externo_id="wamid-1", estado=EstadoEntrega.ENTREGADO)
    encontrado = await caso.ejecutar(externo_id="wamid-1", estado=EstadoEntrega.ENTREGADO)

    assert encontrado is True  # existe: no es un «sin destinatario»
    assert mensajes.guardados == 1


async def test_delivered_despues_de_read_no_retrocede() -> None:
    mensaje = _saliente()
    caso = RegistrarEstadoDeEntrega(RepositorioMensajeEnMemoria(mensaje))

    await caso.ejecutar(externo_id="wamid-1", estado=EstadoEntrega.LEIDO)
    await caso.ejecutar(externo_id="wamid-1", estado=EstadoEntrega.ENTREGADO)

    assert mensaje.estado_entrega is EstadoEntrega.LEIDO


async def test_failed_guarda_el_codigo_de_meta_y_es_terminal() -> None:
    mensaje = _saliente()
    caso = RegistrarEstadoDeEntrega(RepositorioMensajeEnMemoria(mensaje))

    await caso.ejecutar(
        externo_id="wamid-1", estado=EstadoEntrega.FALLIDO, codigo_de_error="131047"
    )
    await caso.ejecutar(externo_id="wamid-1", estado=EstadoEntrega.LEIDO)

    assert mensaje.estado_entrega is EstadoEntrega.FALLIDO
    assert mensaje.motivo_de_falla == "131047"
