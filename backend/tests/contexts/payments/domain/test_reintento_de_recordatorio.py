"""La máquina de estados de un recordatorio que se reintenta (U7, tramo ii, D-U7-3).

Una fila nace al empezar el primer intento (`intentos=1`, con una ventana de envío) y termina de
una sola de cuatro maneras: enviada, fallida, descartada o esperando otro intento. Lo que nunca
puede pasar es que una fila cuyo resultado se desconoce se vuelva a mandar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.payments.domain.recordatorio import (
    COBRO_CERRADO,
    REINTENTOS_MAXIMOS,
    VENTANA_DE_ENVIO,
    EstadoEntrega,
    Recordatorio,
    proximo_paso,
)

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


def _nuevo() -> Recordatorio:
    return Recordatorio(id=uuid4(), cobro_id=uuid4(), paso=1, canal="WHATSAPP")


def _en_curso() -> Recordatorio:
    recordatorio = _nuevo()
    recordatorio.iniciar_intento(AHORA)
    return recordatorio


def test_una_fila_recien_creada_no_tiene_intentos_ni_espera() -> None:
    recordatorio = _nuevo()

    assert recordatorio.intentos == 0
    assert recordatorio.proximo_intento_en is None
    assert recordatorio.sin_intentar is True


def test_iniciar_un_intento_cuenta_y_abre_la_ventana_de_envio() -> None:
    recordatorio = _en_curso()

    assert recordatorio.intentos == 1
    assert recordatorio.proximo_intento_en == AHORA + VENTANA_DE_ENVIO
    assert recordatorio.envio_en_curso is True
    assert recordatorio.sin_intentar is False
    assert recordatorio.enviado_en is None


def test_una_falla_transitoria_programa_el_reintento_con_espera_exponencial() -> None:
    recordatorio = _en_curso()

    hay_reintento = recordatorio.registrar_falla(AHORA, codigo="SATURADA", transitoria=True)

    assert hay_reintento is True
    assert recordatorio.esperando_reintento is True
    assert recordatorio.enviado_en is None
    assert recordatorio.estado_entrega is None
    assert recordatorio.ultimo_error == "SATURADA"
    assert recordatorio.proximo_intento_en == AHORA + timedelta(hours=1)

    recordatorio.iniciar_intento(AHORA + timedelta(hours=1))
    recordatorio.registrar_falla(AHORA + timedelta(hours=1), codigo="SATURADA", transitoria=True)

    assert recordatorio.intentos == 2
    assert recordatorio.proximo_intento_en == AHORA + timedelta(hours=3)


def test_el_ultimo_intento_transitorio_deja_la_fila_fallida_y_despachada() -> None:
    recordatorio = _nuevo()
    for _ in range(REINTENTOS_MAXIMOS):
        recordatorio.iniciar_intento(AHORA)
        hay_reintento = recordatorio.registrar_falla(AHORA, codigo="131056", transitoria=True)

    assert hay_reintento is False
    assert recordatorio.intentos == REINTENTOS_MAXIMOS
    assert recordatorio.estado_entrega is EstadoEntrega.FALLIDO
    assert recordatorio.enviado_en == AHORA  # el paso se da por hecho: la cadena sigue
    assert recordatorio.proximo_intento_en is None
    assert recordatorio.ultimo_error == "131056"


@pytest.mark.parametrize("codigo", ["131026", "INCIERTO", "SIN_TELEFONO"])
def test_una_falla_que_no_es_transitoria_no_se_reintenta(codigo: str) -> None:
    recordatorio = _en_curso()

    hay_reintento = recordatorio.registrar_falla(AHORA, codigo=codigo, transitoria=False)

    assert hay_reintento is False
    assert recordatorio.estado_entrega is EstadoEntrega.FALLIDO
    assert recordatorio.enviado_en == AHORA
    assert recordatorio.proximo_intento_en is None
    assert recordatorio.ultimo_error == codigo


def test_un_envio_que_sale_en_el_reintento_limpia_la_falla_anterior() -> None:
    recordatorio = _en_curso()
    recordatorio.registrar_falla(AHORA, codigo="SATURADA", transitoria=True)
    recordatorio.iniciar_intento(AHORA + timedelta(hours=1))

    recordatorio.marcar_enviado(AHORA + timedelta(hours=1), externo_id="wamid-9")

    assert recordatorio.estado_entrega is EstadoEntrega.ENVIADO
    assert recordatorio.externo_id == "wamid-9"
    assert recordatorio.proximo_intento_en is None
    assert recordatorio.ultimo_error is None
    assert recordatorio.intentos == 2


def test_no_corresponde_intentar_antes_de_la_espera_y_si_despues() -> None:
    recordatorio = _en_curso()
    recordatorio.registrar_falla(AHORA, codigo="SATURADA", transitoria=True)

    assert recordatorio.corresponde_intentar(AHORA + timedelta(minutes=59)) is False
    assert recordatorio.corresponde_intentar(AHORA + timedelta(hours=1)) is True


def test_una_fila_sin_intentar_corresponde_siempre() -> None:
    """Nunca empezó un intento: es seguro mandarla, a diferencia de una en curso."""
    assert _nuevo().corresponde_intentar(AHORA) is True


def test_un_envio_en_curso_solo_vence_con_su_ventana() -> None:
    recordatorio = _en_curso()

    assert recordatorio.envio_perdido(AHORA + VENTANA_DE_ENVIO - timedelta(seconds=1)) is False
    assert recordatorio.envio_perdido(AHORA + VENTANA_DE_ENVIO) is True
    assert recordatorio.corresponde_intentar(AHORA + VENTANA_DE_ENVIO) is True


def test_una_espera_de_reintento_no_es_un_envio_perdido() -> None:
    recordatorio = _en_curso()
    recordatorio.registrar_falla(AHORA, codigo="SATURADA", transitoria=True)

    assert recordatorio.envio_perdido(AHORA + timedelta(days=1)) is False


def test_descartar_deja_la_fila_sin_despachar_y_sin_espera() -> None:
    recordatorio = _en_curso()
    recordatorio.registrar_falla(AHORA, codigo="SATURADA", transitoria=True)

    recordatorio.descartar()

    assert recordatorio.descartado is True
    assert recordatorio.ultimo_error == COBRO_CERRADO
    assert recordatorio.enviado_en is None
    assert recordatorio.proximo_intento_en is None
    assert recordatorio.corresponde_intentar(AHORA + timedelta(days=9)) is False


def test_una_fila_sin_resolver_no_cuenta_como_despachada_en_el_paso() -> None:
    espera = _en_curso()

    assert proximo_paso([espera]) == espera.paso
