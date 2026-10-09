"""`estados_de_entrega`: los `statuses[]` de Meta, leídos a la defensiva (U7, casos 8 y 9).

El cuerpo lo manda un tercero: una forma inesperada tiene que producir una lista vacía y un 200, no
un 500 que Meta reintenta durante horas. De cada estado solo se lee lo que se usa: el `id` (wamid),
el `status` y el `code` de `errors[0]`. **Nada de `recipient_id`** (es un teléfono) ni del `title`.
"""

from __future__ import annotations

from typing import Any

import pytest
from cheatsheet.api.whatsapp_notificaciones import (
    EstadoDeEntregaNotificado,
    estados_de_entrega,
    hay_mensajes,
)

WABA = "100200300"


def _cuerpo(
    *estados: dict[str, Any], waba: object = WABA, campo: str = "messages"
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": waba,
                "changes": [{"field": campo, "value": {"statuses": list(estados)}}],
            }
        ],
    }


def _estado(status: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": "wamid.ABC",
        "status": status,
        "timestamp": "1760000000",
        "recipient_id": "5491155550000",
        **extra,
    }


@pytest.mark.parametrize(
    ("status", "esperado"),
    [("sent", "ENVIADO"), ("delivered", "ENTREGADO"), ("read", "LEIDO"), ("failed", "FALLIDO")],
)
def test_los_cuatro_estados_de_meta_pasan_a_nuestro_vocabulario(status: str, esperado: str) -> None:
    assert estados_de_entrega(_cuerpo(_estado(status))) == [
        EstadoDeEntregaNotificado(
            waba_id=WABA, externo_id="wamid.ABC", estado=esperado, codigo_de_error=None
        )
    ]


def test_failed_lee_el_codigo_de_errors_0_y_no_el_titulo() -> None:
    cuerpo = _cuerpo(_estado("failed", errors=[{"code": 131047, "title": "Re-engagement message"}]))

    (estado,) = estados_de_entrega(cuerpo)

    assert estado.codigo_de_error == "131047"
    assert "Re-engagement" not in repr(estado)
    assert "5491155550000" not in repr(estado)  # el `recipient_id` nunca se lee


def test_un_failed_sin_errores_queda_sin_codigo() -> None:
    (estado,) = estados_de_entrega(_cuerpo(_estado("failed")))

    assert estado.estado == "FALLIDO"
    assert estado.codigo_de_error is None


def test_el_codigo_de_error_solo_se_lee_en_un_failed() -> None:
    (estado,) = estados_de_entrega(_cuerpo(_estado("read", errors=[{"code": 1}])))

    assert estado.codigo_de_error is None


def test_played_y_los_estados_desconocidos_se_ignoran() -> None:
    cuerpo = _cuerpo(_estado("played"), _estado("deleted"), _estado("delivered"))

    assert [uno.estado for uno in estados_de_entrega(cuerpo)] == ["ENTREGADO"]


@pytest.mark.parametrize(
    "malo",
    [
        {"status": "read"},  # sin id
        {"id": "", "status": "read"},
        {"id": 123, "status": "read"},
        {"id": "x" * 161, "status": "read"},  # un id nunca se corta
        {"id": "wamid.1"},  # sin status
        {"id": "wamid.1", "status": 5},
    ],
)
def test_un_estado_ilegible_se_saltea_sin_romper(malo: dict[str, Any]) -> None:
    assert estados_de_entrega(_cuerpo(malo, _estado("read"))) == [
        EstadoDeEntregaNotificado(
            waba_id=WABA, externo_id="wamid.ABC", estado="LEIDO", codigo_de_error=None
        )
    ]


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"entry": "no"},
        {"entry": [{"id": WABA, "changes": "no"}]},
        {"entry": [{"id": WABA, "changes": [{"field": "messages", "value": "no"}]}]},
        {"entry": [{"id": WABA, "changes": [{"field": "messages", "value": {"statuses": "no"}}]}]},
        _cuerpo(_estado("read"), waba=""),  # sin WABA no hay a qué empresa atribuirlo
        _cuerpo(_estado("read"), waba=123),
        _cuerpo(_estado("read"), campo="message_template_status_update"),
    ],
)
def test_lo_que_no_se_entiende_da_lista_vacia(cuerpo: dict[str, Any]) -> None:
    assert estados_de_entrega(cuerpo) == []


def test_el_codigo_de_error_demasiado_largo_se_descarta_en_vez_de_cortarse() -> None:
    (estado,) = estados_de_entrega(_cuerpo(_estado("failed", errors=[{"code": "9" * 80}])))

    assert estado.codigo_de_error is None


def test_hay_mensajes_distingue_messages_de_statuses() -> None:
    solo_estados = _cuerpo(_estado("read"))
    con_mensajes = {
        "entry": [
            {"id": WABA, "changes": [{"field": "messages", "value": {"messages": [{"id": "m"}]}}]}
        ]
    }

    assert hay_mensajes(solo_estados) is False
    assert hay_mensajes(con_mensajes) is True
    assert (
        hay_mensajes({"entry": [{"changes": [{"field": "messages", "value": {"messages": []}}]}]})
        is False
    )
