"""El estado de entrega de un `Recordatorio` es monótono y `FALLIDO` es terminal (U7, D-U7-2).

La regla es la misma que la de `Mensaje` en `conversational`: Meta no garantiza el orden ni la
ausencia de duplicados, y con «lo último que llega vale» un `delivered` retrasado pisaría un `read`
y PAN-COB-02 diría que el cliente no leyó lo que leyó.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cheatsheet.contexts.payments.domain.recordatorio import (
    LARGO_MAXIMO_ULTIMO_ERROR,
    EstadoEntrega,
    Recordatorio,
)

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


def _enviado() -> Recordatorio:
    recordatorio = Recordatorio(id=uuid4(), cobro_id=uuid4(), paso=1, canal="WHATSAPP")
    recordatorio.marcar_enviado(AHORA, externo_id="wamid-1")
    return recordatorio


def test_marcar_enviado_guarda_el_wamid() -> None:
    recordatorio = _enviado()

    assert recordatorio.externo_id == "wamid-1"
    assert recordatorio.estado_entrega is EstadoEntrega.ENVIADO
    assert recordatorio.enviado_en == AHORA


def test_marcar_enviado_sin_wamid_sigue_funcionando() -> None:
    recordatorio = Recordatorio(id=uuid4(), cobro_id=uuid4(), paso=1, canal="WHATSAPP")

    recordatorio.marcar_enviado(AHORA)

    assert recordatorio.externo_id is None


def test_read_despues_de_delivered_avanza_y_delivered_despues_de_read_no_retrocede() -> None:
    recordatorio = _enviado()

    assert recordatorio.marcar_entrega(EstadoEntrega.ENTREGADO) is True
    assert recordatorio.marcar_entrega(EstadoEntrega.LEIDO) is True
    assert recordatorio.marcar_entrega(EstadoEntrega.ENTREGADO) is False

    assert recordatorio.estado_entrega is EstadoEntrega.LEIDO


def test_read_sin_delivered_previo_es_legitimo() -> None:
    recordatorio = _enviado()

    recordatorio.marcar_entrega(EstadoEntrega.LEIDO)

    assert recordatorio.estado_entrega is EstadoEntrega.LEIDO


def test_el_mismo_estado_dos_veces_no_cambia_nada() -> None:
    recordatorio = _enviado()
    recordatorio.marcar_entrega(EstadoEntrega.ENTREGADO)

    assert recordatorio.marcar_entrega(EstadoEntrega.ENTREGADO) is False


def test_failed_es_terminal_y_guarda_el_motivo() -> None:
    recordatorio = _enviado()
    recordatorio.marcar_entrega(EstadoEntrega.ENTREGADO)

    assert recordatorio.marcar_entrega(EstadoEntrega.FALLIDO, motivo="131047") is True
    assert recordatorio.marcar_entrega(EstadoEntrega.LEIDO) is False
    assert recordatorio.marcar_entrega(EstadoEntrega.FALLIDO, motivo="131026") is False

    assert recordatorio.estado_entrega is EstadoEntrega.FALLIDO
    assert recordatorio.ultimo_error == "131047"


def test_el_motivo_solo_se_guarda_al_fallar_y_se_acota() -> None:
    recordatorio = _enviado()
    recordatorio.marcar_entrega(EstadoEntrega.ENTREGADO, motivo="no corresponde")
    assert recordatorio.ultimo_error is None

    recordatorio.marcar_entrega(EstadoEntrega.FALLIDO, motivo="x" * 500)

    assert recordatorio.ultimo_error == "x" * LARGO_MAXIMO_ULTIMO_ERROR


def test_un_recordatorio_sin_estado_acepta_el_primero() -> None:
    recordatorio = Recordatorio(id=uuid4(), cobro_id=uuid4(), paso=1, canal="WHATSAPP")

    assert recordatorio.marcar_entrega(EstadoEntrega.ENVIADO) is True
