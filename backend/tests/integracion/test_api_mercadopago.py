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
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.integrations.infrastructure.mercadopago.simulado import (
    CODIGO_RECHAZADO,
    PREFIJO_SIMULADO,
)
from cheatsheet.contexts.payments.infrastructure.pasarela_simulada import PasarelaSimulada
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import CONSENTIMIENTO

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


# ------------------------------------------------------------------ POST /cobros · D92


async def _crear_cliente(cliente: httpx.AsyncClient, token: str) -> str:
    respuesta = await cliente.post("/clientes", json={"nombre": "Rosa Diaz"}, headers=_auth(token))
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["id"])


def _cobro(cliente_id: str) -> dict[str, str]:
    return {"cliente_id": cliente_id, "monto": "1210.00", "descripcion": "Consulta de septiembre"}


def _con_clave(token: str, clave: UUID | None = None) -> dict[str, str]:
    """Los encabezados de un `POST /cobros`: la clave del pedido es obligatoria (ADR-0013)."""
    return {**_auth(token), "X-Idempotency-Key": str(clave or uuid4())}


@pytest.mark.asyncio
async def test_un_cobro_a_un_cliente_que_no_existe_responde_422_con_el_texto_de_la_historia(
    cliente: httpx.AsyncClient,
) -> None:
    """El rechazo ocurre antes de pedir el link: con un cliente inexistente no se gasta una
    preferencia (el simulado no cuenta, pero el orden lo fija el test unitario del caso de uso)."""
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await cliente.post(
        "/cobros", json=_cobro("00000000-0000-4000-8000-000000000000"), headers=_con_clave(token)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "El cliente seleccionado no existe o esta inactivo."


@pytest.mark.asyncio
async def test_un_cobro_a_un_cliente_valido_responde_201(cliente: httpx.AsyncClient) -> None:
    token = await _registrar(cliente, "ana@empresa.com")
    cliente_id = await _crear_cliente(cliente, token)

    respuesta = await cliente.post("/cobros", json=_cobro(cliente_id), headers=_con_clave(token))

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["cliente_id"] == cliente_id


@pytest.mark.asyncio
async def test_un_cobro_a_un_cliente_inactivo_responde_422(cliente: httpx.AsyncClient) -> None:
    token = await _registrar(cliente, "ana@empresa.com")
    cliente_id = await _crear_cliente(cliente, token)
    await cliente.put(
        f"/clientes/{cliente_id}/estado", json={"activo": False}, headers=_auth(token)
    )

    respuesta = await cliente.post("/cobros", json=_cobro(cliente_id), headers=_con_clave(token))

    assert respuesta.status_code == 422


@pytest.mark.asyncio
async def test_un_monto_no_finito_o_gigante_responde_422_y_no_500(
    cliente: httpx.AsyncClient,
) -> None:
    token = await _registrar(cliente, "ana@empresa.com")
    cliente_id = await _crear_cliente(cliente, token)

    for monto in ("NaN", "Infinity", "100000000.01"):
        respuesta = await cliente.post(
            "/cobros", json={**_cobro(cliente_id), "monto": monto}, headers=_con_clave(token)
        )
        assert respuesta.status_code == 422, (monto, respuesta.text)


# ------------------------------------------------------------------ la clave del pedido · ADR-0013


@pytest.fixture
def pasarela_contada(monkeypatch: pytest.MonkeyPatch) -> PasarelaSimulada:
    """Una pasarela simulada propia del test: `links` cuenta las preferencias que se pidieron."""
    pasarela = PasarelaSimulada()

    def _la_misma(*_: object) -> PasarelaSimulada:
        return pasarela

    monkeypatch.setattr("cheatsheet.api.routers.cobros.armar_pasarela", _la_misma)
    return pasarela


@pytest.mark.asyncio
async def test_sin_la_clave_del_pedido_o_con_una_que_no_es_uuid_responde_422(
    cliente: httpx.AsyncClient,
) -> None:
    """Caso 8. Obligatoria (P1) y con formato acotado (P4)."""
    token = await _registrar(cliente, "ana@empresa.com")
    cliente_id = await _crear_cliente(cliente, token)

    sin = await cliente.post("/cobros", json=_cobro(cliente_id), headers=_auth(token))
    mala = await cliente.post(
        "/cobros",
        json=_cobro(cliente_id),
        headers={**_auth(token), "X-Idempotency-Key": "no-es-un-uuid"},
    )

    assert sin.status_code == 422, sin.text
    assert sin.json()["detalle"] == (
        "Falta la clave de idempotencia del pedido (encabezado X-Idempotency-Key)."
    )
    assert mala.status_code == 422, mala.text
    assert mala.json()["detalle"] == "La clave de idempotencia del pedido no es valida."


@pytest.mark.asyncio
async def test_el_mismo_pedido_repetido_devuelve_el_mismo_cobro_y_una_sola_preferencia(
    cliente: httpx.AsyncClient, pasarela_contada: PasarelaSimulada
) -> None:
    """Caso 9. Dos 201 con el mismo `id`; MercadoPago recibió una sola preferencia."""
    token = await _registrar(cliente, "ana@empresa.com")
    cliente_id = await _crear_cliente(cliente, token)
    encabezados = _con_clave(token)

    primero = await cliente.post("/cobros", json=_cobro(cliente_id), headers=encabezados)
    segundo = await cliente.post("/cobros", json=_cobro(cliente_id), headers=encabezados)

    assert primero.status_code == 201, primero.text
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["id"] == primero.json()["id"]
    assert len(pasarela_contada.links) == 1
    listado = await cliente.get("/cobros", headers=_auth(token))
    assert len(listado.json()["cobros"]) == 1


@pytest.mark.asyncio
async def test_la_misma_clave_con_otro_cuerpo_responde_422_y_no_crea_nada(
    cliente: httpx.AsyncClient, pasarela_contada: PasarelaSimulada
) -> None:
    """Caso 10. Es un error del pedido: 422 `ClaveDeIdempotenciaReusada`, no 409."""
    token = await _registrar(cliente, "ana@empresa.com")
    cliente_id = await _crear_cliente(cliente, token)
    encabezados = _con_clave(token)
    await cliente.post("/cobros", json=_cobro(cliente_id), headers=encabezados)

    otro = await cliente.post(
        "/cobros", json={**_cobro(cliente_id), "monto": "999.00"}, headers=encabezados
    )

    assert otro.status_code == 422, otro.text
    assert otro.json()["error"] == "ClaveDeIdempotenciaReusada"
    assert "otros datos" in otro.json()["detalle"]
    assert len(pasarela_contada.links) == 1
