"""El agregado `Cobro`: la plata y la máquina de estados que la mantiene honesta.

Lo que se prueba acá es lo que, si falla, cuesta dinero de verdad:

1. **`APROBADO` es terminal salvo por el reembolso.** Es la primera línea de la idempotencia
   del webhook (D20) y lo que impide que una notificación repetida dé por saldada una deuda
   dos veces.
2. **Un pagado no se cancela** (HU-E6-04 RN-01), y el mensaje dice qué hacer en su lugar.
3. **El reembolso pedido no cambia el estado** (D27). Un rechazo tiene que dejar el cobro
   donde estaba, y la forma de garantizarlo es que nunca se haya ido.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.payments.domain.cobro import (
    MENSAJE_MONTO_NO_POSITIVO,
    MENSAJE_MOTIVO_CORTO,
    MENSAJE_PAGADO_NO_CANCELABLE,
    MENSAJE_REEMBOLSO_EXCEDIDO,
    MENSAJE_SIN_CONCEPTO,
    MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN,
    Cobro,
    EstadoCobro,
    LinkDePago,
    redondear,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
UN_LINK = LinkDePago(preference_id="pref-1", url="https://mp.com/checkout/pref-1")


def _cobro(monto: str = "1000.00", *, vence_en_dias: int = 30) -> Cobro:
    return Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal(monto),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=vence_en_dias),
        created_at=AHORA,
    )


def _pagado() -> Cobro:
    cobro = _cobro()
    cobro.asignar_link(UN_LINK, AHORA)
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    return cobro


def _estado(cobro: Cobro) -> EstadoCobro:
    """El estado, leído a través de una función.

    Afirmar sobre el atributo angosta su tipo en mypy y no lo vuelve a ensanchar después de un
    método que lo muta, así que la afirmación siguiente de la misma prueba le parecería
    imposible. Es una limitación del narrowing, no del código.
    """
    return cobro.estado


# --------------------------------------------------------------------------- la plata


def test_el_monto_se_redondea_a_dos_decimales_al_construir() -> None:
    assert _cobro("1000.005").monto == Decimal("1000.01")


def test_redondear_usa_half_up_y_no_el_del_banquero() -> None:
    """El default de Python, `ROUND_HALF_EVEN`, redondearía `0.005` a `0.00`."""
    assert redondear(Decimal("0.005")) == Decimal("0.01")
    assert redondear(Decimal("0.015")) == Decimal("0.02")


def test_un_monto_no_positivo_usa_el_texto_de_la_historia() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        _cobro("0")

    assert str(exc.value) == MENSAJE_MONTO_NO_POSITIVO


def test_un_cobro_sin_concepto_usa_el_texto_de_la_historia() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        Cobro(
            id=uuid4(),
            empresa_id=EMPRESA,
            cliente_id=uuid4(),
            monto=Decimal("100.00"),
            descripcion="   ",
            vence_el=AHORA,
            created_at=AHORA,
        )

    assert str(exc.value) == MENSAJE_SIN_CONCEPTO


# --------------------------------------------------------------------------- el link


def test_un_cobro_tiene_un_solo_link_activo_a_la_vez() -> None:
    """RN-04. Reemplazar el objeto **es** invalidar el anterior: nunca hubo dos."""
    cobro = _cobro()
    cobro.asignar_link(UN_LINK, AHORA)
    segundo = LinkDePago(preference_id="pref-2", url="https://mp.com/checkout/pref-2")

    cobro.asignar_link(segundo, AHORA)

    assert cobro.link == segundo
    assert cobro.tiene_link_activo


def test_un_cobro_cancelado_no_admite_un_link_nuevo() -> None:
    cobro = _cobro()
    cobro.cancelar(motivo="El cliente devolvio el producto", ahora=AHORA)

    with pytest.raises(InvarianteViolada):
        cobro.asignar_link(UN_LINK, AHORA)


def test_un_link_sin_preferencia_o_sin_url_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida):
        LinkDePago(preference_id="", url="https://mp.com/x")


# ---------------------------------------------------------------------- las transiciones


def test_el_camino_feliz_va_de_pendiente_a_aprobado() -> None:
    cobro = _cobro()
    cobro.asignar_link(UN_LINK, AHORA)

    cobro.aprobar(payment_id="pago-1", ahora=AHORA)

    assert _estado(cobro) is EstadoCobro.APROBADO
    assert cobro.mp_payment_id == "pago-1"
    assert cobro.pagado_en == AHORA
    assert not cobro.recibe_recordatorios


def test_un_cobro_aprobado_no_se_aprueba_dos_veces() -> None:
    """**La primera línea de la idempotencia del webhook** (D20).

    La tabla de transiciones no tiene `APROBADO → APROBADO`, así que una notificación
    repetida no puede dar por saldada la deuda otra vez. El índice único sobre
    `mp_payment_id` es la segunda línea.
    """
    cobro = _pagado()

    with pytest.raises(InvarianteViolada):
        cobro.aprobar(payment_id="pago-2", ahora=AHORA)

    assert cobro.mp_payment_id == "pago-1"


def test_un_vencido_todavia_se_puede_pagar() -> None:
    """MercadoPago acepta el pago mientras la preferencia viva.

    Rechazarlo acá dejaría plata cobrada sin un cobro que la explique — que es peor que un
    link «vencido» que igual funcionó.
    """
    cobro = _cobro()
    cobro.asignar_link(UN_LINK, AHORA)
    cobro.vencer(AHORA)

    cobro.aprobar(payment_id="pago-1", ahora=AHORA)

    assert _estado(cobro) is EstadoCobro.APROBADO


def test_un_pagado_no_se_cancela_y_el_mensaje_dice_que_hacer() -> None:
    """HU-E6-04 RN-01, con el texto de la historia — que además ofrece la alternativa."""
    cobro = _pagado()

    with pytest.raises(InvarianteViolada) as exc:
        cobro.cancelar(motivo="Ya no corresponde cobrarlo", ahora=AHORA)

    assert str(exc.value) == MENSAJE_PAGADO_NO_CANCELABLE


def test_cancelar_exige_un_motivo_de_diez_caracteres() -> None:
    """RN-02. Diez no es una cifra mágica: es lo que hace que «ok» y «error» no pasen."""
    cobro = _cobro()

    with pytest.raises(EntradaInvalida) as exc:
        cobro.cancelar(motivo="ok", ahora=AHORA)

    assert str(exc.value) == MENSAJE_MOTIVO_CORTO
    assert _estado(cobro) is EstadoCobro.PENDIENTE


def test_cancelar_invalida_el_link_y_corta_los_recordatorios() -> None:
    """RN-03. Los recordatorios se cortan **por el estado**, no por una llamada aparte:
    HS-T3 no le manda a un `CANCELADO`."""
    cobro = _cobro()
    cobro.asignar_link(UN_LINK, AHORA)

    cobro.cancelar(motivo="El cliente devolvio el producto", ahora=AHORA)

    assert _estado(cobro) is EstadoCobro.CANCELADO
    # El link deja de estar activo sin que se borre la preferencia: invalidarlo es dejar de
    # ofrecerlo, no olvidar cuál era.
    assert not cobro.tiene_link_activo
    assert cobro.link is not None
    assert not cobro.recibe_recordatorios
    assert cobro.motivo_de_cancelacion == "El cliente devolvio el producto"


def test_un_cancelado_es_el_final_del_camino() -> None:
    cobro = _cobro()
    cobro.cancelar(motivo="Se dio de baja el servicio", ahora=AHORA)

    with pytest.raises(InvarianteViolada):
        cobro.aprobar(payment_id="pago-1", ahora=AHORA)


# --------------------------------------------------------------------------- el reembolso


def test_pedir_un_reembolso_no_cambia_el_estado() -> None:
    """**Decisión D27.** El cobro sigue `APROBADO` mientras la solicitud está en vuelo.

    Es lo que hace que un rechazo no tenga nada que revertir: nunca se fue de donde estaba.
    """
    cobro = _pagado()

    pedido = cobro.solicitar_reembolso(monto=Decimal("500.00"), ahora=AHORA)

    assert pedido == Decimal("500.00")
    assert _estado(cobro) is EstadoCobro.APROBADO
    assert cobro.reembolso_en_proceso


def test_un_reembolso_rechazado_deja_el_cobro_donde_estaba() -> None:
    """RN-03. **No hay transición porque no hubo cambio de estado.**"""
    cobro = _pagado()
    cobro.solicitar_reembolso(monto=Decimal("500.00"), ahora=AHORA)

    cobro.rechazar_reembolso(AHORA)

    assert _estado(cobro) is EstadoCobro.APROBADO
    assert not cobro.reembolso_en_proceso
    assert cobro.monto_reembolsado is None


def test_un_reembolso_confirmado_cierra_el_cobro() -> None:
    cobro = _pagado()
    cobro.solicitar_reembolso(monto=Decimal("500.00"), ahora=AHORA)

    cobro.confirmar_reembolso(monto=Decimal("500.00"), ahora=AHORA)

    assert _estado(cobro) is EstadoCobro.REEMBOLSADO
    assert cobro.monto_reembolsado == Decimal("500.00")
    assert not cobro.reembolso_en_proceso


def test_no_se_reembolsa_mas_de_lo_que_entro() -> None:
    """RN-02, con el texto de la historia. Devolver de más es plata de otra cuenta."""
    cobro = _pagado()

    with pytest.raises(EntradaInvalida) as exc:
        cobro.solicitar_reembolso(monto=Decimal("2000.00"), ahora=AHORA)

    assert str(exc.value) == MENSAJE_REEMBOLSO_EXCEDIDO


def test_solo_se_reembolsa_lo_que_esta_aprobado() -> None:
    cobro = _cobro()

    with pytest.raises(InvarianteViolada) as exc:
        cobro.solicitar_reembolso(monto=Decimal("100.00"), ahora=AHORA)

    assert str(exc.value) == MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN


# --------------------------------------------------------------------------- consultas


def test_estar_vencido_de_hecho_es_distinto_de_estarlo_de_derecho() -> None:
    """El hecho es del calendario; el estado es lo que el barrido escribió (D23).

    Entre los dos hay una ventana de minutos, y quien necesite el hecho tiene que poder
    preguntarlo sin esperar al barrido.
    """
    cobro = _cobro(vence_en_dias=1)
    despues = AHORA + timedelta(days=2)

    assert cobro.esta_vencido_a(despues)
    assert _estado(cobro) is EstadoCobro.PENDIENTE
    assert cobro.esta_abierto
