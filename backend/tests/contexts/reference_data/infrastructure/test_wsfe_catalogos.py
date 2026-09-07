"""El ACL contra los `FEParamGet*` de WSFEv1 (HS-T4), sin tocar la red.

Misma técnica y misma razón que el test de `billing`: `httpx.MockTransport` donde estaría
el socket, sobres SOAP grabados, y **el foco puesto en el lector**. Un parser roto acá no
tira excepción — devuelve un catálogo vacío, y un catálogo vacío es indistinguible de «ARCA
todavía no publicó nada». La emisión del épico 5 valida contra esta tabla, así que un
catálogo vacío por un parser roto es una emisión que valida contra la nada.

Este módulo llegó tarde: la unidad `parametros-fiscales` probó el adaptador simulado y no
el real. El de `billing`, escrito con la misma forma, tenía un bug en esa parte no probada.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from cheatsheet.contexts.reference_data.application.errors import CatalogoNoDisponible
from cheatsheet.contexts.reference_data.domain.parametro import TipoCatalogoFiscal
from cheatsheet.contexts.reference_data.infrastructure.wsfe_catalogos import (
    OPERACIONES,
    CatalogosDeWsfe,
    CredencialDeWsfe,
)
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(UUID("3f1c2b8e-0000-4000-8000-000000000060"))
CREDENCIAL = CredencialDeWsfe(token="un-token", sign="una-firma", cuit="30712345674")
URL = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"


def _sobre(cuerpo: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<soap:Body><Resp xmlns="http://ar.gov.afip.dif.FEV1/">{cuerpo}</Resp></soap:Body>'
        "</soap:Envelope>"
    )


#: Los códigos reales de ARCA. Si alguien los "corrige", esto se cae.
POR_ETIQUETA = {
    "CbteTipo": "<CbteTipo><Id>1</Id><Desc>Factura A</Desc></CbteTipo>"
    "<CbteTipo><Id>6</Id><Desc>Factura B</Desc></CbteTipo>",
    "IvaTipo": "<IvaTipo><Id>5</Id><Desc>21%</Desc></IvaTipo>"
    "<IvaTipo><Id>3</Id><Desc>0%</Desc></IvaTipo>",
    "DocTipo": "<DocTipo><Id>80</Id><Desc>CUIT</Desc></DocTipo>",
    "Moneda": "<Moneda><Id>PES</Id><Desc>Pesos Argentinos</Desc></Moneda>",
}

FALLA = (
    '<?xml version="1.0"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
    "<soap:Fault><faultcode>soap:Server</faultcode>"
    "<faultstring>Token invalido</faultstring></soap:Fault>"
    "</soap:Body></soap:Envelope>"
)


def _responder_todo(pedido: httpx.Request) -> httpx.Response:
    """Contesta según la `SOAPAction`, que es lo que distingue una operación de otra."""
    accion = pedido.headers.get("SOAPAction", "")
    for operacion, _, etiqueta in OPERACIONES:
        if accion.endswith(operacion):
            return httpx.Response(200, text=_sobre(POR_ETIQUETA[etiqueta]))
    return httpx.Response(200, text=_sobre(""))  # pragma: no cover - no deberia pasar


def _cliente(manejar: object) -> CatalogosDeWsfe:
    return CatalogosDeWsfe(
        url=URL,
        credenciales={EMPRESA: CREDENCIAL},
        transporte=httpx.MockTransport(manejar),  # type: ignore[arg-type]
    )


async def test_trae_los_cuatro_catalogos_con_los_codigos_reales_de_arca() -> None:
    entradas = await _cliente(_responder_todo).obtener(empresa_id=EMPRESA)

    por_tipo = {(e.tipo, e.codigo): e.valor for e in entradas}
    assert por_tipo[(TipoCatalogoFiscal.TIPO_COMPROBANTE, "1")] == "Factura A"
    assert por_tipo[(TipoCatalogoFiscal.TIPO_COMPROBANTE, "6")] == "Factura B"
    assert por_tipo[(TipoCatalogoFiscal.ALICUOTA_IVA, "5")] == "21%"
    assert por_tipo[(TipoCatalogoFiscal.TIPO_DOCUMENTO, "80")] == "CUIT"
    assert por_tipo[(TipoCatalogoFiscal.MONEDA, "PES")] == "Pesos Argentinos"


async def test_cada_operacion_lee_solo_su_propia_etiqueta() -> None:
    """Las cuatro respuestas viajan por el mismo sobre y se distinguen por el nombre del
    nodo. Un lector que no filtrara por etiqueta mezclaría alícuotas con monedas."""
    todo_junto = "".join(POR_ETIQUETA.values())

    entradas = await _cliente(lambda _: httpx.Response(200, text=_sobre(todo_junto))).obtener(
        empresa_id=EMPRESA
    )

    # Cada una de las cuatro pasadas se queda con lo suyo: nada se duplica de tipo.
    alicuotas = {e.codigo for e in entradas if e.tipo is TipoCatalogoFiscal.ALICUOTA_IVA}
    assert alicuotas == {"5", "3"}


async def test_un_espacio_de_nombres_distinto_igual_se_lee() -> None:
    def movido(pedido: httpx.Request) -> httpx.Response:
        original = _responder_todo(pedido)
        return httpx.Response(200, text=original.text.replace("dif.FEV1/", "dif.FEV1/v2"))

    entradas = await _cliente(movido).obtener(empresa_id=EMPRESA)

    assert any(e.codigo == "1" for e in entradas)


async def test_una_entrada_sin_descripcion_se_descarta_en_vez_de_guardarse_vacia() -> None:
    """Un parámetro con `valor` vacío es peor que no tenerlo: se guarda, queda vigente, y
    la emisión lo encuentra."""

    def incompleto(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_sobre("<CbteTipo><Id>1</Id><Desc></Desc></CbteTipo>"),
        )

    entradas = await _cliente(incompleto).obtener(empresa_id=EMPRESA)

    assert entradas == ()


async def test_un_catalogo_rechazado_no_se_lleva_puestos_a_los_otros_tres() -> None:
    """HS-T4 RN-04 por entrada: una falla en `FEParamGetTiposIva` no puede vaciar los tipos
    de comprobante que sí contestaron."""

    def uno_falla(pedido: httpx.Request) -> httpx.Response:
        if pedido.headers.get("SOAPAction", "").endswith("FEParamGetTiposIva"):
            return httpx.Response(200, text=FALLA)
        return _responder_todo(pedido)

    entradas = await _cliente(uno_falla).obtener(empresa_id=EMPRESA)

    tipos = {e.tipo for e in entradas}
    assert TipoCatalogoFiscal.ALICUOTA_IVA not in tipos
    assert TipoCatalogoFiscal.TIPO_COMPROBANTE in tipos


async def test_arca_inalcanzable_es_un_error_y_no_un_catalogo_vacio() -> None:
    """La diferencia importa: un catálogo vacío se guardaría como «ARCA no tiene nada»."""

    def caer(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin ruta al host")

    with pytest.raises(CatalogoNoDisponible):
        await _cliente(caer).obtener(empresa_id=EMPRESA)


async def test_una_empresa_sin_ticket_no_sale_a_la_red() -> None:
    def nunca(_: httpx.Request) -> httpx.Response:  # pragma: no cover - no debe llamarse
        raise AssertionError("no deberia haber salido a la red")

    cliente = CatalogosDeWsfe(url=URL, credenciales={}, transporte=httpx.MockTransport(nunca))

    with pytest.raises(CatalogoNoDisponible):
        await cliente.obtener(empresa_id=EMPRESA)
