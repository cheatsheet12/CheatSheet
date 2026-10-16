"""El aviso al cliente cuando MercadoPago aprueba un cobro (HU-E8-04 RN-01), por el webhook real.

Se prueba el router completo con repositorios en memoria y Meta falso. Lo que se defiende:

- **un solo aviso por pago**: la notificación repetida corta en `buscar_por_payment_id`;
- **el aviso sale después del commit del pago**, en una unidad de trabajo aparte;
- **solo avisa lo aprobado ahora**: ni lo repetido, ni lo huérfano, ni lo pendiente;
- **nada del aviso voltea el pago**: el webhook contesta 200 aunque Meta o el armado del canal fallen.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from cheatsheet.api import avisos_de_cobro
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoEntrega,
    OrigenDelMensaje,
)
from cheatsheet.contexts.conversational.infrastructure.canal import SinCanal
from cheatsheet.contexts.payments.domain.cobro import EstadoCobro
from structlog.testing import capture_logs

from tests.api.montaje_webhook_aviso_de_pago import (
    AHORA,
    EMPRESA,
    NOMBRE,
    TELEFONO,
    WAMID,
    Montaje,
    montar,
    notificar,
    un_cobro,
)
from tests.logs import logs_capturables

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _logger_que_captura_logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Los tests de este archivo miran logs: que no dependan de qué corrió antes."""
    yield from logs_capturables(monkeypatch, avisos_de_cobro)


def _texto_enviado(montaje: Montaje) -> str:
    (pedido,) = montaje.meta.pedidos
    return str(json.loads(pedido.read())["text"]["body"])


async def test_pago_aprobado_avisa_al_cliente_una_vez(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = await montar(monkeypatch)

    respuesta = await notificar(montaje)

    assert respuesta.status_code == 200
    (cobro,) = montaje.cobros.guardados.values()
    assert cobro.estado is EstadoCobro.APROBADO
    assert _texto_enviado(montaje) == (
        f"Hola {NOMBRE}, recibimos tu pago de Consulta de septiembre por $ 1.210,00. ¡Gracias!"
    )
    (pedido,) = montaje.meta.pedidos
    assert json.loads(pedido.read())["to"] == TELEFONO


async def test_el_aviso_queda_en_el_hilo_como_sistema_con_su_wamid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)

    await notificar(montaje)

    (cobro,) = montaje.cobros.guardados.values()
    (hilo,) = montaje.hilos.conversaciones.hilos.values()
    assert hilo.cliente_id == cobro.cliente_id
    (aviso,) = montaje.hilos.mensajes.mensajes.values()
    assert (aviso.conversacion_id, aviso.origen) == (hilo.id, OrigenDelMensaje.SISTEMA)
    assert (aviso.externo_id, aviso.estado_entrega) == (WAMID, EstadoEntrega.ENVIADO)
    assert aviso.contenido == _texto_enviado(montaje)


async def test_el_aviso_sale_despues_del_commit_del_pago(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = await montar(monkeypatch)

    await notificar(montaje)

    # Cuando se llamó a Meta, la unidad del pago ya había confirmado; la del aviso, todavía no.
    assert montaje.confirmadas_al_llamar_a_meta == [1]
    assert montaje.confirmadas == ["unidad", "unidad"]


async def test_webhook_repetido_no_vuelve_a_avisar(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = await montar(monkeypatch)

    primera = await notificar(montaje)
    segunda = await notificar(montaje)

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert len(montaje.meta.pedidos) == 1
    assert len(montaje.hilos.mensajes.mensajes) == 1


async def test_el_aviso_sale_por_el_canal_de_la_empresa_de_la_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)

    await notificar(montaje)

    assert montaje.canales_de == [EMPRESA]


async def test_la_sena_de_un_turno_avisa_igual(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = await montar(monkeypatch, con_cobro=un_cobro(turno_id=uuid4(), monto="5000.00"))

    await notificar(montaje)

    assert "por $ 5.000,00." in _texto_enviado(montaje)


async def test_pago_huerfano_no_avisa(monkeypatch: pytest.MonkeyPatch) -> None:
    cancelado = un_cobro()
    cancelado.cancelar(motivo="El cliente desistio de la compra", ahora=AHORA)
    montaje = await montar(monkeypatch, con_cobro=cancelado)

    respuesta = await notificar(montaje)

    assert respuesta.status_code == 200
    assert montaje.meta.pedidos == []
    assert montaje.canales_de == []


@pytest.mark.parametrize("estado", ["pending", "in_process", "rejected"])
async def test_pago_no_aprobado_no_avisa(monkeypatch: pytest.MonkeyPatch, estado: str) -> None:
    montaje = await montar(monkeypatch, estado_del_pago=estado)

    respuesta = await notificar(montaje)

    assert respuesta.status_code == 200
    assert montaje.meta.pedidos == []
    (cobro,) = montaje.cobros.guardados.values()
    assert cobro.estado is EstadoCobro.PENDIENTE


async def test_cliente_sin_telefono_no_avisa_y_el_pago_queda_aprobado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch, contacto=None)

    respuesta = await notificar(montaje)

    assert respuesta.status_code == 200
    assert montaje.meta.pedidos == []
    (cobro,) = montaje.cobros.guardados.values()
    assert cobro.estado is EstadoCobro.APROBADO


async def test_falla_del_canal_no_voltea_el_pago_y_contesta_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch, httpx.Response(400, json={"error": {"code": 131047}}))

    respuesta = await notificar(montaje)

    assert respuesta.status_code == 200
    (cobro,) = montaje.cobros.guardados.values()
    assert cobro.estado is EstadoCobro.APROBADO
    (aviso,) = montaje.hilos.mensajes.mensajes.values()
    assert aviso.estado_entrega is EstadoEntrega.FALLIDO


async def test_un_fallo_inesperado_del_aviso_no_voltea_el_pago_ni_filtra_datos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)
    montaje.falla_al_armar_el_canal = RuntimeError(f"se rompio algo con {TELEFONO}")

    with capture_logs() as registros:
        respuesta = await notificar(montaje)

    assert respuesta.status_code == 200
    (cobro,) = montaje.cobros.guardados.values()
    assert cobro.estado is EstadoCobro.APROBADO
    assert montaje.meta.pedidos == []
    fallidos = [r for r in registros if r["event"] == "aviso_de_pago_fallido"]
    assert [r["causa"] for r in fallidos] == ["RuntimeError"]
    assert TELEFONO not in str(registros)
    assert NOMBRE not in str(registros)


async def test_la_empresa_sin_whatsapp_conectado_no_deja_hilo_ni_mensaje(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)

    async def sin_canal(*_: object, **__: object) -> SinCanal:
        return SinCanal()

    monkeypatch.setattr("cheatsheet.api.avisos_de_cobro.armar_mensajeria", sin_canal)

    respuesta = await notificar(montaje)

    assert respuesta.status_code == 200
    assert montaje.hilos.conversaciones.hilos == {}
    assert montaje.hilos.mensajes.mensajes == {}


async def test_un_canal_lento_vence_el_plazo_del_aviso_y_el_webhook_sigue_en_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)
    monkeypatch.setattr("cheatsheet.api.avisos_de_cobro.PLAZO_DEL_AVISO_EN_SEGUNDOS", 0.05)

    async def canal_lento(*_: object, **__: object) -> object:
        await asyncio.sleep(30)  # la prueba no espera: el plazo lo corta a los 50 ms
        raise AssertionError("el plazo tenia que cortar el aviso antes")

    monkeypatch.setattr("cheatsheet.api.avisos_de_cobro.armar_mensajeria", canal_lento)

    with capture_logs() as registros:
        respuesta = await notificar(montaje)

    assert respuesta.status_code == 200
    (cobro,) = montaje.cobros.guardados.values()
    assert cobro.estado is EstadoCobro.APROBADO
    vencidos = [r for r in registros if r["event"] == "aviso_de_pago_vencido"]
    assert [r["cobro_id"] for r in vencidos] == [str(cobro.id)]
    assert not [r for r in registros if r["event"] == "aviso_de_pago_fallido"]
    assert TELEFONO not in str(registros)
    assert NOMBRE not in str(registros)
