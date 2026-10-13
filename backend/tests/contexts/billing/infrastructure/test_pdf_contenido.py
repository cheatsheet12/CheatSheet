"""Lo que **dice** el papel del comprobante (HU-E5-02 RN-03).

En su propio módulo porque son sincrónicos y los de la caché no: un
`pytestmark = pytest.mark.asyncio` a nivel de módulo marca también a los sincrónicos y
pytest avisa por cada uno.

Se afirma sobre el **contenido**, no sobre el dibujo. Un test que comparara la maquetación
se caería cada vez que alguien mueva un milímetro y no diría nada sobre si el comprobante
está bien —lo fiscal es la fila y su CAE—, así que `pdf.py` separa las dos cosas y esto
prueba la mitad donde equivocarse importa.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from cheatsheet.contexts.billing.domain.comprobante import (
    CAE,
    AlicuotaIVA,
    Comprobante,
    EstadoComprobante,
    ItemDeComprobante,
    Receptor,
)
from cheatsheet.contexts.billing.domain.leyendas import LEYENDA_MONOTRIBUTO
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.contexts.billing.infrastructure.pdf import (
    PIE,
    TIPO_DE_CONTENIDO,
    clave_de,
    datos_del_encabezado,
    datos_del_receptor,
    lineas_de_leyenda,
    renderizar,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid.uuid4())
UN_CAE = CAE(codigo="75123456789012", vence_el=date(2026, 9, 17))


def comprobante(*, autorizado: bool = True) -> Comprobante:
    documento = Comprobante(
        id=uuid.uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid.uuid4(),
        punto_de_venta_id=uuid.uuid4(),
        tipo=TipoComprobante.FACTURA_A,
        receptor=Receptor(
            nombre="Acme SA",
            cuit="30712345671",
            condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
            domicilio="Av. Siempreviva 742",
        ),
        emisor_condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
        created_at=AHORA,
    )
    documento.agregar_item(
        ItemDeComprobante(
            id=uuid.uuid4(),
            descripcion="Corte de pelo",
            cantidad=Decimal("2"),
            precio_unitario=Decimal("1000.00"),
            alicuota_iva=AlicuotaIVA.GENERAL,
        )
    )
    if autorizado:
        documento.validar()
        documento.enviar_a_arca(123, AHORA)
        documento.autorizar(UN_CAE)
    return documento


def test_lo_que_sale_es_un_pdf() -> None:
    """La firma del formato, y nada sobre el diseño."""
    contenido = renderizar(comprobante(), 1)

    assert contenido.startswith(b"%PDF-")
    assert contenido.rstrip().endswith(b"%%EOF")


def test_el_encabezado_lleva_el_numero_como_lo_imprime_arca() -> None:
    datos = dict(datos_del_encabezado(comprobante(), 1))

    assert datos["Numero"] == "0001-00000123"
    assert datos["CAE"] == "75123456789012"
    assert datos["Vencimiento del CAE"] == "2026-09-17"


def test_un_comprobante_sin_cae_no_inventa_uno() -> None:
    """Un guión y no una cadena vacía: un campo en blanco se lee como un dato perdido."""
    datos = dict(datos_del_encabezado(comprobante(autorizado=False), 1))

    assert datos["CAE"] == "-"
    assert datos["Vencimiento del CAE"] == "-"


def test_el_receptor_sale_de_la_copia_del_comprobante() -> None:
    """Desnormalizado a propósito: el papel dice lo que era cierto el día de la emisión."""
    datos = dict(datos_del_receptor(comprobante()))

    assert datos["Razon social"] == "Acme SA"
    assert datos["CUIT"] == "30712345671"
    assert datos["Condicion de IVA"] == "RESPONSABLE INSCRIPTO"
    assert datos["Domicilio"] == "Av. Siempreviva 742"


def test_el_pie_dice_que_el_papel_no_es_el_comprobante_fiscal() -> None:
    """Sin esto, un PDF guardado en una carpeta parece tan válido como el registro."""
    assert "El comprobante fiscal es el registro electronico y su CAE" in PIE


def test_la_clave_separa_por_empresa() -> None:
    """El prefijo de una empresa nunca contiene el papeleo de otra, ni por accidente."""
    documento = comprobante()

    clave = clave_de(documento)

    assert clave.startswith(f"comprobantes/{EMPRESA}/")
    assert clave.endswith(".pdf")


def test_el_tipo_de_contenido_es_el_de_un_pdf() -> None:
    assert TIPO_DE_CONTENIDO == "application/pdf"


def test_un_comprobante_sin_autorizar_no_es_descargable() -> None:
    """La regla vive en el agregado, no en la ruta: un solo lugar donde puede estar mal.

    Un PDF de algo que ARCA rechazó sería un papel idéntico a una factura que no lo es.
    """
    borrador = comprobante(autorizado=False)

    assert not borrador.es_descargable
    assert borrador.estado is EstadoComprobante.BORRADOR


def test_la_a_a_un_monotributista_imprime_la_leyenda() -> None:
    """HU-E5-03 RN-13: la leyenda va en el PDF, no solo en pantalla."""
    documento = comprobante()
    documento.receptor = Receptor(
        nombre="Cliente Ficticio", cuit="20222222223", condicion_iva=CondicionIVA.MONOTRIBUTO
    )

    lineas = lineas_de_leyenda(documento)

    assert " ".join(lineas) == LEYENDA_MONOTRIBUTO
    assert renderizar(documento, 1).startswith(b"%PDF-")


def test_la_a_a_un_inscripto_no_imprime_leyenda() -> None:
    assert lineas_de_leyenda(comprobante()) == []
