"""Un mensaje entrante con un `wamid` inutilizable se descarta en el borde (wamid-entrante-largo).

El `id` es la clave de idempotencia del mensaje (D20) y entra en `mensaje.externo_id`
(`varchar(160)`). Más largo, el `INSERT` fallaba y salía un 500 que Meta reintentaba; vacío, se
tomaba por «ya procesado» y se perdía en silencio. El montaje es el de `montaje_webhook_estados`
(sin base); `_procesar` se reemplaza para ver qué llega al caso de uso.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from cheatsheet.api.routers import whatsapp
from cheatsheet.contexts.conversational.application.ports import MensajeEntrante
from cheatsheet.shared.externo_id import LARGO_MAXIMO_EXTERNO_ID
from structlog.testing import capture_logs

from tests.api.montaje_webhook_estados import RUTA_APP, enviar, montar
from tests.api.montaje_webhook_plantillas import EMPRESA_A, WABA_A
from tests.logs import logger_nuevo

TELEFONO = "5491155550000"
TEXTO = "quiero un turno para el martes"


def _mensaje(wamid: Any) -> dict[str, Any]:
    return {"id": wamid, "from": TELEFONO, "text": {"body": TEXTO}}


def _notificacion(*mensajes: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": WABA_A,
                "changes": [{"field": "messages", "value": {"messages": list(mensajes)}}],
            }
        ],
    }


def _traducidos(*mensajes: dict[str, Any]) -> list[MensajeEntrante]:
    return whatsapp._mensajes_de(json.dumps(_notificacion(*mensajes)).encode())


# ------------------------------------------------------------------ casos 1 a 3


def test_un_wamid_de_mas_del_largo_de_la_columna_se_omite() -> None:
    assert _traducidos(_mensaje("w" * (LARGO_MAXIMO_EXTERNO_ID + 1))) == []


def test_un_wamid_de_exactamente_el_largo_de_la_columna_se_procesa() -> None:
    justo = "w" * LARGO_MAXIMO_EXTERNO_ID

    (entrante,) = _traducidos(_mensaje(justo))

    assert entrante.externo_id == justo


def test_un_wamid_vacio_se_omite() -> None:
    assert _traducidos(_mensaje("")) == []


# ------------------------------------------------------------------ casos 4 y 5


def _registrar_los_mensajes_procesados(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    procesados: list[str] = []

    async def procesar(_recursos: object, _empresa: object, entrante: MensajeEntrante) -> None:
        procesados.append(entrante.externo_id)

    monkeypatch.setattr(whatsapp, "_procesar", procesar)
    return procesados


@pytest.mark.asyncio
async def test_un_mensaje_inutilizable_no_impide_procesar_el_valido_y_contesta_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await montar(monkeypatch)
    procesados = _registrar_los_mensajes_procesados(monkeypatch)

    respuesta = await enviar(
        montaje,
        _notificacion(
            _mensaje("w" * (LARGO_MAXIMO_EXTERNO_ID + 1)),
            _mensaje(""),
            _mensaje("wamid.VALIDO"),
        ),
        f"{RUTA_APP}/{EMPRESA_A}",
    )

    assert respuesta.status_code == 200
    assert procesados == ["wamid.VALIDO"]


@pytest.mark.asyncio
async def test_el_log_del_descarte_lleva_largo_y_motivo_y_ningun_dato_personal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger_nuevo(monkeypatch, whatsapp)
    montaje = await montar(monkeypatch)
    _registrar_los_mensajes_procesados(monkeypatch)
    largo = "SECRETO" + "w" * LARGO_MAXIMO_EXTERNO_ID

    with capture_logs() as registros:
        respuesta = await enviar(
            montaje,
            _notificacion(_mensaje(largo), _mensaje("")),
            f"{RUTA_APP}/{EMPRESA_A}",
        )

    assert respuesta.status_code == 200
    descartes = [uno for uno in registros if uno["event"] == "whatsapp_id_entrante_inutilizable"]
    assert [(uno["largo"], uno["motivo"]) for uno in descartes] == [
        (len(largo), "demasiado_largo"),
        (0, "vacio"),
    ]
    for dato in ("SECRETO", TELEFONO, TEXTO):
        assert dato not in repr(registros)
