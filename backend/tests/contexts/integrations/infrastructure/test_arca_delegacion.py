"""Verificar la delegación del web service en CheatSheet (ADR-0014).

**Ninguno abre un socket**: `httpx.MockTransport` va donde iría WSFE. Lo que se juega es
qué respuesta de ARCA cuenta como «delegada»: solo los errores 600 y 601 dicen que el
certificado no puede hablar por esa CUIT; cualquier otra respuesta dice que sí.
"""

from __future__ import annotations

import httpx
import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
    TicketNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import MaterialDeConexion, TicketVigente
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_CUIT,
    CLAVE_ETIQUETA,
    EstadoDeConexion,
)
from cheatsheet.contexts.integrations.infrastructure.arca.delegacion import (
    MARCA_DE_DELEGACION,
    ConectorDelegacionArca,
    ConsultaDeDelegacion,
    VerificadorDelegacionArca,
)
from cheatsheet.platform.soap import ClienteSoap, ConfiguracionSoap

from tests.conftest import INSTANTE_FIJO

pytestmark = pytest.mark.asyncio

CUIT = "30000000015"
URL = "https://wsfe.test/service.asmx"


def _respuesta(cuerpo_interno: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=(
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            '<FECompUltimoAutorizadoResponse xmlns="http://ar.gov.afip.dif.FEV1/">'
            f"<FECompUltimoAutorizadoResult>{cuerpo_interno}</FECompUltimoAutorizadoResult>"
            "</FECompUltimoAutorizadoResponse></soap:Body></soap:Envelope>"
        ),
    )


def _con_error(codigo: str) -> httpx.Response:
    return _respuesta(f"<Errors><Err><Code>{codigo}</Code><Msg>algo</Msg></Err></Errors>")


class Tickets:
    def __init__(self, excepcion: Exception | None = None) -> None:
        self.excepcion = excepcion

    async def ejecutar(self, servicio: ServicioDeArca) -> TicketVigente:
        if self.excepcion is not None:
            raise self.excepcion
        return TicketVigente(
            servicio=servicio, contenido=b"el-token\nla-firma", expira_en=INSTANTE_FIJO
        )


class Grabadora:
    def __init__(self, respuesta: httpx.Response | Exception) -> None:
        self.respuesta = respuesta
        self.pedidos: list[httpx.Request] = []

    def transporte(self) -> httpx.MockTransport:
        def manejar(pedido: httpx.Request) -> httpx.Response:
            self.pedidos.append(pedido)
            if isinstance(self.respuesta, Exception):
                raise self.respuesta
            return self.respuesta

        return httpx.MockTransport(manejar)


def _consulta(grabadora: Grabadora, tickets: Tickets | None = None) -> ConsultaDeDelegacion:
    soap = ClienteSoap(
        ConfiguracionSoap(url=URL, timeout_segundos=1.0, max_intentos=1, espera_base=0.0),
        grabadora.transporte(),
    )
    return ConsultaDeDelegacion(soap, tickets or Tickets())


def _material(cuit: str = CUIT) -> MaterialDeConexion:
    return MaterialDeConexion(contenido=cuit.encode(), parametros={}, efimeros={})


async def test_una_cuit_delegada_conecta_y_guarda_solo_la_marca() -> None:
    grabadora = Grabadora(_respuesta("<CbteNro>0</CbteNro>"))

    resultado = await ConectorDelegacionArca(_consulta(grabadora)).conectar(_material())

    assert resultado.credencial == MARCA_DE_DELEGACION
    assert resultado.parametros[CLAVE_CUIT] == CUIT
    assert "30-00000001-5" in resultado.parametros[CLAVE_ETIQUETA]


async def test_el_pedido_lleva_el_token_de_plataforma_y_la_cuit_de_la_empresa() -> None:
    grabadora = Grabadora(_respuesta("<CbteNro>0</CbteNro>"))

    await ConectorDelegacionArca(_consulta(grabadora)).conectar(_material())

    cuerpo = grabadora.pedidos[0].content.decode()
    assert "<ar:Token>el-token</ar:Token>" in cuerpo
    assert "<ar:Sign>la-firma</ar:Sign>" in cuerpo
    assert f"<ar:Cuit>{CUIT}</ar:Cuit>" in cuerpo


@pytest.mark.parametrize("codigo", ["600", "601"])
async def test_sin_delegacion_arca_responde_600_o_601_y_se_rechaza(codigo: str) -> None:
    with pytest.raises(ConexionRechazada, match="no registra que la CUIT 30-00000001-5"):
        await ConectorDelegacionArca(_consulta(Grabadora(_con_error(codigo)))).conectar(_material())


async def test_otro_error_de_wsfe_igual_prueba_la_delegacion() -> None:
    """Un error sobre el punto de venta o el tipo dice que ARCA aceptó hablar por la CUIT."""
    resultado = await ConectorDelegacionArca(_consulta(Grabadora(_con_error("10015")))).conectar(
        _material()
    )

    assert resultado.parametros[CLAVE_CUIT] == CUIT


async def test_una_cuit_que_no_tiene_once_digitos_no_llega_a_arca() -> None:
    grabadora = Grabadora(_respuesta("<CbteNro>0</CbteNro>"))

    with pytest.raises(ConexionRechazada, match="no tiene un CUIT valido"):
        await ConectorDelegacionArca(_consulta(grabadora)).conectar(_material(""))

    assert grabadora.pedidos == []


async def test_wsfe_caido_no_es_un_rechazo() -> None:
    grabadora = Grabadora(httpx.ConnectError("sin red"))

    with pytest.raises(ProveedorNoDisponible):
        await ConectorDelegacionArca(_consulta(grabadora)).conectar(_material())


async def test_sin_ticket_de_plataforma_tampoco_es_un_rechazo() -> None:
    consulta = _consulta(Grabadora(_respuesta("")), Tickets(TicketNoDisponible("WSAA caido")))

    with pytest.raises(ProveedorNoDisponible):
        await ConectorDelegacionArca(consulta).conectar(_material())


async def test_la_verificacion_detecta_una_delegacion_revocada() -> None:
    verificador = VerificadorDelegacionArca(_consulta(Grabadora(_con_error("600"))))

    resultado = await verificador.verificar(MARCA_DE_DELEGACION, {CLAVE_CUIT: CUIT})

    assert resultado.estado is EstadoDeConexion.NO_CONECTADO


async def test_la_verificacion_de_una_delegacion_vigente_queda_conectada() -> None:
    verificador = VerificadorDelegacionArca(
        _consulta(Grabadora(_respuesta("<CbteNro>3</CbteNro>")))
    )

    resultado = await verificador.verificar(MARCA_DE_DELEGACION, {CLAVE_CUIT: CUIT})

    assert resultado.estado is EstadoDeConexion.CONECTADO


async def test_una_integracion_sin_cuit_pide_volver_a_verificar() -> None:
    verificador = VerificadorDelegacionArca(_consulta(Grabadora(_respuesta(""))))

    resultado = await verificador.verificar(MARCA_DE_DELEGACION, {})

    assert resultado.estado is EstadoDeConexion.ATENCION
