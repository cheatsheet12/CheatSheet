"""El webhook de plantillas ante cuerpos raros y verificaciones (U6, casos 15 y 18).

Lo que Meta (o alguien que fingiera ser Meta) puede mandar: JSON roto, formas inesperadas, estados
que no conocemos. Todo es 200 sin efecto: Meta reintenta durante horas ante cualquier otra cosa.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.business_config.domain.plantilla import EstadoDeAprobacion

from .montaje_webhook_plantillas import (
    EMPRESA_A,
    EMPRESA_B,
    WABA_A,
    WABA_B,
    enviar,
    estado,
    evento,
    id_de,
    montar,
)

pytestmark = pytest.mark.asyncio

# --- Robustez del parser ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        b"no es json",
        b"[]",
        b'{"entry": "basura"}',
        b'{"entry": [{"changes": [{"field": "message_template_status_update", "value": 7}]}]}',
        b'{"entry": [{"id": 5, "changes": [{"field": "message_template_status_update", "value": {}}]}]}',
        b'{"entry": [{"id": "1", "changes": [{"field": "otro", "value": {"event": "APPROVED"}}]}]}',
    ],
)
async def test_un_cuerpo_con_forma_inesperada_es_200_sin_efecto(
    monkeypatch: pytest.MonkeyPatch, cuerpo: bytes
) -> None:
    montaje = montar(monkeypatch)

    respuesta = await enviar(montaje, cuerpo)

    assert respuesta.status_code == 200
    assert montaje.repos[EMPRESA_A].guardados == 0


async def test_un_estado_desconocido_es_200_y_no_cambia_nada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = montar(monkeypatch)

    respuesta = await enviar(montaje, evento(WABA_A, "INVENTADO", meta_id=id_de(EMPRESA_A)))

    assert respuesta.status_code == 200
    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


async def test_un_evento_por_cada_cambio_de_la_notificacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = montar(monkeypatch)
    cuerpo = evento(WABA_A, "APPROVED", meta_id=id_de(EMPRESA_A))
    otra_entrada = evento(WABA_B, "REJECTED", meta_id=id_de(EMPRESA_B), reason="SCAM")
    cuerpo["entry"].extend(otra_entrada["entry"])

    await enviar(montaje, cuerpo)

    assert estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert estado(montaje, EMPRESA_B).estado_aprobacion is EstadoDeAprobacion.RECHAZADA
