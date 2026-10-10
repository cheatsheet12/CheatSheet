"""Los endpoints de categorías y clasificación, de punta a punta.

Dos costuras que ninguna prueba de capa mira, y las dos son propias de esta unidad:

1. **El `DELETE`**, que es el único de la API. Su primera versión hacía fallar la
   construcción entera de la aplicación —`from __future__ import annotations` convierte
   `-> None` en `NoneType`, que FastAPI lee como response model de un 204— y ningún test
   de dominio ni de aplicación lo habría visto.
2. **Que el ámbito rechace de verdad**, no sólo que la pantalla esconda. El criterio de
   aceptación de HU-E4-04 dice «el sistema no ofrece esa categoría», y esconder no es
   rechazar: acá se manda la asignación imposible a mano y se espera un error.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.platform.settings import Settings

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import CONSENTIMIENTO

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"


def _settings() -> Settings:
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


async def _token(http: httpx.AsyncClient, email: str = "ana@empresa.com") -> str:
    respuesta = await http.post(
        "/auth/registro",
        json={
            "email": email,
            "contrasena": CONTRASENA,
            "nombre": "Ana Perez",
            "consentimiento": CONSENTIMIENTO,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _categoria(
    http: httpx.AsyncClient, token: str, *, nombre: str = "VIP", aplica_a: str = "AMBOS"
) -> dict[str, Any]:
    respuesta = await http.post(
        "/categorias", json={"nombre": nombre, "aplica_a": aplica_a}, headers=_auth(token)
    )
    assert respuesta.status_code == 201, respuesta.text
    return dict(respuesta.json())


async def _cliente(http: httpx.AsyncClient, token: str) -> dict[str, Any]:
    respuesta = await http.post(
        "/clientes", json={"nombre": "Panaderia Dona Rosa"}, headers=_auth(token)
    )
    assert respuesta.status_code == 201, respuesta.text
    return dict(respuesta.json())


async def _servicio(http: httpx.AsyncClient, token: str) -> dict[str, Any]:
    respuesta = await http.post(
        "/servicios",
        json={"nombre": "Corte", "precio": "5000.00", "alicuota_iva": "0.21"},
        headers=_auth(token),
    )
    assert respuesta.status_code == 201, respuesta.text
    return dict(respuesta.json())


@pytest.mark.asyncio
async def test_sin_token_no_se_listan_categorias(cliente_http: httpx.AsyncClient) -> None:
    assert (await cliente_http.get("/categorias")).status_code == 401


@pytest.mark.asyncio
async def test_alta_y_listado(cliente_http: httpx.AsyncClient) -> None:
    token = await _token(cliente_http)

    creada = await _categoria(cliente_http, token, nombre="VIP", aplica_a="CLIENTE")
    assert creada["aplica_a"] == "CLIENTE"

    listado = await cliente_http.get("/categorias", headers=_auth(token))
    assert [c["nombre"] for c in listado.json()["categorias"]] == ["Vip"]


@pytest.mark.asyncio
async def test_el_nombre_duplicado_llega_con_su_mensaje(cliente_http: httpx.AsyncClient) -> None:
    """422 y no 409, para que el BFF reenvíe el `detalle` — ver el docstring de la excepción."""
    token = await _token(cliente_http)
    await _categoria(cliente_http, token, nombre="VIP", aplica_a="CLIENTE")

    respuesta = await cliente_http.post(
        "/categorias", json={"nombre": "vip", "aplica_a": "CLIENTE"}, headers=_auth(token)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "Ya existe una categoria con ese nombre en este ambito."


@pytest.mark.asyncio
async def test_el_mismo_nombre_en_otro_ambito_entra(cliente_http: httpx.AsyncClient) -> None:
    token = await _token(cliente_http)
    await _categoria(cliente_http, token, nombre="VIP", aplica_a="CLIENTE")

    await _categoria(cliente_http, token, nombre="VIP", aplica_a="SERVICIO")

    listado = await cliente_http.get("/categorias", headers=_auth(token))
    assert len(listado.json()["categorias"]) == 2


@pytest.mark.asyncio
async def test_el_listado_por_ambito_incluye_las_de_ambos(
    cliente_http: httpx.AsyncClient,
) -> None:
    """Lo que el selector pide, y la razón por la que no filtra del lado del navegador."""
    token = await _token(cliente_http)
    await _categoria(cliente_http, token, nombre="Solo clientes", aplica_a="CLIENTE")
    await _categoria(cliente_http, token, nombre="Las dos", aplica_a="AMBOS")
    await _categoria(cliente_http, token, nombre="Solo servicios", aplica_a="SERVICIO")

    respuesta = await cliente_http.get("/categorias?aplica_a=CLIENTE", headers=_auth(token))

    assert [c["nombre"] for c in respuesta.json()["categorias"]] == ["Las dos", "Solo clientes"]


@pytest.mark.asyncio
async def test_clasificar_y_desclasificar_un_cliente(cliente_http: httpx.AsyncClient) -> None:
    token = await _token(cliente_http)
    cliente = await _cliente(cliente_http, token)
    categoria = await _categoria(cliente_http, token)
    ruta = f"/clientes/{cliente['id']}/categorias"

    asignado = await cliente_http.put(
        ruta, json={"categoria_id": categoria["id"], "asignar": True}, headers=_auth(token)
    )
    assert [c["nombre"] for c in asignado.json()["categorias"]] == ["Vip"]

    leido = await cliente_http.get(ruta, headers=_auth(token))
    assert len(leido.json()["categorias"]) == 1

    quitado = await cliente_http.put(
        ruta, json={"categoria_id": categoria["id"], "asignar": False}, headers=_auth(token)
    )
    assert quitado.json()["categorias"] == []


@pytest.mark.asyncio
async def test_una_categoria_de_servicios_no_se_asigna_a_un_cliente(
    cliente_http: httpx.AsyncClient,
) -> None:
    """RN-01 de verdad: la pantalla no la ofrece, y si igual se manda, la API la rechaza."""
    token = await _token(cliente_http)
    cliente = await _cliente(cliente_http, token)
    categoria = await _categoria(cliente_http, token, nombre="Recurrente", aplica_a="SERVICIO")

    respuesta = await cliente_http.put(
        f"/clientes/{cliente['id']}/categorias",
        json={"categoria_id": categoria["id"], "asignar": True},
        headers=_auth(token),
    )

    assert respuesta.status_code == 409


@pytest.mark.asyncio
async def test_un_servicio_se_clasifica_y_el_listado_filtra(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _token(cliente_http)
    servicio = await _servicio(cliente_http, token)
    categoria = await _categoria(cliente_http, token, nombre="Destacado", aplica_a="SERVICIO")

    await cliente_http.put(
        f"/servicios/{servicio['id']}/categorias",
        json={"categoria_id": categoria["id"], "asignar": True},
        headers=_auth(token),
    )

    filtrado = await cliente_http.get(
        f"/servicios?categoria_id={categoria['id']}", headers=_auth(token)
    )
    assert filtrado.json()["total"] == 1


@pytest.mark.asyncio
async def test_el_listado_de_clientes_filtra_por_categoria(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _token(cliente_http)
    cliente = await _cliente(cliente_http, token)
    await cliente_http.post("/clientes", json={"nombre": "Sin etiqueta"}, headers=_auth(token))
    categoria = await _categoria(cliente_http, token)
    await cliente_http.put(
        f"/clientes/{cliente['id']}/categorias",
        json={"categoria_id": categoria["id"], "asignar": True},
        headers=_auth(token),
    )

    filtrado = await cliente_http.get(
        f"/clientes?categoria_id={categoria['id']}", headers=_auth(token)
    )

    assert filtrado.json()["total"] == 1
    assert filtrado.json()["clientes"][0]["nombre"] == "Panaderia Dona Rosa"


@pytest.mark.asyncio
async def test_eliminar_desclasifica_y_deja_al_cliente_intacto(
    cliente_http: httpx.AsyncClient,
) -> None:
    """El único `DELETE` de la API, y RN-03 completa desde afuera."""
    token = await _token(cliente_http)
    cliente = await _cliente(cliente_http, token)
    categoria = await _categoria(cliente_http, token)
    await cliente_http.put(
        f"/clientes/{cliente['id']}/categorias",
        json={"categoria_id": categoria["id"], "asignar": True},
        headers=_auth(token),
    )

    borrado = await cliente_http.delete(f"/categorias/{categoria['id']}", headers=_auth(token))

    assert borrado.status_code == 204
    sin_categorias = await cliente_http.get(
        f"/clientes/{cliente['id']}/categorias", headers=_auth(token)
    )
    assert sin_categorias.json()["categorias"] == []
    listado = await cliente_http.get("/clientes", headers=_auth(token))
    assert listado.json()["clientes"][0]["nombre"] == "Panaderia Dona Rosa"


@pytest.mark.asyncio
async def test_editar_una_categoria(cliente_http: httpx.AsyncClient) -> None:
    token = await _token(cliente_http)
    categoria = await _categoria(cliente_http, token)

    editada = await cliente_http.put(
        f"/categorias/{categoria['id']}",
        json={"nombre": "Clientes preferenciales", "aplica_a": "CLIENTE"},
        headers=_auth(token),
    )

    assert editada.status_code == 200
    assert editada.json()["nombre"] == "Clientes preferenciales"
    assert editada.json()["aplica_a"] == "CLIENTE"


@pytest.mark.asyncio
async def test_una_empresa_no_ve_las_categorias_de_otra(cliente_http: httpx.AsyncClient) -> None:
    token_a = await _token(cliente_http, "ana@empresa-a.com")
    token_b = await _token(cliente_http, "bruno@empresa-b.com")
    await _categoria(cliente_http, token_a, nombre="De la A")

    listado_b = await cliente_http.get("/categorias", headers=_auth(token_b))

    assert listado_b.json()["categorias"] == []


@pytest.mark.asyncio
async def test_no_se_clasifica_con_una_categoria_de_otra_empresa(
    cliente_http: httpx.AsyncClient,
) -> None:
    """La barrera que la clave foránea no pone: el `SELECT` previo, que sí pasa por la RLS."""
    token_a = await _token(cliente_http, "ana@empresa-a.com")
    token_b = await _token(cliente_http, "bruno@empresa-b.com")
    ajena = await _categoria(cliente_http, token_b, nombre="De la B")
    cliente = await _cliente(cliente_http, token_a)

    respuesta = await cliente_http.put(
        f"/clientes/{cliente['id']}/categorias",
        json={"categoria_id": ajena["id"], "asignar": True},
        headers=_auth(token_a),
    )

    assert respuesta.status_code == 422


@pytest.mark.asyncio
async def test_vip_choca_con_vip_en_otra_escritura(cliente_http: httpx.AsyncClient) -> None:
    """HU-E4-05 RN-04: «VIP» con «Vip» existente, y «VIP   GOLD» con «Vip gold» (422, ver arriba)."""
    token = await _token(cliente_http)
    await _categoria(cliente_http, token, nombre="Vip", aplica_a="CLIENTE")
    await _categoria(cliente_http, token, nombre="Vip gold", aplica_a="CLIENTE")

    for nombre in ("VIP", "VIP   GOLD"):
        respuesta = await cliente_http.post(
            "/categorias", json={"nombre": nombre, "aplica_a": "CLIENTE"}, headers=_auth(token)
        )

        assert respuesta.status_code == 422, respuesta.text
        assert (
            respuesta.json()["detalle"] == "Ya existe una categoria con ese nombre en este ambito."
        )
