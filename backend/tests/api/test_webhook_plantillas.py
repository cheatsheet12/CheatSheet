"""El webhook `message_template_status_update` (U6, casos 11 a 15).

**No admite override por cuenta** [WH-OVR]: el estado de una plantilla llega a la URL de la app
(`/webhooks/whatsapp`) y se rutea por el **WABA id** del `entry[].id`, nunca por la URL. Sin base de
datos: la resolución de la empresa, la unidad de trabajo y los repositorios son dobles (ver
`montaje_webhook_plantillas.py`); el parser, los casos de uso y el agregado son los reales.
"""

from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest
from cheatsheet.contexts.business_config.domain.plantilla import EstadoDeAprobacion

from tests.conftest import settings_de_prueba

from .montaje_webhook_plantillas import (
    EMPRESA_A,
    EMPRESA_B,
    T0,
    WABA_A,
    Montaje,
    enviar,
    estado,
    evento,
    id_de,
    montar,
)

pytestmark = pytest.mark.asyncio

# --- Caso 11 ----------------------------------------------------------------------------------------------


async def test_approved_por_la_waba_de_a_deja_aprobada_la_plantilla_de_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = montar(monkeypatch)

    respuesta = await enviar(
        montaje, evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_A), reason="NONE")
    )

    assert respuesta.status_code == 200
    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert estado(montaje, EMPRESA_A).puede_usarse
    assert estado(montaje, EMPRESA_B).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


# --- Caso 12 ----------------------------------------------------------------------------------------------


async def test_rejected_guarda_el_motivo_y_la_recomendacion_de_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = montar(monkeypatch)

    await enviar(
        montaje,
        evento(
            WABA_A,
            "REJECTED",
            meta_id=id_de(EMPRESA_A),
            reason="PROMOTIONAL",
            rejection_info={"reason": "PROMOTIONAL", "recommendation": "Quitá el tono comercial."},
        ),
    )

    guardada = estado(montaje, EMPRESA_A)
    assert guardada.estado_aprobacion is EstadoDeAprobacion.RECHAZADA
    assert guardada.motivo_meta == "PROMOTIONAL"
    assert guardada.detalle_meta == "Quitá el tono comercial."


async def test_flagged_sigue_usable_y_deja_el_detalle_de_other_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = montar(monkeypatch)

    await enviar(
        montaje,
        evento(
            WABA_A,
            "FLAGGED",
            meta_id=id_de(EMPRESA_A),
            other_info={"title": "FLAGGED", "description": "Calidad baja: revisá el texto."},
        ),
    )

    guardada = estado(montaje, EMPRESA_A)
    assert guardada.estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert guardada.detalle_meta == "Calidad baja: revisá el texto."


async def test_el_id_de_meta_puede_venir_como_numero(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = montar(monkeypatch)
    montaje.repos[EMPRESA_A].filas[montaje.plantillas[EMPRESA_A].id].meta_plantilla_id = "9876"

    await enviar(montaje, evento(WABA_A, "APPROVED", meta_id=9876))

    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA


async def test_sin_id_se_encuentra_por_nombre_e_idioma(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = montar(monkeypatch)

    await enviar(montaje, evento(WABA_A, "APPROVED"))

    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA


# --- Caso 13 ----------------------------------------------------------------------------------------------


async def test_el_mismo_evento_dos_veces_es_un_solo_efecto(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = montar(monkeypatch)
    notificacion = evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_A))

    primera = await enviar(montaje, notificacion)
    despues_de_la_primera = estado(montaje, EMPRESA_A).updated_at
    segunda = await enviar(montaje, notificacion)

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert estado(montaje, EMPRESA_A).updated_at == despues_de_la_primera


async def test_un_pending_anterior_al_approved_aplicado_no_retrocede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = montar(monkeypatch)
    await enviar(montaje, evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_A), momento=T0))

    await enviar(
        montaje,
        evento(WABA_A, "PENDING", meta_id=id_de(EMPRESA_A), momento=T0 - timedelta(minutes=10)),
    )

    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA


# --- Caso 14: se rutea por WABA, nunca por la URL ----------------------------------------------------------


async def test_un_evento_de_la_waba_de_a_por_la_url_de_b_actualiza_a_y_nunca_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = montar(monkeypatch)

    respuesta = await enviar(
        montaje,
        evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_A)),
        ruta=f"/webhooks/whatsapp/{EMPRESA_B}",
    )

    assert respuesta.status_code == 200
    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert estado(montaje, EMPRESA_B).estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert montaje.repos[EMPRESA_B].guardados == 0


async def test_una_waba_desconocida_es_200_sin_efecto(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = montar(monkeypatch)

    respuesta = await enviar(montaje, evento("999", "APPROVED", meta_id=id_de(EMPRESA_A)))

    assert respuesta.status_code == 200
    assert montaje.repos[EMPRESA_A].guardados == 0
    assert montaje.repos[EMPRESA_B].guardados == 0


async def test_una_waba_con_dos_duenos_no_se_adivina(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = montar(monkeypatch, {WABA_A: [EMPRESA_A, EMPRESA_B]})

    respuesta = await enviar(montaje, evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_A)))

    assert respuesta.status_code == 200
    assert montaje.repos[EMPRESA_A].guardados == 0
    assert montaje.repos[EMPRESA_B].guardados == 0


async def test_un_id_de_meta_de_otra_empresa_no_toca_la_plantilla_de_esta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La WABA dice A, el id de plantilla es de B: se busca **dentro de A** y no existe."""
    montaje = montar(monkeypatch)

    await enviar(montaje, evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_B)))

    assert estado(montaje, EMPRESA_B).estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


# --- Caso 15: firma y verificación ----------------------------------------------------------------------------


async def test_una_firma_invalida_es_200_sin_efecto(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = montar(monkeypatch)

    respuesta = await enviar(
        montaje,
        evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_A)),
        firma="sha256=" + "0" * 64,
    )

    assert respuesta.status_code == 200
    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


async def test_sin_firma_la_ruta_de_la_app_no_aplica_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = montar(monkeypatch)
    crudo = json.dumps(evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_A))).encode()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.post("/webhooks/whatsapp", content=crudo)

    assert respuesta.status_code == 200
    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


async def _verificar(montaje: Montaje, **params: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        return await cliente.get("/webhooks/whatsapp", params=params)


async def test_la_verificacion_de_la_url_de_la_app_devuelve_el_desafio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = montar(monkeypatch)
    token = settings_de_prueba().whatsapp_webhook_verify_token

    respuesta = await _verificar(
        montaje,
        **{"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "12345"},
    )

    assert respuesta.status_code == 200
    assert respuesta.text == "12345"


async def test_la_verificacion_con_otro_token_es_404(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = montar(monkeypatch)

    respuesta = await _verificar(
        montaje,
        **{"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "12345"},
    )

    assert respuesta.status_code == 404
