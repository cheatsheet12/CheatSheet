"""El ACL contra `FEParamGetPtosVenta` (HU-E5-05 RN-03), sin tocar la red.

`httpx.MockTransport` se pone donde estaría el socket y se responden sobres SOAP grabados
—la misma técnica que los tests de contrato de WSAA, y por la misma razón: homologación
también tiene límites de uso, y un test que consume cupo rompe el test siguiente.

**Lo que se prueba acá es el lector**, que es la pieza que se equivoca en silencio. Un
parser roto no tira excepción: devuelve cero puntos, y cero puntos se lee exactamente igual
que «ARCA no te habilitó ninguno». La activación se bloquea y nadie sabe por qué.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from cheatsheet.contexts.billing.application.errors import ArcaNoDisponible
from cheatsheet.contexts.billing.infrastructure.habilitacion import (
    HabilitacionEnArca,
)
from cheatsheet.platform.wsfe import CredencialDeWsfe
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(UUID("3f1c2b8e-0000-4000-8000-000000000050"))
CREDENCIAL = CredencialDeWsfe(token="un-token", sign="una-firma", cuit="30712345674")
URL = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"


class CredencialesFalsas:
    """Un resolutor de credenciales que no habla con `integrations`.

    `sin_credencial` es lo que prueba que el adaptador **no sale a la red** cuando la
    empresa no tiene ARCA conectado: el error se levanta antes del socket.
    """

    def __init__(self, *, sin_credencial: bool = False, numero: int = 1) -> None:
        self.sin_credencial = sin_credencial
        self.numero = numero

    async def para(self, empresa_id: EmpresaId) -> CredencialDeWsfe:
        del empresa_id
        if self.sin_credencial:
            raise ArcaNoDisponible("La empresa no tiene conectada la integracion con ARCA")
        return CREDENCIAL

    async def numero_de_punto(self, empresa_id: EmpresaId, punto_id: UUID) -> int | None:
        del empresa_id, punto_id
        return self.numero


def _sobre(cuerpo: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<soap:Body>{cuerpo}</soap:Body></soap:Envelope>"
    )


#: La forma real de la respuesta de ARCA, con su espacio de nombres propio.
RESPUESTA = _sobre(
    '<FEParamGetPtosVentaResponse xmlns="http://ar.gov.afip.dif.FEV1/">'
    "<FEParamGetPtosVentaResult><ResultGet>"
    "<PtoVenta><Nro>1</Nro><EmisionTipo>CAE</EmisionTipo><Bloqueado>N</Bloqueado></PtoVenta>"
    "<PtoVenta><Nro>2</Nro><EmisionTipo>CAE</EmisionTipo><Bloqueado>N</Bloqueado></PtoVenta>"
    "<PtoVenta><Nro>99</Nro><EmisionTipo>CAE</EmisionTipo><Bloqueado>S</Bloqueado></PtoVenta>"
    "</ResultGet></FEParamGetPtosVentaResult>"
    "</FEParamGetPtosVentaResponse>"
)

FALLA = _sobre(
    "<soap:Fault><faultcode>soap:Server</faultcode>"
    "<faultstring>Token invalido</faultstring></soap:Fault>"
)


def _cliente(respuesta: httpx.Response) -> HabilitacionEnArca:
    return HabilitacionEnArca(
        url=URL,
        credenciales=CredencialesFalsas(),
        transporte=httpx.MockTransport(lambda _: respuesta),
    )


def _ok(texto: str) -> httpx.Response:
    return httpx.Response(200, text=texto)


async def test_lee_los_puntos_que_arca_reporta() -> None:
    puntos = await _cliente(_ok(RESPUESTA)).puntos_habilitados(empresa_id=EMPRESA)

    assert [p.numero for p in puntos] == [1, 2, 99]
    assert [p.puede_usarse for p in puntos] == [True, True, False]


async def test_un_espacio_de_nombres_distinto_igual_se_lee() -> None:
    """ARCA ya movió el espacio de nombres de estas respuestas antes.

    Un parser anclado a uno fallaría con «no hay puntos», que es indistinguible de «ARCA no
    te habilitó ninguno» — y el resultado sería una activación bloqueada sin explicación.
    """
    movido = RESPUESTA.replace("http://ar.gov.afip.dif.FEV1/", "http://ar.gov.afip.dif.FEV1/v2")

    puntos = await _cliente(_ok(movido)).puntos_habilitados(empresa_id=EMPRESA)

    assert [p.numero for p in puntos] == [1, 2, 99]


@pytest.mark.parametrize("valor", ["S", "s", "X", "true", ""])
async def test_todo_lo_que_no_sea_n_se_lee_como_bloqueado(valor: str) -> None:
    """La dirección conservadora, a propósito.

    Un falso «bloqueado» cuesta un mensaje al soporte. Un falso «habilitado» cuesta una
    factura rechazada con un código que habla de otra cosa.
    """
    cuerpo = _sobre(
        '<FEParamGetPtosVentaResponse xmlns="http://ar.gov.afip.dif.FEV1/">'
        f"<PtoVenta><Nro>3</Nro><Bloqueado>{valor}</Bloqueado></PtoVenta>"
        "</FEParamGetPtosVentaResponse>"
    )

    puntos = await _cliente(_ok(cuerpo)).puntos_habilitados(empresa_id=EMPRESA)

    assert len(puntos) == 1
    assert not puntos[0].puede_usarse


async def test_un_punto_sin_numero_usable_se_descarta_en_vez_de_romper() -> None:
    cuerpo = _sobre(
        '<FEParamGetPtosVentaResponse xmlns="http://ar.gov.afip.dif.FEV1/">'
        "<PtoVenta><Nro>abc</Nro><Bloqueado>N</Bloqueado></PtoVenta>"
        "<PtoVenta><Nro>4</Nro><Bloqueado>N</Bloqueado></PtoVenta>"
        "</FEParamGetPtosVentaResponse>"
    )

    puntos = await _cliente(_ok(cuerpo)).puntos_habilitados(empresa_id=EMPRESA)

    assert [p.numero for p in puntos] == [4]


async def test_una_falla_soap_es_arca_diciendo_que_no_y_devuelve_vacio() -> None:
    """Una falla **es** una respuesta. Reportar cero puntos bloquea la activación, que es
    lo que «ese punto no es tuyo» tiene que hacer — y no es lo mismo que no poder preguntar.
    """
    puntos = await _cliente(_ok(FALLA)).puntos_habilitados(empresa_id=EMPRESA)

    assert puntos == ()


async def test_arca_inalcanzable_es_un_error_distinto() -> None:
    def caer(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin ruta al host")

    cliente = HabilitacionEnArca(
        url=URL, credenciales=CredencialesFalsas(), transporte=httpx.MockTransport(caer)
    )

    with pytest.raises(ArcaNoDisponible):
        await cliente.puntos_habilitados(empresa_id=EMPRESA)


async def test_una_empresa_sin_ticket_no_sale_a_la_red() -> None:
    def nunca(_: httpx.Request) -> httpx.Response:  # pragma: no cover - no debe llamarse
        raise AssertionError("no deberia haber salido a la red")

    cliente = HabilitacionEnArca(
        url=URL,
        credenciales=CredencialesFalsas(sin_credencial=True),
        transporte=httpx.MockTransport(nunca),
    )

    with pytest.raises(ArcaNoDisponible):
        await cliente.puntos_habilitados(empresa_id=EMPRESA)


async def test_el_sobre_lleva_el_token_la_firma_y_el_cuit() -> None:
    enviados: list[bytes] = []

    def espiar(pedido: httpx.Request) -> httpx.Response:
        enviados.append(pedido.content)
        return _ok(RESPUESTA)

    cliente = HabilitacionEnArca(
        url=URL, credenciales=CredencialesFalsas(), transporte=httpx.MockTransport(espiar)
    )
    await cliente.puntos_habilitados(empresa_id=EMPRESA)

    cuerpo = enviados[0].decode()
    assert "<ar:Token>un-token</ar:Token>" in cuerpo
    assert "<ar:Sign>una-firma</ar:Sign>" in cuerpo
    assert "<ar:Cuit>30712345674</ar:Cuit>" in cuerpo
