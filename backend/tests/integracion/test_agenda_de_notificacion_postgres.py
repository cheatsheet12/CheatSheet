"""La agenda de notificación de punta a punta (caso 5 del plan de recordatorio-de-turno).

Dos costuras que ninguna prueba de capa mira:

1. **La API**: `PUT /reglas/agenda` guarda y reemplaza, devuelve el rechazo del dominio como 422
   con su frase y rechaza al Operador (el guarda es del caso de uso).
2. **El aislamiento**: la agenda de la empresa A no se ve en la B (RLS sobre `regla_de_negocio`).

Requiere PostgreSQL (`requiere_base`): se saltea sin base y corre en la CI.
"""

from __future__ import annotations

import base64
import json
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
from cheatsheet.workers import tasks_identity

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import CONSENTIMIENTO, VERSION_DE_PRIVACIDAD
from tests.integracion.test_api_usuarios import DespachadorEspia

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CONTRASENA = "una-contrasena-larga"
MENSAJE_RANGO = "Las horas de anticipación deben estar entre 1 y 168."
MENSAJE_PRIORIDAD = "La prioridad de una regla no puede ser negativa"
MENSAJE_REPETIDOS = "No puede haber dos recordatorios con la misma anticipación."


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


async def _registrar(http: httpx.AsyncClient, email: str) -> str:
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
            "version_privacidad": VERSION_DE_PRIVACIDAD,
        },
    )
    assert aceptacion.status_code == 201, aceptacion.text
    ingreso = await http.post(
        "/auth/login", json={"email": "beto@empresa.com", "contrasena": CONTRASENA}
    )
    return str(ingreso.json()["access_token"])


def _agenda(*horas: int, prioridad: int = 0) -> dict[str, Any]:
    return {"recordatorios": [{"horas_antes": h} for h in horas], "prioridad": prioridad}


def _reglas_de_agenda(listado: httpx.Response) -> list[dict[str, Any]]:
    return [uno for uno in listado.json()["reglas"] if uno["tipo"] == "AGENDA_DE_NOTIFICACION"]


def _decodificar(token: str) -> dict[str, Any]:
    carga = token.split(".")[1]
    carga += "=" * (-len(carga) % 4)
    return dict(json.loads(base64.urlsafe_b64decode(carga)))


class TestApiDeLaAgenda:
    async def test_el_administrador_guarda_y_el_listado_la_devuelve_ordenada(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token = await _registrar(cliente_http, "agenda-alta@test.local")

        guardada = await cliente_http.put(
            "/reglas/agenda", headers=_auth(token), json=_agenda(2, 48)
        )

        assert guardada.status_code == 200, guardada.text
        [regla] = _reglas_de_agenda(await cliente_http.get("/reglas", headers=_auth(token)))
        assert regla["activa"] is True
        assert regla["configuracion"] == {
            "recordatorios": [{"horas_antes": 48}, {"horas_antes": 2}]
        }

    async def test_guardar_dos_veces_reemplaza_en_vez_de_acumular(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token = await _registrar(cliente_http, "agenda-reemplazo@test.local")

        for horas in (24, 12):
            respuesta = await cliente_http.put(
                "/reglas/agenda", headers=_auth(token), json=_agenda(horas)
            )
            assert respuesta.status_code == 200, respuesta.text

        reglas = _reglas_de_agenda(await cliente_http.get("/reglas", headers=_auth(token)))
        assert [uno["configuracion"] for uno in reglas] == [
            {"recordatorios": [{"horas_antes": 12}]}
        ]

    async def test_el_dominio_rechaza_con_su_frase(self, cliente_http: httpx.AsyncClient) -> None:
        token = await _registrar(cliente_http, "agenda-422@test.local")

        fuera_de_rango = await cliente_http.put(
            "/reglas/agenda", headers=_auth(token), json=_agenda(169)
        )
        repetidos = await cliente_http.put(
            "/reglas/agenda", headers=_auth(token), json=_agenda(24, 24)
        )

        assert fuera_de_rango.status_code == 422
        assert MENSAJE_RANGO in fuera_de_rango.text
        assert repetidos.status_code == 422
        assert MENSAJE_REPETIDOS in repetidos.text

    async def test_la_prioridad_guardada_se_persiste_y_se_devuelve(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token = await _registrar(cliente_http, "agenda-prioridad@test.local")

        guardada = await cliente_http.put(
            "/reglas/agenda", headers=_auth(token), json=_agenda(24, prioridad=7)
        )

        assert guardada.status_code == 200, guardada.text
        assert guardada.json()["prioridad"] == 7
        [regla] = _reglas_de_agenda(await cliente_http.get("/reglas", headers=_auth(token)))
        assert regla["prioridad"] == 7

    async def test_guardar_una_regla_desactivada_la_reactiva(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token = await _registrar(cliente_http, "agenda-reactivar@test.local")
        alta = await cliente_http.put("/reglas/agenda", headers=_auth(token), json=_agenda(24))
        apagada = await cliente_http.put(
            f"/reglas/{alta.json()['id']}/estado",
            headers=_auth(token),
            json={"activa": False},
        )
        assert apagada.status_code == 200, apagada.text
        [regla] = _reglas_de_agenda(await cliente_http.get("/reglas", headers=_auth(token)))
        assert regla["activa"] is False

        guardada = await cliente_http.put("/reglas/agenda", headers=_auth(token), json=_agenda(12))

        assert guardada.status_code == 200, guardada.text
        [regla] = _reglas_de_agenda(await cliente_http.get("/reglas", headers=_auth(token)))
        assert regla["activa"] is True
        assert regla["configuracion"] == {"recordatorios": [{"horas_antes": 12}]}

    async def test_una_prioridad_negativa_al_actualizar_es_422_y_no_toca_la_regla(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token = await _registrar(cliente_http, "agenda-prioridad-negativa@test.local")
        await cliente_http.put(
            "/reglas/agenda", headers=_auth(token), json=_agenda(24, prioridad=3)
        )

        rechazo = await cliente_http.put(
            "/reglas/agenda", headers=_auth(token), json=_agenda(12, prioridad=-1)
        )

        assert rechazo.status_code == 422
        assert MENSAJE_PRIORIDAD in rechazo.text
        [regla] = _reglas_de_agenda(await cliente_http.get("/reglas", headers=_auth(token)))
        assert regla["prioridad"] == 3
        assert regla["configuracion"] == {"recordatorios": [{"horas_antes": 24}]}

    async def test_un_operador_no_puede_configurarla_pero_si_leer_las_reglas(
        self, cliente_http: httpx.AsyncClient, despachador: DespachadorEspia
    ) -> None:
        token_admin = await _registrar(cliente_http, "ana@empresa.com")
        token_operador = await _operador(cliente_http, despachador, token_admin)

        rechazo = await cliente_http.put(
            "/reglas/agenda", headers=_auth(token_operador), json=_agenda(24)
        )

        assert rechazo.status_code == 403  # `OperacionNoPermitida(MOTIVO_SOLO_ADMIN)`
        listado = await cliente_http.get("/reglas", headers=_auth(token_operador))
        assert listado.status_code == 200
        assert _reglas_de_agenda(listado) == []

    async def test_la_agenda_de_una_empresa_no_se_ve_en_la_otra(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token_a = await _registrar(cliente_http, "agenda-a@test.local")
        token_b = await _registrar(cliente_http, "agenda-b@test.local")
        assert _decodificar(token_a)["empresa_id"] != _decodificar(token_b)["empresa_id"]
        await cliente_http.put("/reglas/agenda", headers=_auth(token_a), json=_agenda(72))

        listado_b = await cliente_http.get("/reglas", headers=_auth(token_b))

        assert _reglas_de_agenda(listado_b) == []
