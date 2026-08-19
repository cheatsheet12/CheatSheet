"""Tests de contrato contra Meta — casos 12 a 15 del plan, y el conector completo.

**Ninguno abre un socket.** `httpx.MockTransport` se pone en el mismo lugar donde estaría
la red, así que se ejercita el cliente entero —URL, cabecera, campos pedidos, reintentos,
traducción de errores— contra respuestas grabadas de Graph API.

Es la escalada de «nueva integración externa» que pide el workflow: endpoints, autenticación
y modos de falla, cada uno con su caso.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import MaterialDeConexion
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.whatsapp.cliente import (
    ClienteGraph,
    ConfiguracionWhatsApp,
)
from cheatsheet.contexts.integrations.infrastructure.whatsapp.conector import ConectorWhatsApp
from cheatsheet.contexts.integrations.infrastructure.whatsapp.mapeo import (
    CLAVE_DISPLAY_NAME,
    CLAVE_PHONE_NUMBER_ID,
    CLAVE_WABA_ID,
)
from cheatsheet.contexts.integrations.infrastructure.whatsapp.verificador import (
    VerificadorWhatsApp,
)

pytestmark = pytest.mark.asyncio

FAKE_TOKEN_FOR_TESTS = "fake-token-for-tests"
PHONE_ID = "109876543210987"
WABA_ID = "102030405060708"

#: Sin espera entre reintentos: el backoff real ya se prueba en `workers/base.py`, y acá
#: sólo importa cuántas veces se intenta.
CONFIG = ConfiguracionWhatsApp(
    url_base="https://graph.test", version="v21.0", timeout_segundos=1.0, espera_base=0.0
)

NUMERO_APROBADO: dict[str, Any] = {
    "id": PHONE_ID,
    "name_status": "APPROVED",
    "verified_name": "Panaderia Dona Rosa",
    "quality_rating": "GREEN",
    "display_phone_number": "+54 9 11 5555-0000",
    "code_verification_status": "VERIFIED",
}


class Grabadora:
    """Responde lo que se le dijo y anota cada pedido que vio."""

    def __init__(self, respuestas: list[httpx.Response]) -> None:
        self.respuestas = respuestas
        self.pedidos: list[httpx.Request] = []

    def transporte(self) -> httpx.MockTransport:
        def manejar(pedido: httpx.Request) -> httpx.Response:
            self.pedidos.append(pedido)
            indice = min(len(self.pedidos) - 1, len(self.respuestas) - 1)
            return self.respuestas[indice]

        return httpx.MockTransport(manejar)


def _ok(cuerpo: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=cuerpo)


def _error(estado: int, *, codigo: int | None = None, mensaje: str = "no") -> httpx.Response:
    detalle: dict[str, Any] = {"message": mensaje}
    if codigo is not None:
        detalle["code"] = codigo
    return httpx.Response(estado, json={"error": detalle})


def _numeros_de_la_cuenta() -> httpx.Response:
    return _ok({"data": [{"id": PHONE_ID, "display_phone_number": "+54 9 11 5555-0000"}]})


def _cliente(grabadora: Grabadora) -> ClienteGraph:
    return ClienteGraph(CONFIG, grabadora.transporte())


def _material() -> MaterialDeConexion:
    return MaterialDeConexion(
        contenido=FAKE_TOKEN_FOR_TESTS.encode(),
        parametros={CLAVE_PHONE_NUMBER_ID: PHONE_ID, CLAVE_WABA_ID: WABA_ID},
    )


# ------------------------------------------------------- el contrato de la llamada


async def test_la_consulta_del_numero_arma_la_url_la_version_y_los_campos() -> None:
    """Los campos van explícitos: el default de Graph API cambia y perdería RN-03."""
    grabadora = Grabadora([_ok(NUMERO_APROBADO)])

    await _cliente(grabadora).numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)

    pedido = grabadora.pedidos[0]
    assert str(pedido.url).startswith(f"https://graph.test/v21.0/{PHONE_ID}")
    assert pedido.headers["Authorization"] == f"Bearer {FAKE_TOKEN_FOR_TESTS}"
    campos = pedido.url.params["fields"]
    assert "name_status" in campos
    assert "verified_name" in campos
    assert "quality_rating" in campos


async def test_el_timeout_configurado_llega_al_cliente_http() -> None:
    """Caso 15. CLAUDE.md §5: toda llamada saliente lleva timeout explícito."""
    grabadora = Grabadora([_ok(NUMERO_APROBADO)])

    await _cliente(grabadora).numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)

    assert grabadora.pedidos[0].extensions.get("timeout", {}).get("connect") == 1.0


# --------------------------------------------------------------- modos de falla


async def test_un_401_se_traduce_a_credencial_rechazada_y_no_se_reintenta() -> None:
    """Caso 12. Una credencial inválida va a seguir siéndolo: reintentar es ruido."""
    grabadora = Grabadora([_error(401, mensaje="Invalid OAuth access token")])

    with pytest.raises(ConexionRechazada) as fallo:
        await _cliente(grabadora).numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)

    assert "meta" in str(fallo.value).lower()
    assert len(grabadora.pedidos) == 1


async def test_un_403_tambien_es_rechazo_de_credencial() -> None:
    grabadora = Grabadora([_error(403)])

    with pytest.raises(ConexionRechazada):
        await _cliente(grabadora).numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)


async def test_el_codigo_100_de_meta_dice_que_el_identificador_no_existe() -> None:
    grabadora = Grabadora([_error(400, codigo=100)])

    with pytest.raises(ConexionRechazada) as fallo:
        await _cliente(grabadora).numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)

    assert "identificador" in str(fallo.value).lower()


@pytest.mark.parametrize("estado", [429, 500, 503], ids=["rate-limit", "500", "503"])
async def test_un_429_o_un_5xx_se_reintenta_y_termina_en_proveedor_no_disponible(
    estado: int,
) -> None:
    """Caso 13. Meta teniendo un mal momento no es un rechazo del negocio."""
    grabadora = Grabadora([_error(estado)])

    with pytest.raises(ProveedorNoDisponible):
        await _cliente(grabadora).numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)

    assert len(grabadora.pedidos) == CONFIG.max_intentos


async def test_un_corte_de_red_se_reintenta_y_termina_en_proveedor_no_disponible() -> None:
    intentos: list[int] = []

    def manejar(pedido: httpx.Request) -> httpx.Response:
        intentos.append(1)
        raise httpx.ConnectError("sin ruta", request=pedido)

    cliente = ClienteGraph(CONFIG, httpx.MockTransport(manejar))

    with pytest.raises(ProveedorNoDisponible):
        await cliente.numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)

    assert len(intentos) == CONFIG.max_intentos


async def test_un_reintento_que_sale_bien_devuelve_el_cuerpo() -> None:
    """El backoff sirve de algo: el segundo intento contesta y el caso de uso no se entera."""
    grabadora = Grabadora([_error(503), _ok(NUMERO_APROBADO)])

    datos = await _cliente(grabadora).numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)

    assert datos["name_status"] == "APPROVED"
    assert len(grabadora.pedidos) == 2


async def test_una_respuesta_que_no_es_json_no_explota_como_error_de_parseo() -> None:
    grabadora = Grabadora([httpx.Response(200, text="<html>algo salio mal</html>")])

    with pytest.raises(ProveedorNoDisponible):
        await _cliente(grabadora).numero(token=FAKE_TOKEN_FOR_TESTS, phone_number_id=PHONE_ID)


# --------------------------------------------------------------- el conector


async def test_conectar_un_numero_aprobado_devuelve_la_credencial_y_los_datos() -> None:
    grabadora = Grabadora([_numeros_de_la_cuenta(), _ok(NUMERO_APROBADO)])

    resultado = await ConectorWhatsApp(_cliente(grabadora)).conectar(_material())

    assert resultado.credencial == FAKE_TOKEN_FOR_TESTS.encode()
    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.parametros[CLAVE_DISPLAY_NAME] == "Panaderia Dona Rosa"
    assert resultado.parametros[CLAVE_PHONE_NUMBER_ID] == PHONE_ID


async def test_conectar_un_numero_en_revision_lo_deja_pendiente() -> None:
    """El desenlace normal de HU-E2-03: Meta acepta y se toma entre 24 y 72 horas."""
    grabadora = Grabadora(
        [_numeros_de_la_cuenta(), _ok({**NUMERO_APROBADO, "name_status": "PENDING_REVIEW"})]
    )

    resultado = await ConectorWhatsApp(_cliente(grabadora)).conectar(_material())

    assert resultado.estado is EstadoDeConexion.PENDIENTE


async def test_conectar_un_numero_rechazado_no_guarda_nada() -> None:
    """Nada de fila en `NO_CONECTADO`: eso ofrecería «Reconectar» para algo nunca conectado."""
    grabadora = Grabadora(
        [_numeros_de_la_cuenta(), _ok({**NUMERO_APROBADO, "name_status": "DECLINED"})]
    )

    with pytest.raises(ConexionRechazada):
        await ConectorWhatsApp(_cliente(grabadora)).conectar(_material())


async def test_un_numero_que_no_es_de_la_cuenta_declarada_se_rechaza() -> None:
    """Caso 14. Un permiso con acceso a varias cuentas no se apunta con un typo."""
    grabadora = Grabadora([_ok({"data": [{"id": "otro-numero-distinto"}]})])

    with pytest.raises(ConexionRechazada) as fallo:
        await ConectorWhatsApp(_cliente(grabadora)).conectar(_material())

    assert "no pertenece" in str(fallo.value).lower()
    # Y no se llegó a preguntar por el número: el orden de las dos llamadas importa.
    assert len(grabadora.pedidos) == 1


@pytest.mark.parametrize(
    "faltante", [CLAVE_PHONE_NUMBER_ID, CLAVE_WABA_ID], ids=["sin-numero", "sin-cuenta"]
)
async def test_faltando_un_identificador_se_rechaza_sin_llamar_a_meta(faltante: str) -> None:
    grabadora = Grabadora([_numeros_de_la_cuenta()])
    parametros = {CLAVE_PHONE_NUMBER_ID: PHONE_ID, CLAVE_WABA_ID: WABA_ID}
    del parametros[faltante]

    with pytest.raises(ConexionRechazada):
        await ConectorWhatsApp(_cliente(grabadora)).conectar(
            MaterialDeConexion(contenido=FAKE_TOKEN_FOR_TESTS.encode(), parametros=parametros)
        )

    assert grabadora.pedidos == []


async def test_una_credencial_en_blanco_se_rechaza_sin_llamar_a_meta() -> None:
    grabadora = Grabadora([_numeros_de_la_cuenta()])

    with pytest.raises(ConexionRechazada):
        await ConectorWhatsApp(_cliente(grabadora)).conectar(
            MaterialDeConexion(
                contenido=b"   ",
                parametros={CLAVE_PHONE_NUMBER_ID: PHONE_ID, CLAVE_WABA_ID: WABA_ID},
            )
        )

    assert grabadora.pedidos == []


# --------------------------------------------------------------- el verificador


async def test_verificar_relee_el_estado_del_numero_sin_revalidar_la_cuenta() -> None:
    grabadora = Grabadora([_ok(NUMERO_APROBADO)])

    resultado = await VerificadorWhatsApp(_cliente(grabadora)).verificar(
        FAKE_TOKEN_FOR_TESTS.encode(), {CLAVE_PHONE_NUMBER_ID: PHONE_ID}
    )

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert len(grabadora.pedidos) == 1


async def test_verificar_sin_el_id_del_numero_avisa_en_vez_de_explotar() -> None:
    """Una fila sin identificador no responde ninguna pregunta; eso es `ATENCION`."""
    grabadora = Grabadora([_ok(NUMERO_APROBADO)])

    resultado = await VerificadorWhatsApp(_cliente(grabadora)).verificar(
        FAKE_TOKEN_FOR_TESTS.encode(), {}
    )

    assert resultado.estado is EstadoDeConexion.ATENCION
    assert grabadora.pedidos == []
