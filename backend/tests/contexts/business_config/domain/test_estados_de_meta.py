"""El vocabulario de Meta traducido al nuestro (U6, caso 18): los 9 estados del nodo y los 14
eventos del webhook. Un valor que Meta agregue mañana no cambia nada y se nota en un log.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.business_config.domain.estados_de_meta import (
    ESTADOS_DEL_NODO,
    EVENTOS_DEL_WEBHOOK,
    EVENTOS_QUE_SE_RELEEN,
    estado_desde_evento,
    estado_desde_nodo,
)
from cheatsheet.contexts.business_config.domain.plantilla import EstadoDeAprobacion

A = EstadoDeAprobacion


@pytest.mark.parametrize(
    ("meta", "nuestro"),
    [
        ("APPROVED", A.APROBADA),
        ("IN_APPEAL", A.PENDIENTE),
        ("PENDING", A.PENDIENTE),
        ("REJECTED", A.RECHAZADA),
        ("LIMIT_EXCEEDED", A.RECHAZADA),
        ("PAUSED", A.PAUSADA),
        ("DISABLED", A.DESHABILITADA),
        ("DELETED", A.SIN_ENVIAR),
        ("PENDING_DELETION", A.SIN_ENVIAR),
    ],
)
def test_los_nueve_estados_del_nodo(meta: str, nuestro: EstadoDeAprobacion) -> None:
    assert estado_desde_nodo(meta) is nuestro


@pytest.mark.parametrize(
    ("meta", "nuestro"),
    [
        ("APPROVED", A.APROBADA),
        ("REINSTATED", A.APROBADA),
        ("FLAGGED", A.APROBADA),
        ("LOCKED", A.APROBADA),
        ("PENDING", A.PENDIENTE),
        ("IN_APPEAL", A.PENDIENTE),
        ("REJECTED", A.RECHAZADA),
        ("LIMIT_EXCEEDED", A.RECHAZADA),
        ("PAUSED", A.PAUSADA),
        ("DISABLED", A.DESHABILITADA),
        ("DELETED", A.SIN_ENVIAR),
        ("PENDING_DELETION", A.SIN_ENVIAR),
        ("ARCHIVED", A.SIN_ENVIAR),
    ],
)
def test_los_eventos_del_webhook(meta: str, nuestro: EstadoDeAprobacion) -> None:
    assert estado_desde_evento(meta) is nuestro


def test_unarchived_no_decide_un_estado_y_se_relee() -> None:
    assert estado_desde_evento("UNARCHIVED") is None
    assert "UNARCHIVED" in EVENTOS_QUE_SE_RELEEN


def test_estan_los_nueve_estados_y_los_catorce_eventos_documentados() -> None:
    assert len(ESTADOS_DEL_NODO) == 9
    assert len(set(EVENTOS_DEL_WEBHOOK) | EVENTOS_QUE_SE_RELEEN) == 14


@pytest.mark.parametrize("valor", ["INVENTADO", "", "approved"])
def test_un_valor_desconocido_no_se_traduce(valor: str) -> None:
    assert estado_desde_nodo(valor) is None
    assert estado_desde_evento(valor) is None
