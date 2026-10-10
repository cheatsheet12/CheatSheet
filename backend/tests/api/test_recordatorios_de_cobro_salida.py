"""Lo que el panel ve de cada recordatorio de un cobro: sus intentos y su motivo (U7, D-U7-7).

PAN-COB-02 pinta «Reintentando · intento n de 3 · próximo hh:mm» y el motivo traducido de un
`FALLIDO`. El router solo expone lo que ya está en el dominio: `intentos`, `proximo_intento_en`
(**solo** mientras la fila espera un reintento: en un envío en curso es la ventana de la reserva y
mostrarla como «próximo intento» engañaría) y `ultimo_error` (un código de Meta o una clase corta).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cheatsheet.api.routers.cobros import _a_recordatorio
from cheatsheet.contexts.payments.domain.recordatorio import Recordatorio

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


def _fila() -> Recordatorio:
    return Recordatorio(id=uuid4(), cobro_id=uuid4(), paso=1, canal="WHATSAPP")


def test_una_fila_esperando_reintento_expone_el_intento_y_la_hora_del_proximo() -> None:
    fila = _fila()
    fila.iniciar_intento(AHORA)
    assert fila.registrar_falla(AHORA, codigo="SATURADA", transitoria=True) is True

    salida = _a_recordatorio(fila)

    assert salida.intentos == 1
    assert salida.proximo_intento_en == AHORA + timedelta(hours=1)
    assert salida.ultimo_error == "SATURADA"
    assert salida.enviado_en is None


def test_un_envio_en_curso_no_expone_su_ventana_como_proximo_intento() -> None:
    fila = _fila()
    fila.iniciar_intento(AHORA)

    salida = _a_recordatorio(fila)

    assert salida.intentos == 1
    assert salida.proximo_intento_en is None
    assert salida.ultimo_error is None


def test_un_fallido_expone_el_motivo_y_ningun_proximo_intento() -> None:
    fila = _fila()
    fila.iniciar_intento(AHORA)
    fila.registrar_falla(AHORA, codigo="131026", transitoria=False)

    salida = _a_recordatorio(fila)

    assert salida.estado_entrega == "FALLIDO"
    assert salida.ultimo_error == "131026"
    assert salida.proximo_intento_en is None


def test_un_recordatorio_enviado_trae_cero_novedades() -> None:
    fila = _fila()
    fila.iniciar_intento(AHORA)
    fila.marcar_enviado(AHORA, externo_id="wamid.X")

    salida = _a_recordatorio(fila)

    assert (salida.intentos, salida.proximo_intento_en, salida.ultimo_error) == (1, None, None)
