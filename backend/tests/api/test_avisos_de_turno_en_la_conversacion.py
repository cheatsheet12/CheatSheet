"""Los avisos de turno que dejan su rastro en la conversación del cliente (U7, casos 3, 24 y 25a).

El montaje (Meta falso, repositorios en memoria, escena de agenda) es el de los avisos de turno por
el canal real: `montaje_avisos_de_turno_reales.py`.
"""

from __future__ import annotations

import json

import httpx
import pytest
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoEntrega,
    OrigenDelMensaje,
)
from cheatsheet.contexts.conversational.infrastructure.canal import SinCanal
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno

from tests.api.montaje_avisos_de_turno_reales import (
    EnMemoria,
    Meta,
    canal_real,
    cancelar,
    escena_con_canal,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("hilos", "sin_plantillas_aprobadas"),
]


async def test_cancelar_un_turno_deja_el_aviso_en_la_conversacion_del_cliente(
    hilos: EnMemoria,
) -> None:
    """**Caso 3.** Antes el aviso salía y no dejaba ningún registro."""
    meta = Meta(httpx.Response(200, json={"messages": [{"id": "wamid.AVISO"}]}))
    escena, turno = escena_con_canal(canal_real(meta))

    await cancelar(escena, turno)

    (hilo,) = hilos.conversaciones.hilos.values()
    assert hilo.cliente_id == turno.cliente_id
    (aviso,) = hilos.mensajes.mensajes.values()
    assert (aviso.conversacion_id, aviso.origen) == (hilo.id, OrigenDelMensaje.SISTEMA)
    assert (aviso.externo_id, aviso.estado_entrega) == ("wamid.AVISO", EstadoEntrega.ENVIADO)
    assert aviso.contenido == json.loads(meta.pedidos[0].read())["text"]["body"]


async def test_meta_caido_deja_el_aviso_fallido_en_el_hilo_y_el_turno_cancelado(
    hilos: EnMemoria,
) -> None:
    """**Caso 24.** El operador ve el aviso `FALLIDO` con su motivo; el request no falla."""
    escena, turno = escena_con_canal(canal_real(Meta(httpx.Response(500))))

    cancelado = await cancelar(escena, turno)

    assert cancelado.estado is EstadoTurno.CANCELADO
    (aviso,) = hilos.mensajes.mensajes.values()
    assert aviso.estado_entrega is EstadoEntrega.FALLIDO
    assert aviso.motivo_de_falla == "SATURADA"
    assert aviso.externo_id is None


async def test_sin_whatsapp_conectado_no_se_crea_ni_hilo_ni_mensaje(hilos: EnMemoria) -> None:
    """**Caso 25a.** La empresa no usa el canal: la bandeja no se llena de avisos fallidos."""
    escena, turno = escena_con_canal(SinCanal())

    cancelado = await cancelar(escena, turno)

    assert cancelado.estado is EstadoTurno.CANCELADO
    assert hilos.conversaciones.hilos == {}
    assert hilos.mensajes.mensajes == {}
