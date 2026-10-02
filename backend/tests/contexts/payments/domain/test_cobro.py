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

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.domain.cobro import (
    MENSAJE_FECHA_ANTERIOR_AL_PAGO,
    MENSAJE_FECHA_FUTURA,
    MENSAJE_MONTO_NO_POSITIVO,
    MENSAJE_MOTIVO_CORTO,
    MENSAJE_PAGADO_NO_CANCELABLE,
    MENSAJE_REEMBOLSO_EN_PROCESO,
    MENSAJE_REEMBOLSO_EXCEDIDO,
    MENSAJE_REEMBOLSO_MANUAL_SOLO_TRANSFERENCIA,
    MENSAJE_REEMBOLSO_POR_API_SOLO_LINK,
    MENSAJE_SIN_CONCEPTO,
    MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN,
    Cobro,
    EstadoCobro,
    LinkDePago,
    MedioDePago,
    redondear,
)
from cheatsheet.contexts.payments.domain.reembolso import OrigenDeReembolso, Reembolso
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
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
    assert cobro.fecha_pago == AHORA
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

CLAVE = UUID("11111111-1111-4111-8111-111111111111")
USUARIO = UsuarioId(UUID("22222222-2222-4222-8222-222222222222"))


def _confirmar(
    cobro: Cobro, monto: str, *, mp_refund_id: str | None = "ref-1", fecha: datetime | None = None
) -> Reembolso:
    return cobro.confirmar_reembolso(
        reembolso_id=uuid4(),
        monto=Decimal(monto),
        mp_refund_id=mp_refund_id,
        fecha=fecha,
        ahora=AHORA,
    )


def _reembolsar_por_api(cobro: Cobro, monto: str) -> Reembolso:
    cobro.solicitar_reembolso(monto=Decimal(monto), clave=CLAVE, ahora=AHORA)
    return _confirmar(cobro, monto)


def _por_transferencia() -> Cobro:
    cobro = _cobro()
    cobro.medio_de_pago = MedioDePago.TRANSFERENCIA
    cobro.aprobar(payment_id="op-1", ahora=AHORA)
    return cobro


def _manual(cobro: Cobro, monto: str, *, dia: date | None = None) -> Reembolso:
    return cobro.registrar_reembolso_manual(
        reembolso_id=uuid4(),
        monto=Decimal(monto),
        dia=dia or date(2026, 9, 7),
        referencia="OP-123",
        motivo="Devolucion por transferencia",
        usuario_id=USUARIO,
        ahora=AHORA,
    )


def test_pedir_un_reembolso_no_cambia_el_estado() -> None:
    """**Decisión D27.** El cobro sigue `APROBADO` mientras la solicitud está en vuelo.

    Es lo que hace que un rechazo no tenga nada que revertir: nunca se fue de donde estaba.
    """
    cobro = _pagado()

    pedido = cobro.solicitar_reembolso(monto=Decimal("500.00"), clave=CLAVE, ahora=AHORA)

    assert pedido == Decimal("500.00")
    assert _estado(cobro) is EstadoCobro.APROBADO
    assert cobro.reembolso_en_proceso
    # Lo que hace posible reintentar sin duplicar: el monto y la clave quedan en el cobro.
    assert cobro.reembolso_solicitado_monto == Decimal("500.00")
    assert cobro.reembolso_clave_idempotencia == CLAVE
    assert cobro.reembolso_mp_refund_id is None


def test_un_reembolso_parcial_confirmado_deja_el_cobro_reembolsado_parcialmente() -> None:
    """Caso 1: el estado sale del acumulado, no del hecho de haber reembolsado."""
    cobro = _pagado()

    fila = _reembolsar_por_api(cobro, "400.00")

    assert _estado(cobro) is EstadoCobro.REEMBOLSADO_PARCIAL
    assert cobro.monto_reembolsado == Decimal("400.00")
    assert cobro.pendiente_de_reembolso == Decimal("600.00")
    assert not cobro.reembolso_en_proceso
    assert cobro.reembolso_clave_idempotencia is None
    assert fila.origen is OrigenDeReembolso.API_MERCADOPAGO
    assert fila.monto == Decimal("400.00")
    assert fila.mp_refund_id == "ref-1"
    assert fila.registrado_por is None


def test_un_segundo_reembolso_que_completa_el_monto_lo_deja_reembolsado() -> None:
    cobro = _pagado()
    _reembolsar_por_api(cobro, "400.00")

    _reembolsar_por_api(cobro, "600.00")

    assert _estado(cobro) is EstadoCobro.REEMBOLSADO
    assert cobro.monto_reembolsado == Decimal("1000.00")
    assert not cobro.admite_reembolso


def test_no_se_reembolsa_mas_de_lo_que_falta_devolver() -> None:
    """Caso 2, con el texto de la historia. Devolver de más es plata de otra cuenta."""
    cobro = _pagado()
    _reembolsar_por_api(cobro, "400.00")

    with pytest.raises(EntradaInvalida) as exc:
        cobro.solicitar_reembolso(monto=Decimal("600.01"), clave=CLAVE, ahora=AHORA)

    assert str(exc.value) == MENSAJE_REEMBOLSO_EXCEDIDO
    assert MENSAJE_REEMBOLSO_EXCEDIDO == (
        "El monto a reembolsar no puede superar el monto pendiente de reembolso del cobro."
    )
    assert not cobro.reembolso_en_proceso


def test_un_monto_no_positivo_no_se_reembolsa() -> None:
    cobro = _pagado()

    with pytest.raises(EntradaInvalida) as exc:
        cobro.solicitar_reembolso(monto=Decimal("0"), clave=CLAVE, ahora=AHORA)

    assert str(exc.value) == MENSAJE_MONTO_NO_POSITIVO


def test_el_monto_pedido_se_redondea_una_sola_vez() -> None:
    cobro = _pagado()

    pedido = cobro.solicitar_reembolso(monto=Decimal("0.005"), clave=CLAVE, ahora=AHORA)

    assert pedido == Decimal("0.01")


def test_se_puede_pedir_otro_reembolso_sobre_uno_parcial() -> None:
    """Caso 3: `REEMBOLSADO_PARCIAL` admite reembolso."""
    cobro = _pagado()
    _reembolsar_por_api(cobro, "400.00")

    pedido = cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)

    assert pedido == Decimal("100.00")


def test_no_se_pide_reembolso_de_lo_que_no_esta_pagado_o_ya_se_devolvio_entero() -> None:
    """Caso 3: pendiente, cancelado y reembolsado, con el texto de la historia."""
    pendiente = _cobro()
    cancelado = _cobro()
    cancelado.cancelar(motivo="Ya no corresponde cobrarlo", ahora=AHORA)
    reembolsado = _pagado()
    _reembolsar_por_api(reembolsado, "1000.00")

    for cobro in (pendiente, cancelado, reembolsado):
        with pytest.raises(InvarianteViolada) as exc:
            cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)
        assert str(exc.value) == MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN


def test_con_un_reembolso_en_vuelo_no_se_admite_otro() -> None:
    """Caso 4: la solicitud en vuelo es el mutex del reembolso por API."""
    cobro = _pagado()
    cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)

    with pytest.raises(InvarianteViolada) as exc:
        cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=uuid4(), ahora=AHORA)

    assert str(exc.value) == MENSAJE_REEMBOLSO_EN_PROCESO
    # La clave original sigue siendo la que se reintenta.
    assert cobro.reembolso_clave_idempotencia == CLAVE


def test_por_api_solo_se_reembolsa_un_cobro_pagado_por_link() -> None:
    """Caso 5: una transferencia no tiene API a la que pedirle nada."""
    cobro = _por_transferencia()

    with pytest.raises(InvarianteViolada) as exc:
        cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)

    assert str(exc.value) == MENSAJE_REEMBOLSO_POR_API_SOLO_LINK


def test_el_registro_manual_es_solo_para_transferencias() -> None:
    """Caso 5: el dinero de un link lo informa MercadoPago, y contarlo dos veces es peor."""
    cobro = _pagado()

    with pytest.raises(InvarianteViolada) as exc:
        _manual(cobro, "100.00")

    assert str(exc.value) == MENSAJE_REEMBOLSO_MANUAL_SOLO_TRANSFERENCIA
    assert cobro.monto_reembolsado == Decimal("0.00")


def test_un_reembolso_rechazado_deja_estado_y_acumulado_intactos() -> None:
    """Caso 6, RN-03. **No hay transición porque no hubo cambio de estado.**"""
    for previo in (None, "400.00"):
        cobro = _pagado()
        if previo is not None:
            _reembolsar_por_api(cobro, previo)
        estado, acumulado = cobro.estado, cobro.monto_reembolsado
        cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)

        cobro.rechazar_reembolso(AHORA)

        assert _estado(cobro) is estado
        assert cobro.monto_reembolsado == acumulado
        assert not cobro.reembolso_en_proceso
        assert cobro.reembolso_clave_idempotencia is None
        assert cobro.reembolso_solicitado_monto is None


def test_sin_solicitud_en_vuelo_no_se_confirma_nada() -> None:
    """Es lo que hace idempotente la confirmación: la segunda ya no tiene qué confirmar."""
    cobro = _pagado()
    cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)
    _confirmar(cobro, "100.00")

    with pytest.raises(InvarianteViolada):
        _confirmar(cobro, "100.00")

    assert cobro.monto_reembolsado == Decimal("100.00")


def test_una_confirmacion_mayor_al_pendiente_no_se_registra_y_sigue_en_vuelo() -> None:
    """Caso 15: MercadoPago dice haber devuelto más de lo que el cobro admite."""
    cobro = _pagado()
    cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)

    with pytest.raises(EntradaInvalida):
        _confirmar(cobro, "1000.01")

    assert cobro.monto_reembolsado == Decimal("0.00")
    assert cobro.reembolso_en_proceso


def test_una_solicitud_en_vuelo_puede_recordar_el_id_de_mercadopago() -> None:
    cobro = _pagado()
    cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)

    cobro.registrar_id_de_reembolso("ref-9", AHORA)

    assert cobro.reembolso_mp_refund_id == "ref-9"
    assert cobro.reembolso_en_proceso


def test_diez_centavos_mas_veinte_centavos_acumulan_treinta() -> None:
    """Caso 8: `Decimal`, nunca `0.30000000000000004`."""
    cobro = _por_transferencia()

    _manual(cobro, "0.10")
    _manual(cobro, "0.20")

    assert cobro.monto_reembolsado == Decimal("0.30")


def test_la_fecha_de_la_api_se_usa_si_es_plausible_y_si_no_la_de_la_confirmacion() -> None:
    plausible = AHORA - timedelta(minutes=10)
    for fecha, esperada in (
        (plausible, plausible),
        (None, AHORA),
        (AHORA.replace(tzinfo=None), AHORA),  # sin zona horaria
        (AHORA + timedelta(hours=1), AHORA),  # del futuro
        (AHORA - timedelta(days=30), AHORA),  # anterior al pago (hace una hora)
    ):
        cobro = _cobro()
        cobro.aprobar(payment_id="pago-1", ahora=AHORA - timedelta(hours=1))
        cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)

        assert _confirmar(cobro, "100.00", fecha=fecha).fecha_devolucion == esperada


def test_un_reembolso_manual_guarda_el_dia_a_las_doce_de_argentina() -> None:
    """Caso 9, P8: mediodía argentino = 15:00 UTC, del mismo día en las dos grillas."""
    cobro = _por_transferencia()

    fila = _manual(cobro, "250.00", dia=date(2026, 9, 7))

    assert fila.fecha_devolucion == datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
    assert fila.origen is OrigenDeReembolso.MANUAL
    assert fila.registrado_por == USUARIO
    assert fila.referencia == "OP-123"
    assert _estado(cobro) is EstadoCobro.REEMBOLSADO_PARCIAL


def test_una_fecha_manual_del_futuro_o_anterior_al_pago_se_rechaza() -> None:
    """Caso 9. El día de hoy sí vale; mañana no; antes del pago tampoco."""
    cobro = _por_transferencia()

    _manual(cobro, "10.00", dia=date(2026, 9, 7))
    with pytest.raises(EntradaInvalida) as futura:
        _manual(cobro, "10.00", dia=date(2026, 9, 8))
    with pytest.raises(EntradaInvalida) as anterior:
        _manual(cobro, "10.00", dia=date(2026, 9, 6))

    assert str(futura.value) == MENSAJE_FECHA_FUTURA
    assert str(anterior.value) == MENSAJE_FECHA_ANTERIOR_AL_PAGO
    assert cobro.monto_reembolsado == Decimal("10.00")


def test_el_dia_de_hoy_se_mide_en_argentina_y_no_en_utc() -> None:
    """A las 01:00 UTC del 8 todavía es 7 en Argentina (22:00): el 8 sigue siendo futuro."""
    cobro = _por_transferencia()
    tarde = datetime(2026, 9, 8, 1, 0, tzinfo=UTC)

    with pytest.raises(EntradaInvalida):
        cobro.registrar_reembolso_manual(
            reembolso_id=uuid4(),
            monto=Decimal("10.00"),
            dia=date(2026, 9, 8),
            referencia=None,
            motivo="Devolucion por transferencia",
            usuario_id=USUARIO,
            ahora=tarde,
        )


def test_un_reembolso_manual_exige_motivo_y_no_pasa_del_pendiente() -> None:
    cobro = _por_transferencia()

    with pytest.raises(EntradaInvalida):
        cobro.registrar_reembolso_manual(
            reembolso_id=uuid4(),
            monto=Decimal("10.00"),
            dia=date(2026, 9, 7),
            referencia=None,
            motivo="   ",
            usuario_id=USUARIO,
            ahora=AHORA,
        )
    with pytest.raises(EntradaInvalida) as exc:
        _manual(cobro, "1000.01")

    assert str(exc.value) == MENSAJE_REEMBOLSO_EXCEDIDO
    assert cobro.monto_reembolsado == Decimal("0.00")


def test_corregir_un_reembolso_manual_agrega_una_fila_negativa_que_baja_el_estado() -> None:
    """Caso 7, P5: la corrección anula la fila entera y el estado se deriva del acumulado."""
    cobro = _por_transferencia()
    completo = _manual(cobro, "700.00")
    resto = _manual(cobro, "300.00")
    assert _estado(cobro) is EstadoCobro.REEMBOLSADO

    primera = cobro.corregir_reembolso(
        resto,
        reembolso_id=uuid4(),
        ya_corregido=False,
        motivo="Se cargo por error",
        usuario_id=USUARIO,
        ahora=AHORA,
    )
    assert _estado(cobro) is EstadoCobro.REEMBOLSADO_PARCIAL
    segunda = cobro.corregir_reembolso(
        completo,
        reembolso_id=uuid4(),
        ya_corregido=False,
        motivo="Tambien por error",
        usuario_id=USUARIO,
        ahora=AHORA,
    )

    assert _estado(cobro) is EstadoCobro.APROBADO
    assert cobro.monto_reembolsado == Decimal("0.00")
    assert primera.monto == Decimal("-300.00")
    assert primera.corrige_a == resto.id
    assert primera.es_correccion
    assert segunda.monto == Decimal("-700.00")


def test_no_se_corrige_dos_veces_ni_una_correccion_ni_una_fila_de_la_api() -> None:
    """Caso 7. Las filas de la API no se corrigen: MercadoPago es la fuente de verdad."""
    manual_cobro = _por_transferencia()
    original = _manual(manual_cobro, "300.00")
    correccion = manual_cobro.corregir_reembolso(
        original,
        reembolso_id=uuid4(),
        ya_corregido=False,
        motivo="Se cargo por error",
        usuario_id=USUARIO,
        ahora=AHORA,
    )
    por_api = _pagado()
    de_la_api = _reembolsar_por_api(por_api, "100.00")
    _manual(manual_cobro, "300.00")

    for cobro, fila, ya in (
        (manual_cobro, original, True),
        (manual_cobro, correccion, False),
        (por_api, de_la_api, False),
    ):
        acumulado = cobro.monto_reembolsado
        with pytest.raises(InvarianteViolada):
            cobro.corregir_reembolso(
                fila,
                reembolso_id=uuid4(),
                ya_corregido=ya,
                motivo="Otro intento",
                usuario_id=USUARIO,
                ahora=AHORA,
            )
        assert cobro.monto_reembolsado == acumulado


def test_una_correccion_exige_motivo() -> None:
    cobro = _por_transferencia()
    original = _manual(cobro, "300.00")

    with pytest.raises(EntradaInvalida):
        cobro.corregir_reembolso(
            original,
            reembolso_id=uuid4(),
            ya_corregido=False,
            motivo="",
            usuario_id=USUARIO,
            ahora=AHORA,
        )

    assert cobro.monto_reembolsado == Decimal("300.00")


def test_un_cobro_parcialmente_reembolsado_tampoco_se_cancela() -> None:
    cobro = _pagado()
    _reembolsar_por_api(cobro, "100.00")

    with pytest.raises(InvarianteViolada) as exc:
        cobro.cancelar(motivo="Ya no corresponde cobrarlo", ahora=AHORA)

    assert str(exc.value) == MENSAJE_PAGADO_NO_CANCELABLE


def test_los_reembolsados_no_reciben_recordatorios() -> None:
    """Caso 18 (RN-12): por construcción, porque no están abiertos."""
    parcial = _pagado()
    _reembolsar_por_api(parcial, "100.00")
    total = _pagado()
    _reembolsar_por_api(total, "1000.00")

    assert not parcial.recibe_recordatorios
    assert not total.recibe_recordatorios
    assert not parcial.esta_abierto


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


# --------------------------------------------------------------- el pago huerfano


def test_un_pago_sobre_un_cobro_cancelado_se_anota_sin_mover_el_estado() -> None:
    """HU-E6-04. Misma forma que `solicitar_reembolso` (D27): un hecho sin transicion.

    El cobro no resucita. Alguien lo dio de baja con un motivo escrito, y `CANCELADO ->
    APROBADO` no esta en la tabla de transiciones justamente por eso.
    """
    cobro = _cobro()
    cobro.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)

    cobro.registrar_pago_huerfano(payment_id="pago-1", ahora=AHORA)

    assert _estado(cobro) is EstadoCobro.CANCELADO
    assert cobro.mp_payment_id == "pago-1"
    assert cobro.tiene_pago_huerfano


def test_un_cobro_abierto_no_puede_tener_un_pago_huerfano() -> None:
    """Un pendiente que recibe plata se aprueba; para eso esta `aprobar`."""
    cobro = _cobro()

    with pytest.raises(InvarianteViolada):
        cobro.registrar_pago_huerfano(payment_id="pago-1", ahora=AHORA)


def test_un_segundo_pago_huerfano_no_pisa_al_primero() -> None:
    """El `mp_payment_id` es la clave de idempotencia: perderlo seria perder el rastro."""
    cobro = _cobro()
    cobro.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)
    cobro.registrar_pago_huerfano(payment_id="pago-1", ahora=AHORA)

    with pytest.raises(InvarianteViolada):
        cobro.registrar_pago_huerfano(payment_id="pago-2", ahora=AHORA)

    assert cobro.mp_payment_id == "pago-1"


def test_un_cancelado_sin_pago_no_es_un_pago_huerfano() -> None:
    """Lo normal: se cancela y no entra nada. La pantalla no tiene que decir nada."""
    cobro = _cobro()
    cobro.cancelar(motivo="Se cargo por duplicado", ahora=AHORA)

    assert not cobro.tiene_pago_huerfano


def test_un_cobro_aprobado_no_es_un_pago_huerfano() -> None:
    """Tiene `mp_payment_id`, pero esta imputado a su deuda: es lo contrario del caso."""
    cobro = _cobro()
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)

    assert not cobro.tiene_pago_huerfano


# ---------------------------------------------------------- cuándo y cómo se pagó (D91)


def _con_link() -> Cobro:
    cobro = _cobro()
    cobro.asignar_link(UN_LINK, AHORA)
    return cobro


def test_aprobar_con_la_fecha_de_mercadopago_la_guarda_como_cierta() -> None:
    """El pago se ubica en el período en que el cliente pagó, no en el que lo procesamos."""
    cobro = _con_link()
    aprobado_el = AHORA + timedelta(hours=1)

    cobro.aprobar(payment_id="pago-1", ahora=AHORA + timedelta(days=2), fecha_pago=aprobado_el)

    assert cobro.fecha_pago == aprobado_el
    assert cobro.fecha_pago_aproximada is False
    assert cobro.medio_de_pago is MedioDePago.LINK_MERCADOPAGO
    assert cobro.numero_de_operacion is None


def test_la_fecha_informada_con_otro_offset_se_guarda_en_utc() -> None:
    cobro = _con_link()
    en_buenos_aires = timezone(timedelta(hours=-3))
    informada = datetime(2026, 9, 7, 10, 0, tzinfo=en_buenos_aires)  # 13:00 UTC

    cobro.aprobar(payment_id="pago-1", ahora=AHORA + timedelta(hours=2), fecha_pago=informada)

    assert cobro.fecha_pago == datetime(2026, 9, 7, 13, 0, tzinfo=UTC)
    assert cobro.fecha_pago is not None
    assert cobro.fecha_pago.utcoffset() == timedelta(0)


def test_aprobar_sin_fecha_usa_el_momento_y_la_marca_aproximada() -> None:
    cobro = _con_link()

    cobro.aprobar(payment_id="pago-1", ahora=AHORA)

    assert cobro.fecha_pago == AHORA
    assert cobro.fecha_pago_aproximada is True


@pytest.mark.parametrize(
    "informada",
    [
        pytest.param(AHORA.replace(tzinfo=None), id="sin-zona-horaria"),
        pytest.param(AHORA + timedelta(hours=1, minutes=6), id="en-el-futuro"),
        pytest.param(AHORA - timedelta(seconds=1), id="anterior-a-la-creacion"),
    ],
)
def test_una_fecha_implausible_se_ignora_y_queda_aproximada(informada: datetime) -> None:
    """Una fecha equivocada mueve plata de período: ante la duda, no se la toma por cierta."""
    cobro = _con_link()
    ahora = AHORA + timedelta(hours=1)

    cobro.aprobar(payment_id="pago-1", ahora=ahora, fecha_pago=informada)

    assert cobro.fecha_pago == ahora
    assert cobro.fecha_pago_aproximada is True


def test_la_tolerancia_de_reloj_de_cinco_minutos_es_inclusiva() -> None:
    cobro = _con_link()
    informada = AHORA + timedelta(minutes=5)

    cobro.aprobar(payment_id="pago-1", ahora=AHORA, fecha_pago=informada)

    assert cobro.fecha_pago == informada
    assert cobro.fecha_pago_aproximada is False


def test_aprobar_dos_veces_sigue_rechazado_y_no_toca_la_fecha() -> None:
    cobro = _con_link()
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)

    with pytest.raises(InvarianteViolada):
        cobro.aprobar(
            payment_id="pago-2",
            ahora=AHORA + timedelta(days=1),
            fecha_pago=AHORA + timedelta(hours=1),
        )

    assert cobro.fecha_pago == AHORA
    assert cobro.fecha_pago_aproximada is True
    assert cobro.mp_payment_id == "pago-1"


def test_el_pago_huerfano_no_escribe_fecha_ni_medio() -> None:
    cobro = _cobro()
    cobro.cancelar(motivo="El cliente ya pago por transferencia", ahora=AHORA)

    cobro.registrar_pago_huerfano(payment_id="pago-1", ahora=AHORA)

    assert _estado(cobro) is EstadoCobro.CANCELADO
    assert cobro.fecha_pago is None
    assert cobro.fecha_pago_aproximada is False
    assert cobro.medio_de_pago is MedioDePago.LINK_MERCADOPAGO


def test_un_cobro_nuevo_no_tiene_fecha_de_pago() -> None:
    cobro = _cobro()

    assert cobro.fecha_pago is None
    assert cobro.fecha_pago_aproximada is False


def test_el_reembolso_pedido_devuelve_monto_y_clave_y_levanta_si_no_hay_ninguno() -> None:
    cobro = _pagado()
    with pytest.raises(InvarianteViolada):
        _ = cobro.reembolso_pedido

    cobro.solicitar_reembolso(monto=Decimal("100.00"), clave=CLAVE, ahora=AHORA)

    assert cobro.reembolso_pedido == (Decimal("100.00"), CLAVE)


def test_no_se_recuerda_un_id_de_reembolso_sin_una_solicitud_en_vuelo() -> None:
    cobro = _pagado()

    with pytest.raises(InvarianteViolada):
        cobro.registrar_id_de_reembolso("ref-1", AHORA)


def test_una_segunda_correccion_de_la_misma_fila_no_deja_el_acumulado_negativo() -> None:
    """La red de seguridad del dominio si alguien saltea `ya_corregido`: el acumulado no baja de
    cero (la base lo repite con `ck_cobro_reembolso` y con el índice único de `corrige_a`)."""
    cobro = _por_transferencia()
    original = _manual(cobro, "300.00")
    cobro.corregir_reembolso(
        original,
        reembolso_id=uuid4(),
        ya_corregido=False,
        motivo="Se cargo por error",
        usuario_id=USUARIO,
        ahora=AHORA,
    )

    with pytest.raises(InvarianteViolada):
        cobro.corregir_reembolso(
            original,
            reembolso_id=uuid4(),
            ya_corregido=False,
            motivo="Otra vez",
            usuario_id=USUARIO,
            ahora=AHORA,
        )

    assert cobro.monto_reembolsado == Decimal("0.00")
