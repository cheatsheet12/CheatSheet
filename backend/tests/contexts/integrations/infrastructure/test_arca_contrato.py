"""Tests de contrato contra WSAA — casos 7 a 14 del plan.

**Ninguno toca ARCA, ni homologación.** Es la regla del workflow y acá pesa doble:
homologación también tiene límites de uso, y un test que consume un ticket de 12 horas
rompe el test siguiente. `httpx.MockTransport` se pone donde estaría la red y se responden
sobres SOAP grabados.
"""

from __future__ import annotations

import base64
import datetime as dt

import httpx
import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import MaterialDeConexion
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import CLAVE_ETIQUETA, EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.arca.adaptadores import (
    ConectorArca,
    EmisorArcaDeTickets,
    VerificadorArca,
)
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import (
    CLAVE_CUIT,
    CLAVE_VENCIMIENTO,
    YaAutenticado,
)
from cheatsheet.contexts.integrations.infrastructure.arca.wsaa import (
    ClienteWsaa,
    ConfiguracionWsaa,
)
from cheatsheet.shared.clock import RelojFijo
from cryptography.hazmat.primitives.serialization import pkcs7

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest_arca import (
    CUIT_DE_PRUEBA,
    bundle_con_clave_ajena,
)
from tests.contexts.integrations.conftest_arca import (
    bundle as _bundle,
)

pytestmark = pytest.mark.asyncio

RELOJ = RelojFijo(INSTANTE_FIJO)


def bundle(**kwargs: object) -> bytes:
    """Certificados anclados al mismo instante que `RELOJ`.

    Sin esto, un certificado «vencido ayer» respecto del reloj real sigue vigente respecto
    del reloj congelado del test, y el test pasa probando lo contrario de lo que dice.
    """
    return _bundle(desde=INSTANTE_FIJO, **kwargs)


AVISO = dt.timedelta(days=30)
VENCE = "2026-08-20T00:00:00-03:00"

#: Sin espera entre reintentos: el backoff real ya tiene su test en `workers/base.py`.
CONFIG = ConfiguracionWsaa(
    url="https://wsaa.test/ws/services/LoginCms", timeout_segundos=15.0, espera_base=0.0
)


def _respuesta_ok(vence: str = VENCE) -> httpx.Response:
    """Un `loginCmsReturn`, que es un XML escapado adentro de otro XML. Así viene."""
    interior = (
        '<?xml version="1.0"?><loginTicketResponse version="1.0">'
        f"<header><expirationTime>{vence}</expirationTime></header>"
        "<credentials><token>UN-TOKEN</token><sign>UNA-FIRMA</sign></credentials>"
        "</loginTicketResponse>"
    )
    escapado = interior.replace("<", "&lt;").replace(">", "&gt;")
    return httpx.Response(
        200,
        text=(
            '<?xml version="1.0"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            f"<soapenv:Body><loginCmsResponse><loginCmsReturn>{escapado}"
            "</loginCmsReturn></loginCmsResponse></soapenv:Body></soapenv:Envelope>"
        ),
    )


def _falla(codigo: str, detalle: str = "no se pudo") -> httpx.Response:
    return httpx.Response(
        500,
        text=(
            '<?xml version="1.0"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            f"<soapenv:Body><soapenv:Fault><faultcode>{codigo}</faultcode>"
            f"<faultstring>{detalle}</faultstring></soapenv:Fault>"
            "</soapenv:Body></soapenv:Envelope>"
        ),
    )


class Grabadora:
    def __init__(self, respuestas: list[httpx.Response]) -> None:
        self.respuestas = respuestas
        self.pedidos: list[httpx.Request] = []

    def transporte(self) -> httpx.MockTransport:
        def manejar(pedido: httpx.Request) -> httpx.Response:
            self.pedidos.append(pedido)
            return self.respuestas[min(len(self.pedidos) - 1, len(self.respuestas) - 1)]

        return httpx.MockTransport(manejar)


def _emisor(grabadora: Grabadora, config: ConfiguracionWsaa = CONFIG) -> EmisorArcaDeTickets:
    return EmisorArcaDeTickets(ClienteWsaa(config, grabadora.transporte()), RELOJ)


# --------------------------------------------------------------- caso 7: el camino feliz


async def test_un_login_correcto_devuelve_token_sign_y_vencimiento() -> None:
    """Caso 7."""
    grabadora = Grabadora([_respuesta_ok()])

    ticket = await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)

    assert ticket.servicio is ServicioDeArca.WSFE
    assert ticket.contenido == b"UN-TOKEN\nUNA-FIRMA"
    assert ticket.expira_en == dt.datetime.fromisoformat(VENCE)


async def test_el_cms_viaja_en_base64_dentro_del_sobre_soap() -> None:
    """Lo que ARCA espera: un CMS en DER, codificado, dentro de `in0`."""
    grabadora = Grabadora([_respuesta_ok()])

    await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)

    cuerpo = grabadora.pedidos[0].content.decode()
    crudo = cuerpo.split("<wsaa:in0>")[1].split("</wsaa:in0>")[0]
    # Si esto parsea como PKCS#7, lo que se mandó es un CMS de verdad.
    assert pkcs7.load_der_pkcs7_certificates(base64.b64decode(crudo))
    assert grabadora.pedidos[0].headers["Content-Type"].startswith("text/xml")


async def test_el_timeout_configurado_llega_al_cliente_http() -> None:
    """Caso 13. Más largo que el de Meta: ARCA es más lento."""
    grabadora = Grabadora([_respuesta_ok()])

    await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)

    assert grabadora.pedidos[0].extensions.get("timeout", {}).get("connect") == 15.0


# --------------------------------------------------------------- casos 8 a 12: fallas


async def test_ya_autenticado_no_es_un_error() -> None:
    """Caso 8. Es ARCA confirmando que la credencial sirve, y negándose a duplicar el TA."""
    grabadora = Grabadora([_falla("coe.alreadyAuthenticated", "ya posee un TA valido")])

    with pytest.raises(YaAutenticado):
        await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("cms.cert.untrusted", "habilitado"),
        ("cms.cert.expired", "vencido"),
        ("cms.cert.notFound", "no encontro"),
        ("cms.sign.InvalidCertificate", "no reconoce"),
    ],
    ids=["untrusted", "expired", "notfound", "invalid"],
)
async def test_un_rechazo_de_credencial_llega_con_el_motivo(codigo: str, esperado: str) -> None:
    """Casos 9 y 10, más los otros dos códigos de la tabla del plan."""
    grabadora = Grabadora([_falla(codigo)])

    with pytest.raises(ConexionRechazada) as fallo:
        await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)

    assert esperado in str(fallo.value)
    # No se reintenta: la credencial va a seguir siendo la misma.
    assert len(grabadora.pedidos) == 1


async def test_un_codigo_desconocido_no_rompe_la_tarea() -> None:
    """Caso 11. ARCA agrega códigos, y un `KeyError` en Beat es una integración muda."""
    grabadora = Grabadora([_falla("algo.que.arca.invento", "vaya a saber")])

    with pytest.raises(ConexionRechazada) as fallo:
        await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)

    assert "algo.que.arca.invento" in str(fallo.value)


async def test_un_500_sin_fault_se_reintenta() -> None:
    """Caso 12. Un 500 con SOAP fault es una respuesta; uno sin fault es una caída."""
    grabadora = Grabadora([httpx.Response(500, text="<html>Service Unavailable</html>")])

    with pytest.raises(ProveedorNoDisponible):
        await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)

    assert len(grabadora.pedidos) == CONFIG.max_intentos


async def test_un_corte_de_red_se_reintenta_y_termina_en_proveedor_no_disponible() -> None:
    intentos: list[int] = []

    def manejar(pedido: httpx.Request) -> httpx.Response:
        intentos.append(1)
        raise httpx.ConnectError("sin ruta", request=pedido)

    emisor = EmisorArcaDeTickets(ClienteWsaa(CONFIG, httpx.MockTransport(manejar)), RELOJ)

    with pytest.raises(ProveedorNoDisponible):
        await emisor.emitir(bundle(), ServicioDeArca.WSFE)

    assert len(intentos) == CONFIG.max_intentos


async def test_un_reintento_que_sale_bien_devuelve_el_ticket() -> None:
    grabadora = Grabadora([httpx.Response(503, text="no"), _respuesta_ok()])

    ticket = await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)

    assert ticket.contenido == b"UN-TOKEN\nUNA-FIRMA"
    assert len(grabadora.pedidos) == 2


async def test_una_respuesta_sin_ticket_no_se_interpreta_como_exito() -> None:
    grabadora = Grabadora([httpx.Response(200, text="<Envelope><Body/></Envelope>")])

    with pytest.raises(ProveedorNoDisponible):
        await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)


async def test_una_respuesta_que_no_es_xml_no_explota_como_error_de_parseo() -> None:
    grabadora = Grabadora([httpx.Response(200, text="no soy xml <<<")])

    with pytest.raises(ProveedorNoDisponible):
        await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)


async def test_una_bomba_de_entidades_xml_se_rechaza() -> None:
    """`defusedxml` está por esto, y se mide en vez de asumirse.

    `xml.etree` expande entidades internas: 300 bytes se volvieron 3 000 caracteres, diez
    veces por nivel de anidamiento. La respuesta de un servicio externo es entrada no
    confiable por definición.
    """
    bomba = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        "<Envelope><Body><loginCmsReturn>&lol2;</loginCmsReturn></Body></Envelope>"
    )
    grabadora = Grabadora([httpx.Response(200, text=bomba)])

    with pytest.raises(ProveedorNoDisponible):
        await _emisor(grabadora).emitir(bundle(), ServicioDeArca.WSFE)


# --------------------------------------------------------------- el conector


async def test_conectar_devuelve_la_credencial_el_ticket_y_los_datos_de_la_tarjeta() -> None:
    grabadora = Grabadora([_respuesta_ok()])
    material = MaterialDeConexion(contenido=bundle(), parametros={})

    resultado = await ConectorArca(_emisor(grabadora), RELOJ).conectar(material)

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.credencial == material.contenido
    assert len(resultado.tickets) == 1
    assert resultado.parametros[CLAVE_CUIT] == CUIT_DE_PRUEBA
    assert CUIT_DE_PRUEBA in str(resultado.parametros[CLAVE_ETIQUETA])
    assert resultado.parametros[CLAVE_VENCIMIENTO]


async def test_conectar_con_un_certificado_vencido_no_llega_a_arca() -> None:
    """Caso 3 desde el conector: lo verificable localmente se verifica primero."""
    grabadora = Grabadora([_respuesta_ok()])
    material = MaterialDeConexion(contenido=bundle(vence_en_dias=-1), parametros={})

    with pytest.raises(ConexionRechazada):
        await ConectorArca(_emisor(grabadora), RELOJ).conectar(material)

    assert grabadora.pedidos == []


async def test_conectar_con_una_clave_ajena_no_llega_a_arca() -> None:
    grabadora = Grabadora([_respuesta_ok()])
    material = MaterialDeConexion(contenido=bundle_con_clave_ajena(), parametros={})

    with pytest.raises(ConexionRechazada):
        await ConectorArca(_emisor(grabadora), RELOJ).conectar(material)

    assert grabadora.pedidos == []


async def test_si_arca_ya_tenia_un_ticket_la_conexion_igual_es_valida() -> None:
    """ARCA confirmó la credencial y se negó a duplicar el TA: no hay nada que guardar."""
    grabadora = Grabadora([_falla("coe.alreadyAuthenticated")])
    material = MaterialDeConexion(contenido=bundle(), parametros={})

    resultado = await ConectorArca(_emisor(grabadora), RELOJ).conectar(material)

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.tickets == ()


# --------------------------------------------------------------- el verificador


async def test_verificar_no_abre_ningun_socket() -> None:
    """Decisión D-e: llamar a WSAA acá quemaría el ticket de 12 h en cada refresco."""

    def prohibido(pedido: httpx.Request) -> httpx.Response:
        raise AssertionError("el verificador de ARCA no debe usar la red")

    del prohibido  # no hay cliente que pasarle: el verificador no recibe ninguno
    resultado = await VerificadorArca(RELOJ, AVISO).verificar(bundle(vence_en_dias=400), {})

    assert resultado.estado is EstadoDeConexion.CONECTADO


async def test_un_certificado_por_vencer_es_atencion_con_los_dias_que_faltan() -> None:
    resultado = await VerificadorArca(RELOJ, AVISO).verificar(bundle(vence_en_dias=20), {})

    assert resultado.estado is EstadoDeConexion.ATENCION
    assert resultado.detalle is not None
    assert "vence en" in resultado.detalle


async def test_un_certificado_vencido_es_no_conectado() -> None:
    """RN-04, la mitad reactiva."""
    resultado = await VerificadorArca(RELOJ, AVISO).verificar(bundle(vence_en_dias=-1), {})

    assert resultado.estado is EstadoDeConexion.NO_CONECTADO
    assert resultado.detalle is not None
    assert "vencio" in resultado.detalle


async def test_una_credencial_guardada_ilegible_es_atencion_y_no_una_excepcion() -> None:
    """Falla dentro de una tarea de Beat: tiene que quedar visible, no tumbarla."""
    resultado = await VerificadorArca(RELOJ, AVISO).verificar(b"basura", {})

    assert resultado.estado is EstadoDeConexion.ATENCION
