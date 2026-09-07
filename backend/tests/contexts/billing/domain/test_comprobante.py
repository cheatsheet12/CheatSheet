"""El agregado `Comprobante`: la plata, los tipos y la máquina de estados.

Tres bloques, y los tres prueban cosas que si fallan cuestan un comprobante mal emitido:

1. **El redondeo** (D15). Se redondea por ítem y los totales son sumas de valores ya
   redondeados. El caso que lo prueba de verdad es el que da distinto si se redondea al
   final, y está acá abajo con números concretos.
2. **La tabla de tipos** (RN-01, D16). Un tipo inválido para el par de condiciones de IVA
   es un comprobante que ARCA rechaza.
3. **Las transiciones**. Sobre todo las que **no** existen: `AUTORIZADO` es terminal, y
   esa ausencia es lo que hace idempotente la reconciliación de D17.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.billing.domain.comprobante import (
    CAE,
    MENSAJE_PRECIO_NO_POSITIVO,
    MENSAJE_SIN_ITEMS,
    MENSAJE_TIPO_INVALIDO,
    AlicuotaIVA,
    Comprobante,
    EstadoComprobante,
    ItemDeComprobante,
    Receptor,
    redondear,
    tipos_permitidos,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.fiscal import CondicionIVA

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
RI = CondicionIVA.RESPONSABLE_INSCRIPTO
CF = CondicionIVA.CONSUMIDOR_FINAL


def _item(
    *,
    cantidad: str = "1",
    precio: str = "1000.00",
    alicuota: AlicuotaIVA = AlicuotaIVA.GENERAL,
) -> ItemDeComprobante:
    return ItemDeComprobante(
        id=uuid4(),
        descripcion="Corte de pelo",
        cantidad=Decimal(cantidad),
        precio_unitario=Decimal(precio),
        alicuota_iva=alicuota,
    )


def _comprobante(
    *,
    tipo: TipoComprobante = TipoComprobante.FACTURA_A,
    emisor: CondicionIVA = RI,
    receptor: CondicionIVA = RI,
) -> Comprobante:
    return Comprobante(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        punto_de_venta_id=uuid4(),
        tipo=tipo,
        receptor=Receptor(nombre="Acme SA", cuit="30712345674", condicion_iva=receptor),
        emisor_condicion_iva=emisor,
        created_at=AHORA,
    )


# --------------------------------------------------------------------------- la plata


def test_el_subtotal_de_un_item_se_redondea_a_dos_decimales() -> None:
    item = _item(cantidad="3", precio="333.333")

    assert item.subtotal == Decimal("1000.00")


def test_el_iva_se_calcula_sobre_el_subtotal_ya_redondeado() -> None:
    """No sobre el producto crudo, y la diferencia es un centavo.

    `3 x 333.333 = 999.999`. Redondeado da `1000.00`, y el 21 % de eso es `210.00`. El
    21 % del crudo es `209.99979`, que redondea a `210.00` también — pero en otros números
    no, y ARCA rechaza el comprobante con un código que no menciona el centavo.
    """
    item = _item(cantidad="3", precio="333.333")

    assert item.iva == Decimal("210.00")
    assert item.total == Decimal("1210.00")


def test_los_totales_cierran_contra_la_suma_de_items() -> None:
    """D15: **la propiedad que ARCA valida.** Tres ítems elegidos para que redondear al
    final dé distinto que redondear por ítem."""
    comprobante = _comprobante()
    for precio in ("10.005", "10.005", "10.005"):
        comprobante.agregar_item(_item(precio=precio))

    # Por ítem: 10.01 x 3 = 30.03. Al final: 30.015 → 30.02. Un centavo de diferencia.
    assert comprobante.subtotal == Decimal("30.03")
    assert comprobante.subtotal + comprobante.total_iva == comprobante.total


def test_una_alicuota_cero_no_suma_iva() -> None:
    comprobante = _comprobante()
    comprobante.agregar_item(_item(alicuota=AlicuotaIVA.CERO))

    assert comprobante.total_iva == Decimal("0.00")
    assert comprobante.total == comprobante.subtotal


def test_las_alicuotas_llevan_los_codigos_reales_de_arca() -> None:
    """3, 4 y 5 son los `Id` publicados. Adivinar uno emite con la alícuota equivocada."""
    assert AlicuotaIVA.CERO.codigo_arca == 3
    assert AlicuotaIVA.REDUCIDA.codigo_arca == 4
    assert AlicuotaIVA.GENERAL.codigo_arca == 5


def test_la_alicuota_se_reconstruye_desde_la_columna_numericamente() -> None:
    """`NUMERIC(5, 4)` vuelve como `Decimal("0.1050")`, que no es `"0.105"` como texto."""
    assert AlicuotaIVA.desde_tasa(Decimal("0.1050")) is AlicuotaIVA.REDUCIDA


def test_redondear_usa_half_up_y_no_el_banquero() -> None:
    """`ROUND_HALF_EVEN`, el default de Python, redondearía `0.005` a `0.00`."""
    assert redondear(Decimal("0.005")) == Decimal("0.01")
    assert redondear(Decimal("0.015")) == Decimal("0.02")


def test_un_precio_no_positivo_se_rechaza_con_el_texto_de_la_historia() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        _item(precio="0")

    assert str(exc.value) == MENSAJE_PRECIO_NO_POSITIVO


def test_el_saldo_pendiente_arranca_igual_al_total() -> None:
    """HU-E5-03 RN-06. Se registra acá; el épico 6 es el que lo consume."""
    comprobante = _comprobante()
    comprobante.agregar_item(_item())

    assert comprobante.saldo_pendiente == comprobante.total


# --------------------------------------------------------------------------- los tipos


@pytest.mark.parametrize(
    ("emisor", "receptor", "esperado"),
    [
        (RI, RI, TipoComprobante.FACTURA_A),
        (RI, CF, TipoComprobante.FACTURA_B),
        (RI, CondicionIVA.MONOTRIBUTO, TipoComprobante.FACTURA_B),
        (CondicionIVA.MONOTRIBUTO, RI, TipoComprobante.FACTURA_C),
        (CondicionIVA.EXENTO, CF, TipoComprobante.FACTURA_C),
    ],
)
def test_la_tabla_de_tipos_es_la_del_regimen(
    emisor: CondicionIVA, receptor: CondicionIVA, esperado: TipoComprobante
) -> None:
    """RN-01 y D16. Un Responsable Inscripto factura A a otro RI y B a todo el resto; un
    Monotributista o un Exento facturan C a cualquiera."""
    assert esperado in tipos_permitidos(emisor=emisor, receptor=receptor)


def test_un_consumidor_final_no_puede_emitir() -> None:
    """No es un rol del sistema: es que un consumidor final no factura."""
    assert tipos_permitidos(emisor=CF, receptor=RI) == frozenset()


def test_emitir_una_factura_a_a_un_consumidor_final_no_valida() -> None:
    comprobante = _comprobante(tipo=TipoComprobante.FACTURA_A, emisor=RI, receptor=CF)
    comprobante.agregar_item(_item())

    with pytest.raises(EntradaInvalida) as exc:
        comprobante.validar()

    assert str(exc.value) == MENSAJE_TIPO_INVALIDO


def test_validar_sin_items_usa_el_texto_de_la_historia() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        _comprobante().validar()

    assert str(exc.value) == MENSAJE_SIN_ITEMS


# --------------------------------------------------------------------- las transiciones


def _estado(comprobante: Comprobante) -> EstadoComprobante:
    """El estado, leído a través de una función.

    Afirmar sobre el atributo directamente angosta su tipo en mypy, y mypy no lo vuelve a
    ensanchar después de un método que lo muta — así que la afirmación siguiente de la
    misma prueba le parece imposible y falla el gate. Es una limitación del narrowing, no
    del código.
    """
    return comprobante.estado


def _validado() -> Comprobante:
    comprobante = _comprobante()
    comprobante.agregar_item(_item())
    comprobante.validar()
    return comprobante


def test_el_camino_feliz_va_de_borrador_a_autorizado() -> None:
    comprobante = _validado()
    # Leído a una variable y no afirmado sobre el atributo: mypy angosta el tipo del
    # atributo y no lo vuelve a ensanchar después de un método que lo muta, así que la
    # afirmación siguiente le parecería imposible.
    assert _estado(comprobante) is EstadoComprobante.VALIDADO

    comprobante.enviar_a_arca(numero=1, ahora=AHORA)
    assert comprobante.esta_en_vuelo
    assert comprobante.numero == 1
    assert comprobante.fecha_emision == AHORA

    comprobante.autorizar(CAE(codigo="75123456789012", vence_el=date(2026, 9, 17)))
    assert _estado(comprobante) is EstadoComprobante.AUTORIZADO
    assert comprobante.es_descargable


def test_un_comprobante_autorizado_no_se_vuelve_a_autorizar() -> None:
    """**Esta ausencia es lo que hace idempotente la reconciliación de D17.**

    Un barrido que encuentra un comprobante ya autorizado no puede pisarle el CAE con un
    segundo. Sin esta transición prohibida, un reintento que llegue tarde reemplazaría el
    código legal por otro.
    """
    comprobante = _validado()
    comprobante.enviar_a_arca(numero=1, ahora=AHORA)
    primero = CAE(codigo="75123456789012", vence_el=date(2026, 9, 17))
    comprobante.autorizar(primero)

    with pytest.raises(InvarianteViolada):
        comprobante.autorizar(CAE(codigo="99999999999999", vence_el=date(2026, 9, 20)))

    assert comprobante.cae == primero


def test_un_comprobante_en_vuelo_no_se_puede_modificar() -> None:
    """HU-E5-02 RN-01, aplicado también al estado en que no sabemos qué pasó.

    Cambiarle los ítems a un comprobante que ARCA quizá ya autorizó haría que nuestra copia
    diga algo distinto de la legal.
    """
    comprobante = _validado()
    comprobante.enviar_a_arca(numero=1, ahora=AHORA)

    with pytest.raises(InvarianteViolada):
        comprobante.agregar_item(_item())


def test_editar_un_validado_lo_devuelve_a_borrador() -> None:
    """Lo que se validó ya no es lo que hay: revalidar es obligatorio."""
    comprobante = _validado()

    comprobante.agregar_item(_item())

    assert comprobante.estado is EstadoComprobante.BORRADOR


def test_un_rechazado_se_puede_corregir_y_volver_a_emitir() -> None:
    """Un rechazo es una **respuesta**: ARCA no registró nada y se puede reintentar."""
    comprobante = _validado()
    comprobante.enviar_a_arca(numero=1, ahora=AHORA)
    comprobante.rechazar("Error 10016: el comprobante no cumple la resolucion vigente")

    assert _estado(comprobante) is EstadoComprobante.RECHAZADO
    assert not comprobante.es_descargable

    comprobante.validar()
    assert _estado(comprobante) is EstadoComprobante.VALIDADO


def test_no_se_puede_saltear_arca() -> None:
    """Autorizar sin haber enviado sería un CAE que nadie pidió."""
    comprobante = _validado()

    with pytest.raises(InvarianteViolada):
        comprobante.autorizar(CAE(codigo="75123456789012", vence_el=date(2026, 9, 17)))


def test_un_anulado_es_el_final_del_camino() -> None:
    comprobante = _validado()
    comprobante.enviar_a_arca(numero=1, ahora=AHORA)
    comprobante.autorizar(CAE(codigo="75123456789012", vence_el=date(2026, 9, 17)))
    comprobante.anular()

    with pytest.raises(InvarianteViolada):
        comprobante.anular()


def test_autorizar_limpia_un_rechazo_anterior() -> None:
    """Si se corrigió y salió, el motivo viejo en pantalla sería una mentira."""
    comprobante = _validado()
    comprobante.enviar_a_arca(numero=1, ahora=AHORA)
    comprobante.rechazar("Error 10016: algo")
    comprobante.validar()
    comprobante.enviar_a_arca(numero=2, ahora=AHORA)
    comprobante.autorizar(CAE(codigo="75123456789012", vence_el=date(2026, 9, 17)))

    assert comprobante.motivo_de_rechazo is None
