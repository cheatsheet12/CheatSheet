"""El webhook de WhatsApp recibe los `statuses[]` de Meta y mueve el estado de entrega (U7).

Casos 1, 2, 5, 8, 10, 11 y 12: el ruteo por empresa y el orden de los estados. La robustez del
webhook (wamid desconocido, estados que fallan, firma, logs) está en
`test_webhook_estados_robustez.py`; el montaje, en `montaje_webhook_estados.py`.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoEntrega as EstadoDeMensaje,
)
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega as EstadoDeRecordatorio
from cheatsheet.shared.empresa import EmpresaId
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
from tests.api.montaje_webhook_plantillas import EMPRESA_A, EMPRESA_B, WABA_A, WABA_B

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------ caso 1 y 2


@pytest.mark.parametrize("ruta", [RUTA_APP, f"{RUTA_APP}/{EMPRESA_A}"])
async def test_delivered_del_wamid_de_un_mensaje_del_agente_lo_deja_entregado(
    monkeypatch: pytest.MonkeyPatch, ruta: str
) -> None:
    montaje = await montar(monkeypatch)

    respuesta = await enviar(montaje, cuerpo(WABA_A, estado("wamid-agente-a", "delivered")), ruta)

    assert respuesta.status_code == 200
    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENTREGADO
    assert montaje.confirmadas == [EMPRESA_A]


@pytest.mark.parametrize("ruta", [RUTA_APP, f"{RUTA_APP}/{EMPRESA_A}"])
async def test_read_del_wamid_de_un_recordatorio_de_cobro_lo_deja_leido(
    monkeypatch: pytest.MonkeyPatch, ruta: str
) -> None:
    montaje = await montar(monkeypatch)

    await enviar(montaje, cuerpo(WABA_A, estado("wamid-cobro-a", "read")), ruta)

    assert recordatorio_de(montaje, EMPRESA_A).estado_entrega is EstadoDeRecordatorio.LEIDO


# ------------------------------------------------------------------ caso 5 y 8


async def test_el_mismo_statuses_dos_veces_es_un_solo_efecto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)
    notificacion = cuerpo(
        WABA_A, estado("wamid-cobro-a", "failed", errors=[{"code": 131047, "title": "x"}])
    )

    await enviar(montaje, notificacion)
    await enviar(montaje, notificacion)

    recordatorio = recordatorio_de(montaje, EMPRESA_A)
    assert recordatorio.estado_entrega is EstadoDeRecordatorio.FALLIDO
    assert recordatorio.ultimo_error == "131047"
    assert len(montaje.publicadores[EMPRESA_A].eventos) == 1


async def test_failed_deja_el_motivo_y_un_read_posterior_no_lo_cambia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)

    await enviar(
        montaje,
        cuerpo(WABA_A, estado("wamid-agente-a", "failed", errors=[{"code": 131047}])),
    )
    await enviar(montaje, cuerpo(WABA_A, estado("wamid-agente-a", "read")))

    mensaje = mensaje_de(montaje, EMPRESA_A)
    assert mensaje.estado_entrega is EstadoDeMensaje.FALLIDO
    assert mensaje.motivo_de_falla == "131047"


async def test_delivered_fuera_de_orden_despues_de_read_no_retrocede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)

    await enviar(
        montaje,
        cuerpo(
            WABA_A,
            estado("wamid-agente-a", "read"),
            estado("wamid-agente-a", "delivered"),
            estado("wamid-cobro-a", "read"),
            estado("wamid-cobro-a", "delivered"),
        ),
    )

    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.LEIDO
    assert recordatorio_de(montaje, EMPRESA_A).estado_entrega is EstadoDeRecordatorio.LEIDO


async def test_played_se_ignora_sin_error(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = await montar(monkeypatch)

    respuesta = await enviar(montaje, cuerpo(WABA_A, estado("wamid-agente-a", "played")))

    assert respuesta.status_code == 200
    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENVIADO
    assert montaje.confirmadas == []


# ------------------------------------------------------------------ caso 10, 11 y 12


async def test_el_wamid_de_un_recordatorio_de_b_por_la_url_de_a_no_cambia_nada_en_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 10. Con la WABA de A en el cuerpo, el estado se busca **en A**: el `wamid` de B no existe ahí."""
    montaje = await montar(monkeypatch)

    respuesta = await enviar(
        montaje,
        cuerpo(WABA_A, estado("wamid-cobro-b", "read"), estado("wamid-agente-b", "read")),
        f"{RUTA_APP}/{EMPRESA_A}",
    )

    assert respuesta.status_code == 200
    assert recordatorio_de(montaje, EMPRESA_B).estado_entrega is EstadoDeRecordatorio.ENVIADO
    assert mensaje_de(montaje, EMPRESA_B).estado_entrega is EstadoDeMensaje.ENVIADO


async def test_una_waba_ajena_en_la_url_de_a_se_descarta_con_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 11: la URL no decide la empresa, y la WABA de B no es la de A."""
    montaje = await montar(monkeypatch)

    with capture_logs() as registros:
        respuesta = await enviar(
            montaje, cuerpo(WABA_B, estado("wamid-agente-b", "read")), f"{RUTA_APP}/{EMPRESA_A}"
        )

    assert respuesta.status_code == 200
    assert mensaje_de(montaje, EMPRESA_B).estado_entrega is EstadoDeMensaje.ENVIADO
    assert montaje.confirmadas == []
    assert "whatsapp_estado_de_waba_ajena" in [uno["event"] for uno in registros]


async def test_la_ruta_de_la_app_rutea_cada_estado_a_la_empresa_dueña_de_su_waba(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 12."""
    montaje = await montar(monkeypatch)

    await enviar(
        montaje,
        {
            "entry": [
                {
                    "id": waba,
                    "changes": [
                        {"field": "messages", "value": {"statuses": [estado(wamid, "read")]}}
                    ],
                }
                for waba, wamid in ((WABA_A, "wamid-agente-a"), (WABA_B, "wamid-cobro-b"))
            ]
        },
    )

    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.LEIDO
    assert recordatorio_de(montaje, EMPRESA_B).estado_entrega is EstadoDeRecordatorio.LEIDO
    assert montaje.confirmadas == [EMPRESA_A, EMPRESA_B]  # una transacción por estado


@pytest.mark.parametrize("duenas", [[], [EMPRESA_A, EMPRESA_B]])
async def test_una_waba_sin_dueña_o_con_dos_se_registra_y_se_sigue(
    monkeypatch: pytest.MonkeyPatch, duenas: list[EmpresaId]
) -> None:
    montaje = await montar(monkeypatch, {WABA_A: duenas})

    with capture_logs() as registros:
        respuesta = await enviar(montaje, cuerpo(WABA_A, estado("wamid-agente-a", "read")))

    assert respuesta.status_code == 200
    assert mensaje_de(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENVIADO
    assert "whatsapp_estado_de_waba_sin_una_sola_empresa" in [uno["event"] for uno in registros]
