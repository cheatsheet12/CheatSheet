"""El webhook de estados no se rompe por un estado malo, y no filtra datos personales (U7).

Casos 13, 14, 28: un `wamid` desconocido, un estado que falla sin voltear a los demás ni a los
mensajes del cliente, la firma y los logs. El montaje, en `montaje_webhook_estados.py`.
"""

from __future__ import annotations

import json

import httpx
import pytest
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoEntrega as EstadoDeMensaje,
)
from structlog.testing import capture_logs

from tests.api.montaje_webhook_estados import (
    RUTA_APP,
    cuerpo,
    enviar,
    estado,
    mensaje_de,
    montar,
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


async def test_si_el_segundo_estado_falla_el_primero_ya_quedo_aplicado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 14: una transacción por estado, no una para todo el lote."""
    montaje = await montar(monkeypatch)

    with pytest.raises(RuntimeError):
        await enviar(
            montaje,
            cuerpo(WABA_A, estado("wamid-agente-a", "delivered"), estado("wamid-boom", "read")),
        )

    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENTREGADO
    assert montaje.confirmadas == [EMPRESA_A]  # el segundo se descartó: no hay confirmación


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
