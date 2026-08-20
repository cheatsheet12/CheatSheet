"""Tests de contrato del padrón A5 de ARCA — casos 1 a 9, 13 y 14 del plan.

Payloads fijos y `httpx.MockTransport`: **ningún test toca la red** (regla del workflow,
paso 3). Lo que se fija acá es la forma del `getPersona` que ARCA devuelve y, sobre todo,
la traducción a `CondicionIVA` — que es la que después decide qué comprobante puede emitir
el épico 5. Un error en esa tabla no se ve hasta que sale una factura mal.
"""

from __future__ import annotations

import httpx
import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.domain.valores import CLAVE_CUIT
from cheatsheet.contexts.integrations.infrastructure.arca.padron import (
    ClientePadronA5,
    ConfiguracionPadron,
)
from cheatsheet.shared.fiscal import CondicionIVA

pytestmark = pytest.mark.asyncio

CONFIG = ConfiguracionPadron(url="https://padron.test/personaServiceA5", espera_base=0.0)
TICKET = b"un-token\nuna-firma"
PARAMETROS = {CLAVE_CUIT: "30111111117"}
CUIT_CONSULTADO = "20123456789"


def _sobre(cuerpo: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<soapenv:Body><personaReturn>{cuerpo}</personaReturn></soapenv:Body>"
        "</soapenv:Envelope>"
    )


def _falla(detalle: str, codigo: str = "soapenv:Server") -> str:
    return (
        '<?xml version="1.0"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soapenv:Body><soapenv:Fault>"
        f"<faultcode>{codigo}</faultcode><faultstring>{detalle}</faultstring>"
        "</soapenv:Fault></soapenv:Body></soapenv:Envelope>"
    )


EMPRESA_INSCRIPTA = _sobre(
    "<datosGenerales>"
    "<idPersona>20123456789</idPersona><estadoClave>ACTIVO</estadoClave>"
    "<razonSocial>PANADERIA DONA ROSA SRL</razonSocial>"
    "</datosGenerales>"
    "<datosRegimenGeneral><impuesto>"
    "<idImpuesto>30</idImpuesto><descripcionImpuesto>IVA</descripcionImpuesto>"
    "</impuesto></datosRegimenGeneral>"
)


class Secuencia:
    """Handler de `MockTransport`: contesta en orden y guarda lo que le pidieron.

    Guardar los pedidos no es contabilidad: es lo que permite afirmar que el reintento
    ocurrió tres veces y que el sobre llevaba el CUIT del certificado.
    """

    def __init__(self, respuestas: list[httpx.Response]) -> None:
        self.pendientes = list(respuestas)
        self.peticiones: list[httpx.Request] = []

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        return self.pendientes.pop(0) if len(self.pendientes) > 1 else self.pendientes[0]


def _con(respuestas: list[httpx.Response]) -> tuple[ClientePadronA5, Secuencia]:
    handler = Secuencia(respuestas)
    return ClientePadronA5(CONFIG, httpx.MockTransport(handler)), handler


async def test_un_cuit_conocido_devuelve_razon_social_y_condicion() -> None:
    """Caso 1. Lo que HU-E1-02 llama «autocompleta la condición IVA»."""
    cliente, _ = _con([httpx.Response(200, text=EMPRESA_INSCRIPTA)])

    datos = await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert datos is not None
    assert datos.razon_social == "PANADERIA DONA ROSA SRL"
    assert datos.condicion_iva is CondicionIVA.RESPONSABLE_INSCRIPTO
    assert datos.activo


async def test_monotributo_gana_sobre_la_lista_de_impuestos() -> None:
    """Caso 2. Un monotributista también figura con impuestos; el régimen manda."""
    cuerpo = _sobre(
        "<datosGenerales><estadoClave>ACTIVO</estadoClave>"
        "<apellido>PEREZ</apellido><nombre>JUAN</nombre></datosGenerales>"
        "<datosMonotributo><categoriaMonotributo>C</categoriaMonotributo>"
        "<impuesto><idImpuesto>30</idImpuesto></impuesto></datosMonotributo>"
    )
    cliente, _ = _con([httpx.Response(200, text=cuerpo)])

    datos = await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert datos is not None
    assert datos.condicion_iva is CondicionIVA.MONOTRIBUTO


async def test_iva_exento_se_traduce_a_exento() -> None:
    """Caso 4."""
    cuerpo = _sobre(
        "<datosGenerales><estadoClave>ACTIVO</estadoClave>"
        "<razonSocial>FUNDACION EJEMPLO</razonSocial></datosGenerales>"
        "<datosRegimenGeneral><impuesto><idImpuesto>32</idImpuesto></impuesto>"
        "</datosRegimenGeneral>"
    )
    cliente, _ = _con([httpx.Response(200, text=cuerpo)])

    datos = await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert datos is not None
    assert datos.condicion_iva is CondicionIVA.EXENTO


async def test_sin_impuestos_reconocibles_no_inventa_una_condicion() -> None:
    """Caso 5, y la regla del módulo: el silencio es mejor que una adivinanza.

    Una condición de IVA equivocada decide mal qué comprobante emite el épico 5. Cuando el
    padrón no alcanza para saberlo, elige la persona.
    """
    cuerpo = _sobre(
        "<datosGenerales><estadoClave>ACTIVO</estadoClave>"
        "<razonSocial>SIN IMPUESTOS SA</razonSocial></datosGenerales>"
        "<datosRegimenGeneral><impuesto><idImpuesto>11</idImpuesto></impuesto>"
        "</datosRegimenGeneral>"
    )
    cliente, _ = _con([httpx.Response(200, text=cuerpo)])

    datos = await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert datos is not None
    assert datos.condicion_iva is None
    assert datos.razon_social == "SIN IMPUESTOS SA"


async def test_persona_fisica_arma_la_razon_social_con_apellido_y_nombre() -> None:
    """Caso 6. ARCA llena un par o el otro, nunca los dos."""
    cuerpo = _sobre(
        "<datosGenerales><estadoClave>ACTIVO</estadoClave>"
        "<apellido>PEREZ</apellido><nombre>JUAN</nombre></datosGenerales>"
    )
    cliente, _ = _con([httpx.Response(200, text=cuerpo)])

    datos = await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert datos is not None
    assert datos.razon_social == "PEREZ JUAN"


async def test_un_cuit_dado_de_baja_se_informa_pero_no_desaparece() -> None:
    """Existe y no está activo. Son dos respuestas distintas y llevan a decisiones opuestas."""
    cuerpo = _sobre(
        "<datosGenerales><estadoClave>INACTIVO</estadoClave>"
        "<razonSocial>EX EMPRESA SRL</razonSocial></datosGenerales>"
    )
    cliente, _ = _con([httpx.Response(200, text=cuerpo)])

    datos = await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert datos is not None
    assert not datos.activo


async def test_la_falla_de_no_existe_devuelve_none_y_no_excepcion() -> None:
    """Caso 7, y el nudo del contrato.

    ARCA dice «no existe» con `soapenv:Server`, que para WSAA significa «tuve un mal
    momento». Mismo código, sentidos opuestos: por eso el transporte compartido no traduce
    y cada servicio decide.
    """
    cliente, _ = _con([httpx.Response(500, text=_falla("No existe persona con ese Id"))])

    datos = await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert datos is None


async def test_una_falla_de_autenticacion_sigue_siendo_un_error() -> None:
    """La contracara del caso 7: no todo `Fault` es un CUIT inexistente."""
    cliente, _ = _con(
        [
            httpx.Response(
                500, text=_falla("El certificado no esta habilitado", "cms.cert.untrusted")
            )
        ]
    )

    with pytest.raises(ConexionRechazada):
        await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)


async def test_un_5xx_sin_fault_reintenta_y_termina_en_no_disponible() -> None:
    """Caso 8. Tres intentos y ninguno es un rechazo del CUIT."""
    handler = Secuencia([httpx.Response(503, text="mantenimiento")])
    cliente = ClientePadronA5(CONFIG, httpx.MockTransport(handler))

    with pytest.raises(ProveedorNoDisponible):
        await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert len(handler.peticiones) == CONFIG.max_intentos


async def test_un_timeout_tambien_reintenta() -> None:
    """Caso 8, la otra mitad: la red que no contesta no es ARCA diciendo que no."""
    intentos: list[httpx.Request] = []

    def caerse(peticion: httpx.Request) -> httpx.Response:
        intentos.append(peticion)
        raise httpx.ConnectTimeout("sin respuesta")

    cliente = ClientePadronA5(CONFIG, httpx.MockTransport(caerse))

    with pytest.raises(ProveedorNoDisponible):
        await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    assert len(intentos) == CONFIG.max_intentos


async def test_un_xml_hostil_no_se_procesa() -> None:
    """Caso 9. La bomba de entidades que `defusedxml` rechaza, traducida a algo manejable.

    Sin la traducción, el rechazo escapa sin tipo y tumba lo que lo haya llamado — que es
    exactamente el defecto que un test de la unidad anterior destapó en `wsaa.py`.
    """
    bomba = (
        '<?xml version="1.0"?>'
        "<!DOCTYPE lol [<!ENTITY a 'aaaaaaaaaa'><!ENTITY b '&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;'>]>"
        "<personaReturn>&b;</personaReturn>"
    )
    cliente, _ = _con([httpx.Response(200, text=bomba)])

    with pytest.raises(ProveedorNoDisponible):
        await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)


async def test_el_pedido_declara_el_cuit_del_certificado_y_el_consultado() -> None:
    """Caso 13. Confundirlos devolvería los datos de la empresa equivocada."""
    handler = Secuencia([httpx.Response(200, text=EMPRESA_INSCRIPTA)])
    cliente = ClientePadronA5(CONFIG, httpx.MockTransport(handler))

    await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit="20-12345678-9")

    enviado = handler.peticiones[0].content.decode()
    assert "<cuitRepresentada>30111111117</cuitRepresentada>" in enviado
    assert "<idPersona>20123456789</idPersona>" in enviado
    assert "<token>un-token</token>" in enviado
    assert "<sign>una-firma</sign>" in enviado


async def test_sin_cuit_en_el_certificado_no_se_consulta() -> None:
    """ARCA rechaza un pedido que no dice quién pregunta, con un mensaje que despista."""
    cliente, _ = _con([httpx.Response(200, text=EMPRESA_INSCRIPTA)])

    with pytest.raises(ProveedorNoDisponible, match="no declara un CUIT"):
        await cliente.consultar(ticket=TICKET, parametros={}, cuit=CUIT_CONSULTADO)


async def test_un_ticket_sin_firma_se_rechaza_antes_de_salir() -> None:
    """El blob guardado son dos líneas. Si no lo son, el pedido no tiene sentido."""
    cliente, _ = _con([httpx.Response(200, text=EMPRESA_INSCRIPTA)])

    with pytest.raises(ProveedorNoDisponible, match="token y firma"):
        await cliente.consultar(ticket=b"solo-token", parametros=PARAMETROS, cuit=CUIT_CONSULTADO)


async def test_la_consulta_no_loguea_lo_que_leyo(caplog: pytest.LogCaptureFixture) -> None:
    """Caso 14. Una respuesta del padrón es el nombre real y el CUIT de alguien."""
    cliente, _ = _con([httpx.Response(200, text=EMPRESA_INSCRIPTA)])

    with caplog.at_level("DEBUG"):
        await cliente.consultar(ticket=TICKET, parametros=PARAMETROS, cuit=CUIT_CONSULTADO)

    registrado = caplog.text
    assert "PANADERIA DONA ROSA" not in registrado
    assert CUIT_CONSULTADO not in registrado
    assert "un-token" not in registrado
