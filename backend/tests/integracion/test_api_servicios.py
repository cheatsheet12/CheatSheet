"""Los endpoints del catálogo de servicios, de punta a punta.

La costura que ninguna prueba unitaria mira, y que en esta unidad es **la del dinero**:
que un número JSON no se convierta en un `Decimal` en silencio. `precio` viaja como
string precisamente para que no pueda, y este archivo lo comprueba desde afuera —
mandando el número y esperando un 422, no un servicio creado con centavos binarios.
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


async def _registrar_empresa(http: httpx.AsyncClient, email: str) -> str:
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


def _cuerpo(**campos: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "nombre": "Corte de pelo",
        "precio": "5000.00",
        "alicuota_iva": "0.21",
        "agendable": False,
    }
    base.update(campos)
    return base


async def _crear(http: httpx.AsyncClient, token: str, **campos: Any) -> httpx.Response:
    return await http.post("/servicios", json=_cuerpo(**campos), headers=_auth(token))


@pytest.mark.asyncio
async def test_sin_token_no_se_listan_servicios(cliente_http: httpx.AsyncClient) -> None:
    respuesta = await cliente_http.get("/servicios")

    assert respuesta.status_code == 401


@pytest.mark.asyncio
async def test_alta_y_listado(cliente_http: httpx.AsyncClient) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    creado = await _crear(cliente_http, token)
    assert creado.status_code == 201, creado.text
    assert creado.json()["origen"] == "PANEL"
    assert creado.json()["precio"] == "5000.00"
    assert creado.json()["alicuota_iva"] == "0.21"

    listado = await cliente_http.get("/servicios", headers=_auth(token))
    assert listado.json()["total"] == 1


@pytest.mark.asyncio
async def test_un_precio_numerico_en_el_json_se_rechaza(cliente_http: httpx.AsyncClient) -> None:
    """**El test del dinero.**

    Un `number` de JSON es un float de 64 bits. Si el campo se declarara `Decimal`,
    pydantic lo aceptaría y el error binario entraría al sistema sin que nadie lo note.
    Declarado como `str`, la respuesta es 422 y el servicio no existe.
    """
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await cliente_http.post(
        "/servicios", json=_cuerpo(precio=19999.99), headers=_auth(token)
    )

    assert respuesta.status_code == 422
    listado = await cliente_http.get("/servicios", headers=_auth(token))
    assert listado.json()["total"] == 0


@pytest.mark.asyncio
async def test_un_precio_que_no_es_un_numero_responde_el_mensaje_de_la_historia(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, precio="gratis")

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "El precio debe ser mayor a cero."


@pytest.mark.asyncio
async def test_precio_cero_responde_el_mensaje_de_la_historia(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, precio="0")

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "El precio debe ser mayor a cero."


@pytest.mark.asyncio
async def test_agendable_sin_duracion_responde_el_mensaje_de_la_historia(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, agendable=True)

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "La duracion es obligatoria para servicios agendables."


RANGO_DE_DURACION = "La duracion debe estar entre 5 y 480 minutos."


@pytest.mark.asyncio
@pytest.mark.parametrize("duracion", [4, 99999])
async def test_una_duracion_fuera_del_rango_responde_el_mensaje_de_rango(
    cliente_http: httpx.AsyncClient, duracion: int
) -> None:
    """La regla vive en el dominio: llega como `detalle`, no como un 422 de Pydantic."""
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, agendable=True, duracion_estandar_min=duracion)

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == RANGO_DE_DURACION


@pytest.mark.asyncio
async def test_editar_con_una_duracion_fuera_del_rango_responde_el_mensaje_de_rango(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")
    servicio_id = (await _crear(cliente_http, token)).json()["id"]

    respuesta = await cliente_http.put(
        f"/servicios/{servicio_id}",
        json=_cuerpo(agendable=True, duracion_estandar_min=481),
        headers=_auth(token),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == RANGO_DE_DURACION


@pytest.mark.asyncio
@pytest.mark.parametrize("duracion", [5, 480])
async def test_los_limites_de_la_duracion_se_aceptan(
    cliente_http: httpx.AsyncClient, duracion: int
) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, agendable=True, duracion_estandar_min=duracion)

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["duracion_estandar_min"] == duracion


@pytest.mark.asyncio
async def test_una_alicuota_que_no_esta_en_el_enum_se_rechaza(
    cliente_http: httpx.AsyncClient,
) -> None:
    """RN-02: el catálogo es cerrado, y lo cierra el esquema del endpoint."""
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, alicuota_iva="0.27")

    assert respuesta.status_code == 422


@pytest.mark.asyncio
async def test_el_precio_se_redondea_a_centavos_de_punta_a_punta(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")

    respuesta = await _crear(cliente_http, token, precio="1234.567")

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["precio"] == "1234.57"


@pytest.mark.asyncio
async def test_editar_y_cambiar_estado(cliente_http: httpx.AsyncClient) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")
    creado = await _crear(cliente_http, token)
    servicio_id = creado.json()["id"]

    editado = await cliente_http.put(
        f"/servicios/{servicio_id}",
        json=_cuerpo(
            nombre="Corte y barba", precio="7000", agendable=True, duracion_estandar_min=45
        ),
        headers=_auth(token),
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["agendable"] is True
    assert editado.json()["duracion_estandar_min"] == 45
    assert editado.json()["origen"] == "PANEL"

    desactivado = await cliente_http.put(
        f"/servicios/{servicio_id}/estado", json={"activo": False}, headers=_auth(token)
    )
    assert desactivado.json()["activo"] is False

    activos = await cliente_http.get("/servicios?solo_activos=true", headers=_auth(token))
    assert activos.json()["total"] == 0


@pytest.mark.asyncio
async def test_no_existe_el_borrado(cliente_http: httpx.AsyncClient) -> None:
    token = await _registrar_empresa(cliente_http, "ana@empresa.com")
    creado = await _crear(cliente_http, token)

    respuesta = await cliente_http.delete(f"/servicios/{creado.json()['id']}", headers=_auth(token))

    assert respuesta.status_code == 405


@pytest.mark.asyncio
async def test_una_empresa_no_ve_los_servicios_de_otra(cliente_http: httpx.AsyncClient) -> None:
    token_a = await _registrar_empresa(cliente_http, "ana@empresa-a.com")
    token_b = await _registrar_empresa(cliente_http, "bruno@empresa-b.com")
    await _crear(cliente_http, token_a, nombre="De la empresa A")

    listado_b = await cliente_http.get("/servicios", headers=_auth(token_b))

    assert listado_b.json()["total"] == 0
