"""MercadoPago de punta a punta contra PostgreSQL y Redis reales.

Tres cosas no se pueden probar con un doble, y son las que este archivo cubre:

- que el **`state` viva de verdad en Redis** y se consuma una sola vez, incluso entre dos
  pedidos distintos — que es como llega en producción;
- que los dos tokens queden **cifrados en la base** y no salgan por ninguna respuesta;
- que reconectar reemplace la fila en lugar de acumular otra, contra el índice único real.

MercadoPago sigue simulado, siempre. El adaptador simulado recorre el redirect entero, así
que lo que se ejercita acá es el flujo completo y no un atajo.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.integrations.infrastructure.mercadopago.simulado import (
    CODIGO_RECHAZADO,
    PREFIJO_SIMULADO,
)
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

requiere_redis = pytest.mark.skipif(
    os.environ.get("REDIS_URL", "").strip() == "",
    reason="Necesita Redis: el `state` de la autorizacion vive ahi.",
)

pytestmark = [requiere_base, requiere_redis, pytest.mark.integration]

#: Cómo empieza cada token que fabrica el simulado. Se busca esto y no `PREFIJO_SIMULADO`
#: a secas: el apodo de la cuenta también dice «SIMULADO», y con razón.
MARCAS_DE_TOKEN = (f"{PREFIJO_SIMULADO}-acceso-", f"{PREFIJO_SIMULADO}-refresco-")

CONTRASENA = "una-contrasena-larga"


def _settings(**extra: object) -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
        **extra,  # type: ignore[arg-type]
    )


@pytest_asyncio.fixture
async def recursos(esquema_migrado: None) -> AsyncIterator[Recursos]:
    creados = Recursos.crear(_settings())
    yield creados
    await creados.cerrar()


@pytest_asyncio.fixture
async def cliente(recursos: Recursos) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(recursos.settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as abierto:
        yield abierto


async def _registrar(cliente: httpx.AsyncClient, email: str) -> str:
    respuesta = await cliente.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _empresa_de(token: str) -> EmpresaId:
    payload = token.split(".")[1]
    relleno = "=" * (-len(payload) % 4)
    return EmpresaId(UUID(json.loads(base64.urlsafe_b64decode(payload + relleno))["empresa_id"]))


async def _iniciar(cliente: httpx.AsyncClient, token: str) -> tuple[str, str]:
    """La primera mitad: devuelve el código y el `state` que el proveedor mandaría de vuelta."""
    respuesta = await cliente.post("/integraciones/MERCADOPAGO/autorizacion", headers=_auth(token))
    assert respuesta.status_code == 200, respuesta.text
    consulta = parse_qs(urlparse(str(respuesta.json()["url"])).query)
    return consulta["code"][0], consulta["state"][0]


async def _canjear(
    cliente: httpx.AsyncClient, token: str, codigo: str, estado: str
) -> httpx.Response:
    return await cliente.post(
        "/integraciones/MERCADOPAGO/autorizacion/canje",
        headers=_auth(token),
        json={"codigo": codigo, "estado": estado},
    )


@pytest.mark.asyncio
async def test_la_vuelta_completa_deja_la_cuenta_conectada(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Los dos criterios de aceptación felices de HU-E2-02, en un solo recorrido."""
    token = await _registrar(cliente, "ana@empresa.com")
    codigo, estado = await _iniciar(cliente, token)

    respuesta = await _canjear(cliente, token, codigo, estado)

    assert respuesta.status_code == 200, respuesta.text
    vista = respuesta.json()
    assert vista["estado"] == "CONECTADO"
    assert vista["ambiente"] == "HOMOLOGACION"
    assert vista["etiqueta"]
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT count(*) FROM registro_de_auditoria WHERE modulo = 'integrations'")
        )
        assert filas.scalar_one() == 1


@pytest.mark.asyncio
async def test_los_tokens_quedan_cifrados_y_no_salen_por_la_api(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """RN-01. Ni en la fila en claro, ni en la respuesta, ni en los parámetros."""
    token = await _registrar(cliente, "ana@empresa.com")
    codigo, estado = await _iniciar(cliente, token)
    respuesta = await _canjear(cliente, token, codigo, estado)

    for marca in MARCAS_DE_TOKEN:
        assert marca not in respuesta.text
    async with engine_dueno.begin() as conexion:
        fila = await conexion.execute(
            text(
                "SELECT credencial_contenido_cifrado, credencial_algoritmo, parametros "
                "FROM configuracion_de_integracion WHERE sistema = 'MERCADOPAGO'"
            )
        )
        cifrado, algoritmo, parametros = fila.one()
    assert algoritmo.startswith("AES-256-GCM")
    for marca in MARCAS_DE_TOKEN:
        assert marca.encode() not in bytes(cifrado)
        assert marca not in json.dumps(parametros)
    # Y el verificador de PKCE tampoco quedó guardado: es efímero por definición.
    assert "code_verifier" not in json.dumps(parametros)


@pytest.mark.asyncio
async def test_el_mismo_estado_no_sirve_dos_veces(cliente: httpx.AsyncClient) -> None:
    """El `state` vive en Redis y se consume con `GETDEL`: el segundo pedido no lo encuentra."""
    token = await _registrar(cliente, "ana@empresa.com")
    codigo, estado = await _iniciar(cliente, token)
    assert (await _canjear(cliente, token, codigo, estado)).status_code == 200

    repetido = await _canjear(cliente, token, codigo, estado)

    assert repetido.status_code == 422, repetido.text
    assert "iniciar la conexion" in repetido.text


@pytest.mark.asyncio
async def test_el_estado_de_una_empresa_no_conecta_a_la_otra(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 4 contra el sistema real: dos empresas, dos sesiones, un `state` robado."""
    token_a = await _registrar(cliente, "ana@empresa.com")
    token_b = await _registrar(cliente, "beto@otra.com")
    codigo, estado = await _iniciar(cliente, token_a)

    respuesta = await _canjear(cliente, token_b, codigo, estado)

    assert respuesta.status_code == 422, respuesta.text
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT count(*) FROM configuracion_de_integracion WHERE empresa_id = :empresa"),
            {"empresa": str(_empresa_de(token_b))},
        )
        assert filas.scalar_one() == 0


@pytest.mark.asyncio
async def test_un_codigo_rechazado_no_escribe_ninguna_fila(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Segundo criterio de HU-E2-01, que HU-E2-02 hereda: se indica el error y no se guarda."""
    token = await _registrar(cliente, "ana@empresa.com")
    _, estado = await _iniciar(cliente, token)

    respuesta = await _canjear(cliente, token, CODIGO_RECHAZADO, estado)

    assert respuesta.status_code == 422, respuesta.text
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(text("SELECT count(*) FROM configuracion_de_integracion"))
        assert filas.scalar_one() == 0


@pytest.mark.asyncio
async def test_reconectar_reemplaza_la_fila_en_lugar_de_acumular(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 15, contra el índice único real."""
    token = await _registrar(cliente, "ana@empresa.com")
    for _ in range(2):
        codigo, estado = await _iniciar(cliente, token)
        assert (await _canjear(cliente, token, codigo, estado)).status_code == 200

    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT count(*) FROM configuracion_de_integracion WHERE sistema = 'MERCADOPAGO'")
        )
        assert filas.scalar_one() == 1


@pytest.mark.asyncio
async def test_la_funcion_de_barrido_ve_a_la_empresa_conectada(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """La tercera perforación de RLS: devuelve `empresa_id` y nada más.

    Se prueba con el rol de la aplicación —no con el dueño— porque de eso se trata: sin la
    función, Beat no ve nada, que es lo correcto y también lo inservible.
    """
    token = await _registrar(cliente, "ana@empresa.com")
    codigo, estado = await _iniciar(cliente, token)
    await _canjear(cliente, token, codigo, estado)

    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT empresa_id FROM empresas_con_integracion_de_mercadopago()")
        )
        empresas = [str(valor) for (valor,) in filas.all()]

    assert empresas == [str(_empresa_de(token))]
