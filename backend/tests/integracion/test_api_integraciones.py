"""PAN-CFG-INT end to end — cases 10, 11, 14, 15 and 18 of the plan.

The whole stack in one process: ASGI app, `EmpresaMiddleware` verifying a real JWT, the
router, the use cases, the PostgreSQL repository, the real AES-GCM cipher and Row-Level
Security. No socket is opened except to the local database.

**Why this file exists even though every layer has its own test.** Three of the listed
risks live exactly in the seams: that one company can see another's configuration (RLS is
a database feature, and a double would pass while proving nothing), that a decrypted
credential leaks into a response, and that an Operador who tries to connect gets a 500
instead of a 403.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.platform.settings import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import CONSENTIMIENTO

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"

#: Estos tests son sobre el camino **genérico** —cifrado, idempotencia, RLS y bitácora—,
#: no sobre ningún proveedor. Se conectan contra MercadoPago porque alguno hay que usar, y
#: desde `conexion-mercadopago` eso significa recorrer su OAuth2: **ya no queda un sistema
#: con adaptador genérico**, que es justamente lo que esa unidad terminó. Lo específico de
#: cada proveedor vive en `test_arca_ciclo_de_vida.py` y `test_api_mercadopago.py`.
SISTEMA = "MERCADOPAGO"

#: Para el único caso que sigue usando el endpoint directo: un sistema sin conector.
CREDENCIAL = b"una-credencial-opaca-de-prueba"


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest_asyncio.fixture
async def cliente(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        yield cliente
    await recursos.cerrar()


async def _registrar(cliente: httpx.AsyncClient, email: str) -> str:
    respuesta = await cliente.post(
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


def _conexion(contenido: bytes = CREDENCIAL) -> dict[str, object]:
    return {"contenido": base64.b64encode(contenido).decode(), "parametros": {}}


async def _conectar(cliente: httpx.AsyncClient, token: str) -> httpx.Response:
    """Las dos mitades del OAuth2, que es la única forma de conectar MercadoPago.

    El adaptador simulado devuelve un redirect a la pantalla con el código puesto, así que
    esto recorre exactamente lo que recorre un navegador.
    """
    inicio = await cliente.post(f"/integraciones/{SISTEMA}/autorizacion", headers=_auth(token))
    assert inicio.status_code == 200, inicio.text
    consulta = parse_qs(urlparse(str(inicio.json()["url"])).query)
    return await cliente.post(
        f"/integraciones/{SISTEMA}/autorizacion/canje",
        headers=_auth(token),
        json={"codigo": consulta["code"][0], "estado": consulta["state"][0]},
    )


@pytest.mark.asyncio
async def test_sin_token_no_se_ven_las_integraciones(cliente: httpx.AsyncClient) -> None:
    respuesta = await cliente.get("/integraciones")

    assert respuesta.status_code == 401


@pytest.mark.asyncio
async def test_una_empresa_nueva_ve_las_cuatro_sin_conectar(cliente: httpx.AsyncClient) -> None:
    """The four cards come from the enum, so an empty table still renders a screen."""
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await cliente.get("/integraciones", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert len(cuerpo["integraciones"]) == 4
    assert all(i["estado"] == "NO_CONECTADO" for i in cuerpo["integraciones"])
    assert cuerpo["verificado_en"] is None


@pytest.mark.asyncio
async def test_conectar_verificar_y_ver_el_estado(cliente: httpx.AsyncClient) -> None:
    """The unit's deliverable in one test, against the real cipher and the real table."""
    token = await _registrar(cliente, "ana@empresa.com")

    conexion = await _conectar(cliente, token)
    assert conexion.status_code == 200, conexion.text
    assert conexion.json()["estado"] == "CONECTADO"
    # Derived from APP_ENV, never from the request (decision D-b).
    assert conexion.json()["ambiente"] == "HOMOLOGACION"

    verificacion = await cliente.post("/integraciones/verificacion", headers=_auth(token))
    assert verificacion.status_code == 200, verificacion.text
    cuerpo = verificacion.json()
    arca = next(i for i in cuerpo["integraciones"] if i["sistema"] == SISTEMA)
    assert arca["estado"] == "CONECTADO"
    assert arca["configurada"] is True
    assert cuerpo["verificado_en"] is not None


@pytest.mark.asyncio
async def test_la_credencial_nunca_vuelve_en_la_respuesta(cliente: httpx.AsyncClient) -> None:
    """Case 15. The boundary ADR-0003 draws, restated at the HTTP edge."""
    token = await _registrar(cliente, "ana@empresa.com")
    conectada = await _conectar(cliente, token)
    assert conectada.status_code == 200, conectada.text

    listado = await cliente.get("/integraciones", headers=_auth(token))
    verificacion = await cliente.post("/integraciones/verificacion", headers=_auth(token))

    for respuesta in (listado, verificacion, conectada):
        crudo = respuesta.text
        assert "CERTIFICATE" not in crudo
        assert "credencial" not in crudo
        assert "acceso-" not in crudo
        assert "refresco-" not in crudo


@pytest.mark.asyncio
async def test_la_credencial_se_guarda_cifrada(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Read the row as the owner: what is on disk must not be the credential."""
    token = await _registrar(cliente, "ana@empresa.com")
    assert (await _conectar(cliente, token)).status_code == 200

    async with engine_dueno.begin() as conexion:
        filas = (
            await conexion.execute(
                text(
                    "SELECT credencial_contenido_cifrado, credencial_algoritmo "
                    "FROM configuracion_de_integracion"
                )
            )
        ).all()

    assert len(filas) == 1
    contenido, algoritmo = filas[0]
    assert b"acceso-" not in bytes(contenido)
    assert b"refresco-" not in bytes(contenido)
    assert algoritmo == "AES-256-GCM/v1"


@pytest.mark.asyncio
async def test_conectar_dos_veces_deja_una_sola_fila(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Case 11, against the unique index rather than against the in-memory dictionary."""
    token = await _registrar(cliente, "ana@empresa.com")

    for _ in range(2):
        respuesta = await _conectar(cliente, token)
        assert respuesta.status_code == 200, respuesta.text

    async with engine_dueno.begin() as conexion:
        total = (
            await conexion.execute(text("SELECT count(*) FROM configuracion_de_integracion"))
        ).scalar_one()

    assert total == 1


@pytest.mark.asyncio
async def test_una_empresa_no_ve_la_configuracion_de_otra(cliente: httpx.AsyncClient) -> None:
    """Case 14 — RLS is a database feature, so this cannot be checked against a double."""
    token_a = await _registrar(cliente, "ana@empresa-a.com")
    token_b = await _registrar(cliente, "beto@empresa-b.com")

    assert (await _conectar(cliente, token_a)).status_code == 200

    de_b = await cliente.get("/integraciones", headers=_auth(token_b))

    assert de_b.status_code == 200
    assert all(not i["configurada"] for i in de_b.json()["integraciones"])


@pytest.mark.asyncio
async def test_un_cambio_de_estado_queda_en_la_bitacora(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Case 10 — connecting is a transition, and HS-T5 says transitions are recorded."""
    token = await _registrar(cliente, "ana@empresa.com")
    assert (await _conectar(cliente, token)).status_code == 200

    async with engine_dueno.begin() as conexion:
        filas = (
            await conexion.execute(
                text(
                    "SELECT accion, entidad_afectada, usuario_id FROM registro_de_auditoria "
                    "WHERE modulo = 'integrations'"
                )
            )
        ).all()

    assert len(filas) == 1
    accion, entidad, usuario_id = filas[0]
    assert SISTEMA in accion
    assert entidad == f"ConfiguracionDeIntegracion:{SISTEMA}"
    # HS-T5 RN-02: who initiated it. Not the system — a person clicked Conectar.
    assert usuario_id is not None


@pytest.mark.asyncio
async def test_un_sistema_de_otro_epico_no_se_puede_conectar(
    cliente: httpx.AsyncClient,
) -> None:
    """Google Sheets has a card but no connector until epic 4."""
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await cliente.put(
        "/integraciones/GOOGLE_SHEETS/conexion", headers=_auth(token), json=_conexion()
    )

    assert respuesta.status_code == 422, respuesta.text


@pytest.mark.asyncio
async def test_un_contenido_que_no_es_base64_es_rechazado(cliente: httpx.AsyncClient) -> None:
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await cliente.put(
        f"/integraciones/{SISTEMA}/conexion",
        headers=_auth(token),
        json={"contenido": "no es base64!!", "parametros": {}},
    )

    assert respuesta.status_code == 422, respuesta.text
