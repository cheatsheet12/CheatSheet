"""El estado de entrega de un `Mensaje` y su motivo de falla (U7, casos 6 a 8).

Meta no garantiza el orden de los callbacks ni que no se repitan: el estado solo avanza, `FALLIDO`
es el veredicto final, y aplicar dos veces lo mismo no cambia nada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cheatsheet.contexts.conversational.domain.conversacion import (
    LARGO_MAXIMO_MOTIVO_DE_FALLA,
    DireccionMensaje,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.shared.empresa import EmpresaId

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


def _saliente(estado: EstadoEntrega | None = EstadoEntrega.ENVIADO) -> Mensaje:
    return Mensaje(
        id=uuid4(),
        conversacion_id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        direccion=DireccionMensaje.SALIENTE,
        tipo_contenido=TipoContenido.TEXTO,
        contenido="hola",
        momento=AHORA,
        origen=OrigenDelMensaje.AGENTE,
        estado_entrega=estado,
        externo_id="wamid-1",
    )


def test_avanzar_devuelve_verdadero_y_repetir_o_retroceder_devuelve_falso() -> None:
    mensaje = _saliente()

    assert mensaje.marcar_entrega(EstadoEntrega.ENTREGADO) is True
    assert mensaje.marcar_entrega(EstadoEntrega.ENTREGADO) is False  # el mismo callback, dos veces
    assert mensaje.marcar_entrega(EstadoEntrega.LEIDO) is True
    assert mensaje.marcar_entrega(EstadoEntrega.ENTREGADO) is False  # fuera de orden
    assert mensaje.estado_entrega is EstadoEntrega.LEIDO


def test_leido_sin_entregado_previo_es_legitimo() -> None:
    """Meta no manda `delivered` cuando entrega y lectura son simultáneas."""
    mensaje = _saliente()

    mensaje.marcar_entrega(EstadoEntrega.LEIDO)

    assert mensaje.estado_entrega is EstadoEntrega.LEIDO


def test_fallido_registra_el_motivo_y_un_leido_posterior_no_lo_cambia() -> None:
    mensaje = _saliente()

    mensaje.marcar_entrega(EstadoEntrega.FALLIDO, motivo="131047")
    cambio = mensaje.marcar_entrega(EstadoEntrega.LEIDO)

    assert cambio is False
    assert mensaje.estado_entrega is EstadoEntrega.FALLIDO
    assert mensaje.motivo_de_falla == "131047"


def test_un_fallido_despues_de_entregado_es_el_veredicto_final() -> None:
    mensaje = _saliente(EstadoEntrega.ENTREGADO)

    assert mensaje.marcar_entrega(EstadoEntrega.FALLIDO, motivo="131049") is True

    assert mensaje.estado_entrega is EstadoEntrega.FALLIDO
    assert mensaje.motivo_de_falla == "131049"


def test_un_segundo_fallido_no_pisa_el_primer_motivo() -> None:
    mensaje = _saliente()
    mensaje.marcar_entrega(EstadoEntrega.FALLIDO, motivo="131047")

    assert mensaje.marcar_entrega(EstadoEntrega.FALLIDO, motivo="131026") is False

    assert mensaje.motivo_de_falla == "131047"


def test_el_motivo_solo_se_guarda_cuando_el_estado_es_fallido() -> None:
    mensaje = _saliente()

    mensaje.marcar_entrega(EstadoEntrega.ENTREGADO, motivo="131047")

    assert mensaje.motivo_de_falla is None


def test_el_motivo_se_acota_al_largo_de_la_columna() -> None:
    mensaje = _saliente()

    mensaje.marcar_entrega(EstadoEntrega.FALLIDO, motivo="x" * 500)

    assert mensaje.motivo_de_falla == "x" * LARGO_MAXIMO_MOTIVO_DE_FALLA


def test_un_mensaje_sin_estado_acepta_el_primero() -> None:
    mensaje = _saliente(None)

    assert mensaje.marcar_entrega(EstadoEntrega.ENVIADO) is True
