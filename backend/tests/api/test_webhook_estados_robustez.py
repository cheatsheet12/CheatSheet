"""El webhook de estados no se rompe por un estado malo, y no filtra datos personales (U7).

Casos 13, 14, 28: un `wamid` desconocido, un estado que falla sin voltear a los demás ni a los
mensajes del cliente, la firma y los logs. El montaje, en `montaje_webhook_estados.py`.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from cheatsheet.api import entregas
from cheatsheet.api.routers import whatsapp
from cheatsheet.contexts.conversational.application.ports import MensajeEntrante
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoEntrega as EstadoDeMensaje,
)
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega as EstadoDeRecordatorio
from structlog.testing import capture_logs

from tests.api.montaje_webhook_estados import (
    RUTA_APP,
    cuerpo,
    enviar,
    estado,
    mensaje_de,
    montar,
    recordatorio_de,
)
from tests.api.montaje_webhook_plantillas import EMPRESA_A, WABA_A, WABA_B

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------ caso 13 y 14


async def test_un_wamid_desconocido_contesta_200_y_el_log_no_lleva_el_wamid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)
    desconocido = "wamid.HBgMNTQ5MTE1NTU1MDAwMBUCABIYFjNFQjAxMjM0NTY3ODlBQkNERUY"

    with capture_logs() as registros:
        respuesta = await enviar(montaje, cuerpo(WABA_A, estado(desconocido, "sent")))

    assert respuesta.status_code == 200
    assert "whatsapp_estado_sin_destinatario" in [uno["event"] for uno in registros]
    assert desconocido not in repr(registros)
    assert "5491155550000" not in repr(registros)


async def test_un_estado_que_falla_no_voltea_a_los_demas_de_la_notificacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 14: una transacción por estado, y un estado venenoso no tumba la notificación.

    El primero y el tercero (de los dos lados: mensaje y recordatorio) quedan aplicados; el del
    medio se descarta con un log que lleva solo la clase de la excepción, y se contesta 200 (un 500
    haría que Meta reintentara el mismo estado venenoso durante horas).
    """
    montaje = await montar(monkeypatch)

    with capture_logs() as registros:
        respuesta = await enviar(
            montaje,
            cuerpo(
                WABA_A,
                estado("wamid-agente-a", "delivered"),
                estado("wamid-boom", "read", recipient_id="5491155550000"),
                estado("wamid-cobro-a", "read"),
            ),
        )

    assert respuesta.status_code == 200
    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENTREGADO
    assert recordatorio_de(montaje, EMPRESA_A).estado_entrega is EstadoDeRecordatorio.LEIDO
    assert montaje.confirmadas == [EMPRESA_A, EMPRESA_A]  # el venenoso no confirma
    (fallo,) = [uno for uno in registros if uno["event"] == "whatsapp_estado_sin_aplicar"]
    assert fallo["causa"] == "RuntimeError"
    for dato in ("wamid-boom", "5491155550000", "se rompio algo nuestro"):
        assert dato not in repr(registros)


async def test_un_estado_venenoso_no_bloquea_los_mensajes_del_cliente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """En la ruta por empresa los estados corren antes que los mensajes entrantes (H4)."""
    montaje = await montar(monkeypatch)
    procesados = _registrar_los_mensajes_procesados(monkeypatch)

    respuesta = await enviar(
        montaje,
        _notificacion_con_estado_y_mensaje(estado("wamid-boom", "read")),
        f"{RUTA_APP}/{EMPRESA_A}",
    )

    assert respuesta.status_code == 200
    assert procesados == ["wamid.entrante"]


async def test_una_falla_transitoria_no_corta_los_demas_estados_ni_los_mensajes_y_se_reintenta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se cae la base en un estado: los demás y los mensajes se procesan y recién al final es 500.

    El 500 es lo que le dice a Meta que reintente; el reintento es idempotente.
    """
    montaje = await montar(monkeypatch)
    procesados = _registrar_los_mensajes_procesados(monkeypatch)

    with capture_logs() as registros, pytest.raises(entregas.EstadosSinAplicarPorFallaTransitoria):
        await enviar(
            montaje,
            _notificacion_con_estado_y_mensaje(
                estado("wamid-caido", "read"), estado("wamid-agente-a", "delivered")
            ),
            f"{RUTA_APP}/{EMPRESA_A}",
        )

    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENTREGADO
    assert procesados == ["wamid.entrante"]
    (fallo,) = [uno for uno in registros if uno["event"] == "whatsapp_estado_con_falla_transitoria"]
    assert fallo["causa"] == "OperationalError"
    assert "wamid-caido" not in repr(registros)


def _registrar_los_mensajes_procesados(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    procesados: list[str] = []

    async def procesar(_recursos: object, _empresa: object, entrante: MensajeEntrante) -> None:
        procesados.append(entrante.externo_id)

    monkeypatch.setattr(whatsapp, "_procesar", procesar)
    return procesados


def _notificacion_con_estado_y_mensaje(*estados: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry": [
            {
                "id": WABA_A,
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "statuses": list(estados),
                            "messages": [
                                {
                                    "id": "wamid.entrante",
                                    "from": "5491155550000",
                                    "text": {"body": "hola"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


# ------------------------------------------------------------------ rutas y robustez


async def test_una_firma_invalida_no_procesa_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = await montar(monkeypatch)
    crudo = json.dumps(cuerpo(WABA_A, estado("wamid-agente-a", "read"))).encode()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.post(
            RUTA_APP, content=crudo, headers={"x-hub-signature-256": "sha256=00"}
        )

    assert respuesta.status_code == 200
    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENVIADO


async def test_un_payload_solo_de_estados_no_loguea_mensajes_en_la_url_de_la_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`hay_mensajes` era verdadero para cualquier `field=messages`: ahora mira `messages[]`."""
    montaje = await montar(monkeypatch)

    with capture_logs() as registros:
        await enviar(montaje, cuerpo(WABA_A, estado("wamid-agente-a", "read")))
        await enviar(
            montaje,
            {
                "entry": [
                    {
                        "id": WABA_A,
                        "changes": [
                            {"field": "messages", "value": {"messages": [{"id": "m", "from": "1"}]}}
                        ],
                    }
                ]
            },
        )

    eventos = [uno["event"] for uno in registros]
    assert eventos.count("whatsapp_mensajes_en_la_url_de_la_app") == 1


async def test_ningun_log_de_los_estados_lleva_telefono_ni_wamid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 28 para los módulos nuevos: el `recipient_id` (un teléfono) y el `wamid` no se loguean."""
    montaje = await montar(monkeypatch)
    notificacion = cuerpo(
        WABA_A,
        estado("wamid-agente-a", "failed", errors=[{"code": 131026}], recipient_id="5491155550000"),
        estado("wamid-nadie", "read", recipient_id="5491155550000"),
    )

    with capture_logs() as registros:
        await enviar(montaje, notificacion)
        await enviar(
            montaje, cuerpo(WABA_B, estado("wamid-nadie", "read")), f"{RUTA_APP}/{EMPRESA_A}"
        )

    volcado = repr(registros)
    assert registros
    for dato in ("5491155550000", "wamid-nadie", "wamid-agente-a"):
        assert dato not in volcado
