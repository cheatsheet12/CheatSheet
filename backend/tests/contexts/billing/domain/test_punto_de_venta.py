"""El agregado `PuntoDeVenta` y los códigos de ARCA que lleva encima.

Todo esto es sincrónico y puro: la numeración por tipo, la nota de crédito que corresponde
a cada factura, y los seis códigos publicados. Vive separado de los casos de uso porque no
necesita ni repositorio ni red, y porque es lo que hay que leer para entender por qué un
comprobante sale con el tipo que sale.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.contexts.billing.infrastructure.habilitacion import HabilitacionSimulada
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


def test_la_numeracion_es_independiente_por_tipo() -> None:
    """RN-02. Cada tipo lleva su propia serie: ARCA las cuenta por separado."""
    punto = PuntoDeVenta(id=uuid4(), empresa_id=EMPRESA, numero=1, created_at=AHORA)

    assert punto.siguiente_numero(TipoComprobante.FACTURA_A) == 1
    assert punto.siguiente_numero(TipoComprobante.FACTURA_B) == 1
    assert punto.siguiente_numero(TipoComprobante.FACTURA_A) == 2
    assert punto.ultimo_numero(TipoComprobante.FACTURA_C) == 0


def test_devolver_un_numero_solo_funciona_con_el_ultimo() -> None:
    """Para el caso angosto en que el pedido nunca salió: nada se consumió.

    Un comprobante que ARCA **recibió** y rechazó se queda con su número para siempre —
    la serie tiene un hueco y está bien, porque ARCA cuenta lo que le mandaron.
    """
    punto = PuntoDeVenta(id=uuid4(), empresa_id=EMPRESA, numero=1, created_at=AHORA)
    punto.siguiente_numero(TipoComprobante.FACTURA_B)
    segundo = punto.siguiente_numero(TipoComprobante.FACTURA_B)

    punto.devolver_numero(TipoComprobante.FACTURA_B, segundo)
    assert punto.ultimo_numero(TipoComprobante.FACTURA_B) == 1

    with pytest.raises(InvarianteViolada):
        punto.devolver_numero(TipoComprobante.FACTURA_B, segundo)


def test_cada_factura_tiene_su_nota_de_credito_de_la_misma_letra() -> None:
    """HU-E5-04 RN-02, determinado por el sistema y nunca elegido por el usuario."""
    assert TipoComprobante.FACTURA_A.nota_de_credito is TipoComprobante.NOTA_CREDITO_A
    assert TipoComprobante.FACTURA_B.nota_de_credito is TipoComprobante.NOTA_CREDITO_B
    assert TipoComprobante.FACTURA_C.nota_de_credito is TipoComprobante.NOTA_CREDITO_C

    with pytest.raises(InvarianteViolada):
        _ = TipoComprobante.NOTA_CREDITO_A.nota_de_credito


def test_los_codigos_de_arca_son_los_publicados() -> None:
    """No son secuenciales, y equivocarse en uno emite un comprobante de otro tipo."""
    assert TipoComprobante.FACTURA_A.codigo_arca == 1
    assert TipoComprobante.NOTA_CREDITO_A.codigo_arca == 3
    assert TipoComprobante.FACTURA_B.codigo_arca == 6
    assert TipoComprobante.NOTA_CREDITO_B.codigo_arca == 8
    assert TipoComprobante.FACTURA_C.codigo_arca == 11
    assert TipoComprobante.NOTA_CREDITO_C.codigo_arca == 13


@pytest.mark.parametrize("numero", [0, -1, 100_000])
def test_un_numero_fuera_del_rango_de_arca_es_rechazado(numero: int) -> None:
    with pytest.raises(EntradaInvalida):
        PuntoDeVenta(id=uuid4(), empresa_id=EMPRESA, numero=numero, created_at=AHORA)


def test_la_habilitacion_simulada_es_rechazada_en_produccion() -> None:
    """Se activarían puntos que ARCA nunca habilitó, y se descubre al facturar."""
    with pytest.raises(RuntimeError):
        HabilitacionSimulada(Entorno.PRODUCTION)
