"""Tests de contrato contra MercadoPago — la escalada de «nueva integración externa».

**Ninguno abre un socket.** `httpx.MockTransport` se pone donde estaría la red, así que se
ejercita el cliente entero —URL, cuerpo, cabecera, reintentos, traducción de errores—
contra respuestas grabadas.

Lo que más se juega acá es el **reintento**, y es lo contrario de lo que suele ser: el
endpoint de tokens consume un código de un solo uso y **rota el refresh token en cada
llamada**, así que repetir un pedido que MercadoPago quizá ya procesó es como una empresa
termina con un refresh token que el proveedor ya reemplazó. Sólo se repite lo que prueba
que el pedido nunca llegó.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    PedidoDeAutorizacion,
)
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_ETIQUETA,
    CLAVE_VENCIMIENTO,
    CLAVE_VERIFICADOR,
    EstadoDeConexion,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.autorizacion import (
    AutorizacionMercadoPago,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.cliente import (
    ClienteMercadoPago,
    ConfiguracionMercadoPago,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.conector import (
    ConectorMercadoPago,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.mapeo import (
    CLAVE_CUENTA_REAL,
    CLAVE_USUARIO,
    desempaquetar,
    empaquetar,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.verificador import (
    VerificadorMercadoPago,
)
from cheatsheet.shared.clock import RelojFijo

from tests.conftest import INSTANTE_FIJO

pytestmark = pytest.mark.asyncio

#: Inventados. El canje real devuelve cadenas opacas mucho más largas.
ACCESO = "APP_USR-acceso-de-prueba"
REFRESCO = "TG-refresco-de-prueba"
CODIGO = "TG-codigo-de-autorizacion"
VERIFICADOR = "verificador-pkce-de-prueba"
RETORNO = "https://panel.test/configuracion/integraciones"

#: Sin espera entre reintentos: el backoff real se prueba en `workers/base.py`, y acá sólo
#: importa cuántas veces se intenta.
CONFIG = ConfiguracionMercadoPago(
    client_id="app-de-prueba",
    client_secret="secreto-de-prueba",
    redirect_uri=RETORNO,
    auth_url="https://auth.test",
    api_url="https://api.test",
    timeout_segundos=1.0,
    espera_base=0.0,
)

TOKENS: dict[str, Any] = {
    "access_token": ACCESO,
    "refresh_token": REFRESCO,
    "expires_in": 15552000,
    "user_id": 123456789,
    # MercadoPago answers `live_mode: true` for a test user too, once the token is a
    # production one: the field says which credentials minted it, not whose account it is.
    "live_mode": True,
    "scope": "offline_access read write",
}

CUENTA: dict[str, Any] = {
    "id": 123456789,
    "nickname": "PANADERIA-ROSA",
    "email": "rosa@example.invalid",
    "site_id": "MLA",
    "tags": ["test_user", "normal"],
}

#: The same seller, but a real account: no `test_user` tag.
CUENTA_REAL: dict[str, Any] = {**CUENTA, "tags": ["normal"]}


class Grabadora:
    """Responde lo que se le dijo y anota cada pedido que vio."""

    def __init__(self, respuestas: list[httpx.Response | Exception]) -> None:
        self.respuestas = respuestas
        self.pedidos: list[httpx.Request] = []

    def transporte(self) -> httpx.MockTransport:
        def manejar(pedido: httpx.Request) -> httpx.Response:
            self.pedidos.append(pedido)
            indice = min(len(self.pedidos) - 1, len(self.respuestas) - 1)
            respuesta = self.respuestas[indice]
            if isinstance(respuesta, Exception):
                raise respuesta
            return respuesta

        return httpx.MockTransport(manejar)


def _ok(cuerpo: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=cuerpo)


def _error(estado: int, error: str, descripcion: str = "") -> httpx.Response:
    return httpx.Response(estado, json={"error": error, "error_description": descripcion})


def _cliente(grabadora: Grabadora) -> ClienteMercadoPago:
    return ClienteMercadoPago(CONFIG, grabadora.transporte())


def _conector(grabadora: Grabadora, *, es_produccion: bool = False) -> ConectorMercadoPago:
    return ConectorMercadoPago(
        _cliente(grabadora), RelojFijo(INSTANTE_FIJO), es_produccion=es_produccion
    )


def _material() -> MaterialDeConexion:
    return MaterialDeConexion(
        contenido=CODIGO.encode(), parametros={}, efimeros={CLAVE_VERIFICADOR: VERIFICADOR}
    )


# ------------------------------------------------------- la URL de autorización


async def test_la_url_de_autorizacion_lleva_todo_lo_que_mercadopago_exige() -> None:
    """Caso 1. `S256`: `plain` pondría el verificador en la URL, que es lo que PKCE evita."""
    url = AutorizacionMercadoPago(CONFIG).url_de_autorizacion(
        PedidoDeAutorizacion(estado="el-estado", desafio="el-desafio")
    )

    pedido = httpx.URL(url)
    assert str(pedido).startswith("https://auth.test/authorization?")
    assert pedido.params["client_id"] == "app-de-prueba"
    assert pedido.params["response_type"] == "code"
    assert pedido.params["platform_id"] == "mp"
    assert pedido.params["state"] == "el-estado"
    assert pedido.params["redirect_uri"] == RETORNO
    assert pedido.params["code_challenge"] == "el-desafio"
    assert pedido.params["code_challenge_method"] == "S256"


# ------------------------------------------------------- el canje del código


async def test_el_canje_manda_el_verificador_y_la_misma_redirect_uri() -> None:
    """Caso 6. MercadoPago compara la `redirect_uri` con la del paso 1: si difiere, rechaza."""
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA)])

    await _conector(grabadora).conectar(_material())

    pedido = grabadora.pedidos[0]
    assert pedido.method == "POST"
    assert str(pedido.url) == "https://api.test/oauth/token"
    cuerpo = json.loads(pedido.content)
    assert cuerpo["grant_type"] == "authorization_code"
    assert cuerpo["code"] == CODIGO
    assert cuerpo["code_verifier"] == VERIFICADOR
    assert cuerpo["redirect_uri"] == RETORNO
    assert cuerpo["client_id"] == "app-de-prueba"


async def test_el_canje_no_pide_credenciales_de_sandbox() -> None:
    """Con `test_token`, el token es de sandbox y el checkout de sandbox falla al pagar
    («Oh, no, algo anduvo mal»). Las cuentas de prueba usan credenciales productivas."""
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA)])

    await _conector(grabadora).conectar(_material())

    assert "test_token" not in json.loads(grabadora.pedidos[0].content)


async def test_una_cuenta_de_prueba_con_token_productivo_conecta_en_staging() -> None:
    """El caso de staging: `live_mode` en `true`, y aun así es una cuenta de prueba."""
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA)])

    resultado = await _conector(grabadora, es_produccion=False).conectar(_material())

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.parametros[CLAVE_CUENTA_REAL] is False


async def test_la_cuenta_se_lee_antes_de_dar_por_conectada_la_integracion() -> None:
    """RN-02. Un canje exitoso prueba que el código servía, no que el token hable por nadie."""
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA)])

    resultado = await _conector(grabadora).conectar(_material())

    assert len(grabadora.pedidos) == 2
    assert str(grabadora.pedidos[1].url) == "https://api.test/users/me"
    assert grabadora.pedidos[1].headers["Authorization"] == f"Bearer {ACCESO}"
    assert resultado.estado is EstadoDeConexion.CONECTADO


async def test_los_dos_tokens_quedan_juntos_en_la_credencial() -> None:
    """Caso 7, del lado del adaptador: un par partido en dos es un par que se desincroniza."""
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA)])

    resultado = await _conector(grabadora).conectar(_material())

    assert desempaquetar(resultado.credencial) == (ACCESO, REFRESCO)


async def test_los_parametros_guardados_no_incluyen_ningun_token() -> None:
    """Lo que va a la fila identifica la cuenta y dice hasta cuándo sirve. Nada más."""
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA)])

    resultado = await _conector(grabadora).conectar(_material())

    assert resultado.parametros[CLAVE_USUARIO] == "123456789"
    assert resultado.parametros[CLAVE_ETIQUETA] == "PANADERIA-ROSA · rosa@example.invalid"
    assert resultado.parametros[CLAVE_CUENTA_REAL] is False
    vence = datetime.fromisoformat(resultado.parametros[CLAVE_VENCIMIENTO])
    assert vence > INSTANTE_FIJO
    for valor in resultado.parametros.values():
        assert ACCESO not in str(valor)
        assert REFRESCO not in str(valor)


async def test_sin_verificador_no_se_canjea_nada() -> None:
    """Sólo `CompletarAutorizacion` lo provee: sin él, el código llegó por otro camino."""
    grabadora = Grabadora([_ok(TOKENS)])

    with pytest.raises(ConexionRechazada):
        await _conector(grabadora).conectar(
            MaterialDeConexion(contenido=CODIGO.encode(), parametros={})
        )
    assert grabadora.pedidos == []


# ------------------------------------------------------- los modos de falla


async def test_invalid_grant_se_traduce_a_un_rechazo_que_dice_qué_hacer() -> None:
    """Caso 10. El código venció o ya se usó: hay que volver a empezar el flujo."""
    grabadora = Grabadora([_error(400, "invalid_grant", "code expired")])

    with pytest.raises(ConexionRechazada, match="Volve a iniciar la conexion"):
        await _conector(grabadora).conectar(_material())


async def test_invalid_client_dice_que_el_problema_es_del_despliegue() -> None:
    """Caso 11. Es error nuestro, no del Administrador, y el mensaje nombra las variables."""
    grabadora = Grabadora([_error(400, "invalid_client")])

    with pytest.raises(ConexionRechazada, match="MERCADOPAGO_CLIENT_ID"):
        await _conector(grabadora).conectar(_material())


async def test_un_4xx_no_se_reintenta() -> None:
    """Caso 12. Repetirlo no falla distinto: sólo tarda más y quema el código otra vez."""
    grabadora = Grabadora([_error(400, "invalid_grant")])

    with pytest.raises(ConexionRechazada):
        await _conector(grabadora).conectar(_material())

    assert len(grabadora.pedidos) == 1


async def test_un_5xx_en_el_canje_tampoco_se_reintenta() -> None:
    """Y esto es lo que separa a este cliente del de Meta.

    Un 500 puede significar que MercadoPago procesó el canje y se cayó al contestar.
    Reintentar rotaría el refresh token una segunda vez y nos dejaría con uno viejo.
    """
    grabadora = Grabadora([httpx.Response(503, json={})])

    with pytest.raises(ProveedorNoDisponible):
        await _conector(grabadora).conectar(_material())

    assert len(grabadora.pedidos) == 1


async def test_un_fallo_de_conexion_si_se_reintenta() -> None:
    """Porque prueba que el pedido nunca llegó: repetirlo no puede duplicar nada."""
    grabadora = Grabadora(
        [httpx.ConnectError("sin ruta"), httpx.ConnectError("sin ruta"), _ok(TOKENS)]
    )

    await _cliente(grabadora).canjear(codigo=CODIGO, verificador=VERIFICADOR)

    assert len(grabadora.pedidos) == 3


async def test_un_timeout_de_lectura_no_se_reintenta() -> None:
    """Un `ReadTimeout` no prueba nada: el pedido pudo haber llegado y haberse procesado."""
    grabadora = Grabadora([httpx.ReadTimeout("tarde")])

    with pytest.raises(ProveedorNoDisponible):
        await _cliente(grabadora).canjear(codigo=CODIGO, verificador=VERIFICADOR)

    assert len(grabadora.pedidos) == 1


async def test_una_respuesta_sin_los_dos_tokens_no_se_guarda() -> None:
    """MercadoPago contestó 200 y aun así no hay nada que guardar."""
    grabadora = Grabadora([_ok({"access_token": ACCESO, "expires_in": 100})])

    with pytest.raises(ProveedorNoDisponible, match="par de tokens"):
        await _conector(grabadora).conectar(_material())


# ------------------------------------------------------- `live_mode` contra el ambiente


async def test_una_cuenta_real_en_homologacion_se_rechaza() -> None:
    """Caso 13. Es el caso que cobra plata de verdad desde un entorno de pruebas."""
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA_REAL)])

    with pytest.raises(ConexionRechazada, match="cuenta de prueba"):
        await _conector(grabadora, es_produccion=False).conectar(_material())


async def test_sin_la_etiqueta_de_prueba_se_rechaza_aunque_live_mode_sea_false() -> None:
    """La cuenta se juzga por quién es, no por qué credenciales firmaron el token."""
    grabadora = Grabadora([_ok({**TOKENS, "live_mode": False}), _ok(CUENTA_REAL)])

    with pytest.raises(ConexionRechazada, match="cuenta de prueba"):
        await _conector(grabadora, es_produccion=False).conectar(_material())


async def test_una_cuenta_de_prueba_en_produccion_conecta_en_atencion() -> None:
    """Caso 14. Acá el riesgo es no cobrar, y eso se ve la primera vez que alguien paga."""
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA)])

    resultado = await _conector(grabadora, es_produccion=True).conectar(_material())

    assert resultado.estado is EstadoDeConexion.ATENCION
    assert resultado.detalle is not None
    assert "prueba" in resultado.detalle


async def test_una_cuenta_real_en_produccion_conecta_normal() -> None:
    grabadora = Grabadora([_ok(TOKENS), _ok(CUENTA_REAL)])

    resultado = await _conector(grabadora, es_produccion=True).conectar(_material())

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.detalle is None


# ------------------------------------------------------- la renovación


async def test_la_renovacion_manda_el_refresh_token_guardado() -> None:
    grabadora = Grabadora([_ok(TOKENS)])

    await _conector(grabadora).renovar(empaquetar("acceso-viejo", "refresco-viejo"))

    cuerpo = json.loads(grabadora.pedidos[0].content)
    assert cuerpo["grant_type"] == "refresh_token"
    assert cuerpo["refresh_token"] == "refresco-viejo"


async def test_la_renovacion_tampoco_pide_credenciales_de_sandbox() -> None:
    grabadora = Grabadora([_ok(TOKENS)])

    await _conector(grabadora).renovar(empaquetar(ACCESO, REFRESCO))

    assert "test_token" not in json.loads(grabadora.pedidos[0].content)


async def test_la_renovacion_no_vuelve_a_leer_la_cuenta() -> None:
    """Un canje que funciona ya prueba que el token sirve. Preguntar de nuevo no agrega."""
    grabadora = Grabadora([_ok(TOKENS)])

    await _conector(grabadora).renovar(empaquetar(ACCESO, REFRESCO))

    assert len(grabadora.pedidos) == 1


async def test_la_renovacion_no_vuelve_a_juzgar_el_tipo_de_cuenta() -> None:
    """Un refresh no cambia de quién es la cuenta: eso se decidió al conectar y queda en los
    parámetros guardados, que la renovación no pisa. `live_mode` no dice nada sobre eso."""
    grabadora = Grabadora([_ok(TOKENS)])

    resultado = await _conector(grabadora, es_produccion=False).renovar(
        empaquetar(ACCESO, REFRESCO)
    )

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert CLAVE_CUENTA_REAL not in resultado.parametros


async def test_una_credencial_guardada_rota_se_reporta_como_tal() -> None:
    grabadora = Grabadora([_ok(TOKENS)])

    with pytest.raises(ProveedorNoDisponible, match="los dos tokens"):
        await _conector(grabadora).renovar(b"solo-un-token")


# ------------------------------------------------------- la verificación en vivo


async def test_la_verificacion_lee_la_cuenta_con_el_token_guardado() -> None:
    grabadora = Grabadora([_ok(CUENTA)])

    resultado = await VerificadorMercadoPago(_cliente(grabadora), es_produccion=False).verificar(
        empaquetar(ACCESO, REFRESCO), {CLAVE_CUENTA_REAL: False}
    )

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert grabadora.pedidos[0].headers["Authorization"] == f"Bearer {ACCESO}"
    assert resultado.parametros[CLAVE_ETIQUETA].startswith("PANADERIA-ROSA")


async def test_un_401_es_rn03_pasando_no_una_caida() -> None:
    """Caso 20. MercadoPago contestó, y lo que dijo es que el token ya no vale."""
    grabadora = Grabadora([_error(401, "unauthorized", "invalid token")])

    resultado = await VerificadorMercadoPago(_cliente(grabadora), es_produccion=False).verificar(
        empaquetar(ACCESO, REFRESCO), {}
    )

    assert resultado.estado is EstadoDeConexion.NO_CONECTADO


async def test_un_429_se_reintenta_porque_leer_no_duplica_nada() -> None:
    grabadora = Grabadora([httpx.Response(429, json={}), httpx.Response(429, json={}), _ok(CUENTA)])

    await VerificadorMercadoPago(_cliente(grabadora), es_produccion=False).verificar(
        empaquetar(ACCESO, REFRESCO), {}
    )

    assert len(grabadora.pedidos) == 3


async def test_ningun_test_de_este_archivo_abre_un_socket() -> None:
    """Caso 23, dicho como test: el transporte es siempre un `MockTransport`.

    Un cliente construido sin transporte iría a la red de verdad, y `api.test` no resuelve
    — el test fallaría, que es lo correcto, pero tarde y con un error confuso.
    """
    assert CONFIG.api_url.endswith(".test")
    assert CONFIG.auth_url.endswith(".test")


# ------------------------------------------------------- detalles del ACL


async def test_una_autorizacion_sin_codigo_no_llega_al_proveedor() -> None:
    grabadora = Grabadora([_ok(TOKENS)])

    with pytest.raises(ConexionRechazada, match="sin codigo"):
        await _conector(grabadora).conectar(
            MaterialDeConexion(
                contenido=b"   ", parametros={}, efimeros={CLAVE_VERIFICADOR: VERIFICADOR}
            )
        )
    assert grabadora.pedidos == []


async def test_sin_expires_in_se_asume_la_duracion_habitual() -> None:
    """Un campo ausente no puede volverse «renovar todos los días para siempre»."""
    grabadora = Grabadora(
        [_ok({k: v for k, v in TOKENS.items() if k != "expires_in"}), _ok(CUENTA)]
    )

    resultado = await _conector(grabadora).conectar(_material())

    vence = datetime.fromisoformat(resultado.parametros[CLAVE_VENCIMIENTO])
    assert (vence - INSTANTE_FIJO).days == 180


async def test_una_cuenta_sin_email_igual_tiene_etiqueta() -> None:
    """MercadoPago no siempre devuelve el mail; la tarjeta necesita decir algo igual."""
    grabadora = Grabadora(
        [_ok(TOKENS), _ok({"id": 1, "nickname": "PANADERIA-ROSA", "tags": ["test_user"]})]
    )

    resultado = await _conector(grabadora).conectar(_material())

    assert resultado.parametros[CLAVE_ETIQUETA] == "PANADERIA-ROSA"


async def test_la_verificacion_de_una_cuenta_real_en_homologacion_marca_atencion() -> None:
    """Igual que en la renovación: se marca, no se desconecta lo que venía funcionando."""
    grabadora = Grabadora([_ok(CUENTA)])

    resultado = await VerificadorMercadoPago(_cliente(grabadora), es_produccion=False).verificar(
        empaquetar(ACCESO, REFRESCO), {CLAVE_CUENTA_REAL: True}
    )

    assert resultado.estado is EstadoDeConexion.ATENCION


async def test_un_429_eterno_termina_en_proveedor_no_disponible() -> None:
    grabadora = Grabadora([httpx.Response(429, json={})])

    with pytest.raises(ProveedorNoDisponible, match="no respondio tras"):
        await _cliente(grabadora).cuenta(acceso=ACCESO)

    assert len(grabadora.pedidos) == 3
