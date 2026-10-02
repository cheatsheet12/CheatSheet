"""Los endpoints de la corrección de datos existentes, de punta a punta — HU-E4-05 RN-09.

Tres costuras que ninguna prueba de capa mira:

1. **El rol**: el guard es el caso de uso, no la pantalla. Un Operador recibe 403 en los
   cuatro endpoints, y el informe —que es solo lectura— tampoco se le abre.
2. **La bitácora**: la fila `correccion_de_datos_aplicada` existe y lleva conteos, nunca un
   nombre.
3. **El 409** cuando otra corrección de la misma empresa tiene el turno, y el 422 de una
   corrida que no existe.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.platform.settings import Settings
from cheatsheet.workers import tasks_identity
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.test_api_usuarios import DespachadorEspia

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
NOMBRE_DE_PRUEBA = "JUAN PEREZ"


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest.fixture
def despachador(monkeypatch: pytest.MonkeyPatch) -> DespachadorEspia:
    espia = DespachadorEspia()
    monkeypatch.setattr(tasks_identity, "_despachador", lambda _settings: espia)
    return espia


@pytest_asyncio.fixture
async def cliente_http(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as http:
        yield http
    await recursos.cerrar()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _administrador(http: httpx.AsyncClient) -> str:
    respuesta = await http.post(
        "/auth/registro",
        json={"email": "ana@empresa.com", "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["access_token"])


async def _operador(
    http: httpx.AsyncClient, despachador: DespachadorEspia, token_admin: str
) -> str:
    invitacion = await http.post(
        "/usuarios/invitaciones",
        headers=_auth(token_admin),
        json={"email": "beto@empresa.com", "rol": "OPERADOR"},
    )
    assert invitacion.status_code == 201, invitacion.text
    aceptacion = await http.post(
        "/auth/invitaciones/aceptar",
        json={
            "token": despachador.tareas[0]["kwargs"]["token"],
            "nombre": "Beto Gomez",
            "contrasena": CONTRASENA,
        },
    )
    assert aceptacion.status_code == 201, aceptacion.text
    ingreso = await http.post(
        "/auth/login", json={"email": "beto@empresa.com", "contrasena": CONTRASENA}
    )
    return str(ingreso.json()["access_token"])


async def _empresa_y_datos_viejos(engine_dueno: AsyncEngine) -> uuid.UUID:
    """The only company in the database, with a client whose name predates normalization."""
    async with engine_dueno.begin() as conexion:
        empresa_id = (await conexion.execute(text("SELECT id FROM empresa"))).scalar_one()
        await conexion.execute(
            text(
                "INSERT INTO cliente (id, empresa_id, nombre, origen, presente_en_planilla, "
                "activo, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :e, :nombre, 'PANEL', false, true, now(), now())"
            ),
            {"e": empresa_id, "nombre": NOMBRE_DE_PRUEBA},
        )
    return uuid.UUID(str(empresa_id))


@pytest.mark.asyncio
async def test_sin_token_no_se_corrige(cliente_http: httpx.AsyncClient) -> None:
    assert (await cliente_http.get("/datos-maestros/correccion/informe")).status_code == 401
    assert (await cliente_http.post("/datos-maestros/correccion")).status_code == 401


@pytest.mark.asyncio
async def test_el_administrador_informa_aplica_y_deja_la_fila_en_la_bitacora(
    cliente_http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    token = await _administrador(cliente_http)
    await _empresa_y_datos_viejos(engine_dueno)

    informe = await cliente_http.get("/datos-maestros/correccion/informe", headers=_auth(token))
    assert informe.status_code == 200, informe.text
    assert informe.json()["a_corregir"]["CLIENTE"] == 1
    assert informe.json()["ejemplos"]["CLIENTE"] == [
        {"antes": NOMBRE_DE_PRUEBA, "despues": "Juan Perez"}
    ]

    aplicada = await cliente_http.post("/datos-maestros/correccion", headers=_auth(token))
    assert aplicada.status_code == 201, aplicada.text
    cuerpo: dict[str, Any] = aplicada.json()
    assert cuerpo["conteos"]["clientes"] == 1

    async with engine_dueno.connect() as conexion:
        fila = (
            await conexion.execute(
                text(
                    "SELECT entidad_afectada, detalle FROM registro_de_auditoria "
                    "WHERE accion = 'correccion_de_datos_aplicada'"
                )
            )
        ).one()
    assert fila.entidad_afectada == f"correccion:{cuerpo['corrida_id']}"
    assert fila.detalle["clientes"] == "1"
    assert "perez" not in json.dumps(fila.detalle).lower()

    corridas = await cliente_http.get("/datos-maestros/correccion/corridas", headers=_auth(token))
    assert [c["corrida_id"] for c in corridas.json()["corridas"]] == [cuerpo["corrida_id"]]

    restaurada = await cliente_http.post(
        f"/datos-maestros/correccion/{cuerpo['corrida_id']}/restauracion", headers=_auth(token)
    )
    assert restaurada.status_code == 200, restaurada.text
    assert restaurada.json() == {"restaurados": 1, "conservados": 0}


@pytest.mark.asyncio
async def test_un_operador_recibe_403_en_los_cuatro_endpoints(
    cliente_http: httpx.AsyncClient, despachador: DespachadorEspia
) -> None:
    token_admin = await _administrador(cliente_http)
    token = await _operador(cliente_http, despachador, token_admin)
    corrida = uuid.uuid4()

    respuestas = [
        await cliente_http.get("/datos-maestros/correccion/informe", headers=_auth(token)),
        await cliente_http.post("/datos-maestros/correccion", headers=_auth(token)),
        await cliente_http.get("/datos-maestros/correccion/corridas", headers=_auth(token)),
        await cliente_http.post(
            f"/datos-maestros/correccion/{corrida}/restauracion", headers=_auth(token)
        ),
    ]

    assert [r.status_code for r in respuestas] == [403, 403, 403, 403]
    assert {r.json()["error"] for r in respuestas} == {"PermisoDenegado"}


@pytest.mark.asyncio
async def test_restaurar_una_corrida_inexistente_responde_con_su_mensaje(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _administrador(cliente_http)

    respuesta = await cliente_http.post(
        f"/datos-maestros/correccion/{uuid.uuid4()}/restauracion", headers=_auth(token)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["error"] == "CorridaNoEncontrada"


@pytest.mark.asyncio
async def test_con_el_turno_tomado_la_aplicacion_responde_409(
    cliente_http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    token = await _administrador(cliente_http)
    empresa_id = await _empresa_y_datos_viejos(engine_dueno)
    clave = text("SELECT hashtextextended('correccion_de_datos:' || :e, 0)")
    async with engine_dueno.connect() as conexion:
        valor = (await conexion.execute(clave, {"e": str(empresa_id)})).scalar_one()
        await conexion.execute(text("SELECT pg_advisory_lock(:k)"), {"k": valor})
        try:
            respuesta = await cliente_http.post("/datos-maestros/correccion", headers=_auth(token))
        finally:
            await conexion.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": valor})

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["error"] == "CorreccionEnCurso"
    async with engine_dueno.connect() as conexion:
        nombre = (await conexion.execute(text("SELECT nombre FROM cliente"))).scalar_one()
    assert nombre == NOMBRE_DE_PRUEBA
