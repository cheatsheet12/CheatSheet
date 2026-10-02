"""Los endpoints del catálogo de clientes, de punta a punta.

Toda la pila en un proceso: la app ASGI, `EmpresaMiddleware` verificando un JWT real, el
router, los casos de uso, el repositorio de PostgreSQL y la RLS. No se abre ningún socket
salvo hacia la base local — `httpx.ASGITransport` llama a la aplicación directamente — y
ARCA corre con su adaptador simulado, como en toda la suite.

**Por qué existe este archivo si cada capa ya tiene su test.** Dos costuras que ninguna
prueba unitaria mira: que el 409 del CUIT duplicado llegue al navegador **con el id del
que ya estaba** —el manejador propio que se registra en `create_app`, y que el cuerpo
uniforme de `api/errors.py` no sabría armar—, y que la empresa del token sea la que
gobierna lo que se ve. Además, el alta de un cliente desde el panel es el entregable de
la unidad: hasta que no corre entera, nadie la vio funcionar.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import replace

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.platform.settings import Settings

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
CUIT_VALIDO = "30712345671"
OTRO_CUIT = "20123456786"


def _settings() -> Settings:
    """La configuración inerte compartida, con las URLs reales de la base puestas."""
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest_asyncio.fixture
async def cliente_http(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as http:
        yield http
    await recursos.cerrar()


async def _registrar_empresa(http: httpx.AsyncClient, email: str) -> str:
    """Crea la empresa y devuelve el token de su Administrador."""
    respuesta = await http.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _crear(http: httpx.AsyncClient, token: str, **campos: str | None) -> httpx.Response:
    return await http.post("/clientes", json=campos, headers=_auth(token))


@pytest.mark.asyncio
async def test_sin_token_no_se_listan_clientes(cliente_http: httpx.AsyncClient) -> None:
    """El middleware rechaza antes de que corra ningún caso de uso."""
    respuesta = await cliente_http.get("/clientes")

    assert respuesta.status_code == 401


@pytest.mark.asyncio
async def test_alta_y_listado(cliente_http: httpx.AsyncClient) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    creado = await _crear(cliente_http, token, nombre="Panaderia Dona Rosa")
    assert creado.status_code == 201, creado.text
    assert creado.json()["origen"] == "PANEL"
    assert creado.json()["activo"] is True

    listado = await cliente_http.get("/clientes", headers=_auth(token))
    assert listado.status_code == 200
    assert listado.json()["total"] == 1
    assert listado.json()["clientes"][0]["nombre"] == "Panaderia Dona Rosa"


@pytest.mark.asyncio
async def test_un_cuit_corto_responde_422_con_el_mensaje_de_la_historia(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, nombre="Rosa", cuit="3071234567")

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "El CUIT debe contener 11 digitos."


@pytest.mark.asyncio
async def test_el_duplicado_responde_409_con_el_id_del_existente(
    cliente_http: httpx.AsyncClient,
) -> None:
    """La costura entera: el manejador propio de `create_app` y el «ver el duplicado»."""
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")
    primero = await _crear(cliente_http, token, nombre="Rosa", cuit=CUIT_VALIDO)
    assert primero.status_code == 201, primero.text

    segundo = await _crear(cliente_http, token, nombre="Rosa otra vez", cuit=CUIT_VALIDO)

    assert segundo.status_code == 409
    assert segundo.json()["detalle"] == "Ya existe un cliente con ese CUIT."
    assert segundo.json()["cliente_existente_id"] == primero.json()["id"]


@pytest.mark.asyncio
async def test_sin_arca_conectada_el_alta_con_cuit_igual_entra(
    cliente_http: httpx.AsyncClient,
) -> None:
    """La decisión del Gate 1, vista desde afuera: se guarda y se avisa por qué no se validó."""
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, nombre="Rosa", cuit=CUIT_VALIDO)

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["validacion"]["estado"] == "NO_DISPONIBLE"
    assert respuesta.json()["validacion"]["motivo"]


@pytest.mark.asyncio
async def test_editar_y_cambiar_estado(cliente_http: httpx.AsyncClient) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")
    creado = await _crear(cliente_http, token, nombre="Rosa")
    cliente_id = creado.json()["id"]

    editado = await cliente_http.put(
        f"/clientes/{cliente_id}",
        json={"nombre": "Rosa Diaz", "contacto_whatsapp": "+54 9 11 1234-5678"},
        headers=_auth(token),
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["nombre"] == "Rosa Diaz"
    assert editado.json()["contacto_whatsapp"] == "5491112345678"
    assert editado.json()["origen"] == "PANEL"

    desactivado = await cliente_http.put(
        f"/clientes/{cliente_id}/estado", json={"activo": False}, headers=_auth(token)
    )
    assert desactivado.status_code == 200
    assert desactivado.json()["activo"] is False

    activos = await cliente_http.get("/clientes?solo_activos=true", headers=_auth(token))
    assert activos.json()["total"] == 0


@pytest.mark.asyncio
async def test_no_existe_el_borrado(cliente_http: httpx.AsyncClient) -> None:
    """No hay `DELETE` en el router: la ruta contesta 405, no 204."""
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")
    creado = await _crear(cliente_http, token, nombre="Rosa")

    respuesta = await cliente_http.delete(f"/clientes/{creado.json()['id']}", headers=_auth(token))

    assert respuesta.status_code == 405


@pytest.mark.asyncio
async def test_una_empresa_no_ve_los_clientes_de_otra(cliente_http: httpx.AsyncClient) -> None:
    """La barrera, desde el borde HTTP: dos tokens, dos catálogos."""
    token_a = await _registrar_empresa(cliente_http, "ana@empresa-a.com")
    token_b = await _registrar_empresa(cliente_http, "bruno@empresa-b.com")
    await _crear(cliente_http, token_a, nombre="De la empresa A")

    listado_b = await cliente_http.get("/clientes", headers=_auth(token_b))

    assert listado_b.status_code == 200
    assert listado_b.json()["total"] == 0


@pytest.mark.asyncio
async def test_el_boton_de_validar_contra_arca_responde_los_tres_estados(
    cliente_http: httpx.AsyncClient,
) -> None:
    """Con ARCA sin conectar el estado es `NO_DISPONIBLE`, nunca `NO_ENCONTRADO`."""
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await cliente_http.post(
        "/clientes/padron", json={"cuit": OTRO_CUIT}, headers=_auth(token)
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "NO_DISPONIBLE"


@pytest.mark.asyncio
async def test_ver_un_cliente_por_id(cliente_http: httpx.AsyncClient) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")
    creado = await _crear(cliente_http, token, nombre="Rosa Diaz", cuit=CUIT_VALIDO)
    cliente_id = creado.json()["id"]

    respuesta = await cliente_http.get(f"/clientes/{cliente_id}", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["id"] == cliente_id
    assert respuesta.json()["nombre"] == "Rosa Diaz"


@pytest.mark.asyncio
async def test_ver_un_cliente_de_otra_empresa_responde_igual_que_uno_inexistente(
    cliente_http: httpx.AsyncClient,
) -> None:
    """Distinguirlos le diria a una empresa que el id ajeno es real."""
    token_a = await _registrar_empresa(cliente_http, "ana@empresa-a.com")
    token_b = await _registrar_empresa(cliente_http, "bruno@empresa-b.com")
    ajeno = (await _crear(cliente_http, token_a, nombre="De la empresa A")).json()["id"]

    de_otra = await cliente_http.get(f"/clientes/{ajeno}", headers=_auth(token_b))
    inexistente = await cliente_http.get(
        "/clientes/00000000-0000-4000-8000-000000000000", headers=_auth(token_b)
    )

    assert de_otra.status_code == inexistente.status_code == 422
