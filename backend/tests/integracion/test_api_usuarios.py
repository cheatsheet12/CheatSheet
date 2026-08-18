"""The user administration endpoints, end to end.

The whole stack in one process: ASGI app, `EmpresaMiddleware` verifying a real JWT, the
routers, the use cases, the PostgreSQL repositories and Row-Level Security. No socket is
opened except to the local database — `httpx.ASGITransport` calls the application
directly, and the Celery dispatcher is replaced by a spy.

**Why this file exists even though every layer already has its own test.** The listed
risk is that an Operador who tries to administer users gets an empty screen instead of a
403 — a failure that lives precisely in the seam between the layers, where no unit test
looks. And the sign-up → invite → accept → sign-in path is the epic's actual deliverable;
until it runs whole, nobody has seen it work.
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
from cheatsheet.workers import tasks_identity

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"


class DespachadorEspia:
    """Stands in for Celery. Keeps the invitation token the endpoint would have sent."""

    def __init__(self) -> None:
        self.tareas: list[dict[str, Any]] = []

    def send_task(self, nombre: str, **kwargs: Any) -> None:
        self.tareas.append({"nombre": nombre, **kwargs})


def _settings() -> Settings:
    """The shared inert settings, with the real database URLs put back."""
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest.fixture
def despachador(monkeypatch) -> DespachadorEspia:
    espia = DespachadorEspia()
    monkeypatch.setattr(tasks_identity, "_despachador", lambda _settings: espia)
    return espia


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
        json={"email": email, "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_sin_token_no_se_listan_usuarios(cliente: httpx.AsyncClient):
    """The middleware refuses before any use case runs."""
    respuesta = await cliente.get("/usuarios")

    assert respuesta.status_code == 401


@pytest.mark.asyncio
async def test_el_administrador_ve_su_propia_empresa_y_solo_esa(cliente: httpx.AsyncClient):
    token_a = await _registrar(cliente, "ana@empresa-a.com")
    await _registrar(cliente, "beto@empresa-b.com")

    respuesta = await cliente.get("/usuarios", headers=_auth(token_a))

    assert respuesta.status_code == 200
    emails = [fila["email"] for fila in respuesta.json()]
    assert emails == ["ana@empresa-a.com"]


@pytest.mark.asyncio
async def test_el_ciclo_completo_invitar_aceptar_e_ingresar(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia
):
    """The epic's deliverable, in one test: an administrator invites somebody and that
    person ends up signed in with a password they chose."""
    token = await _registrar(cliente, "ana@empresa.com")

    invitacion = await cliente.post(
        "/usuarios/invitaciones",
        headers=_auth(token),
        json={"email": "beto@empresa.com", "rol": "OPERADOR"},
    )
    assert invitacion.status_code == 201, invitacion.text
    assert invitacion.json()["estado"] == "INVITADO"

    # The clear-text token exists only in the queued task — the database holds its hash.
    assert despachador.tareas[0]["nombre"] == tasks_identity.NOMBRE
    token_invitacion = despachador.tareas[0]["kwargs"]["token"]

    aceptacion = await cliente.post(
        "/auth/invitaciones/aceptar",
        json={
            "token": token_invitacion,
            "nombre": "Beto Gomez",
            "contrasena": CONTRASENA,
        },
    )
    assert aceptacion.status_code == 201, aceptacion.text

    ingreso = await cliente.post(
        "/auth/login", json={"email": "beto@empresa.com", "contrasena": CONTRASENA}
    )
    assert ingreso.status_code == 200, ingreso.text

    listado = await cliente.get("/usuarios", headers=_auth(token))
    estados = {fila["email"]: fila["estado"] for fila in listado.json()}
    assert estados == {"ana@empresa.com": "ACTIVO", "beto@empresa.com": "ACTIVO"}


@pytest.mark.asyncio
async def test_un_operador_recibe_403_al_administrar_usuarios(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia
):
    """The listed risk: 403, not an empty screen. The frontend hides the button; this is
    what actually refuses."""
    token_admin = await _registrar(cliente, "ana@empresa.com")
    await cliente.post(
        "/usuarios/invitaciones",
        headers=_auth(token_admin),
        json={"email": "beto@empresa.com", "rol": "OPERADOR"},
    )
    await cliente.post(
        "/auth/invitaciones/aceptar",
        json={
            "token": despachador.tareas[0]["kwargs"]["token"],
            "nombre": "Beto Gomez",
            "contrasena": CONTRASENA,
        },
    )
    ingreso = await cliente.post(
        "/auth/login", json={"email": "beto@empresa.com", "contrasena": CONTRASENA}
    )
    token_operador = ingreso.json()["access_token"]

    invitar = await cliente.post(
        "/usuarios/invitaciones",
        headers=_auth(token_operador),
        json={"email": "carla@empresa.com", "rol": "OPERADOR"},
    )

    assert invitar.status_code == 403
    assert invitar.json()["error"] == "PermisoDenegado"
    # And the read *is* allowed: HU-E1-05's third criterion has the Operador looking at
    # the list and finding the action unavailable.
    assert (await cliente.get("/usuarios", headers=_auth(token_operador))).status_code == 200


@pytest.mark.asyncio
async def test_desactivar_al_unico_administrador_devuelve_409(cliente: httpx.AsyncClient):
    """A broken business rule is a 409: the request was understood and the system is fine."""
    token = await _registrar(cliente, "ana@empresa.com")
    yo = (await cliente.get("/usuarios", headers=_auth(token))).json()[0]

    respuesta = await cliente.post(f"/usuarios/{yo['id']}/desactivacion", headers=_auth(token))

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "UltimoAdministradorActivo"


@pytest.mark.asyncio
async def test_cualquier_usuario_edita_sus_propias_preferencias(cliente: httpx.AsyncClient):
    """HU-E1-07 — and `/usuarios/yo/...` must not be parsed as a user id."""
    token = await _registrar(cliente, "ana@empresa.com")

    actuales = await cliente.get("/usuarios/yo/preferencias", headers=_auth(token))
    assert actuales.status_code == 200
    assert actuales.json()["pref_suscripciones"]["FACTURACION"] == ["EMAIL", "PANEL"]

    guardadas = await cliente.put(
        "/usuarios/yo/preferencias",
        headers=_auth(token),
        json={
            "pref_zona_horaria": "America/Argentina/Cordoba",
            "pref_suscripciones": {"FACTURACION": ["EMAIL"]},
        },
    )

    assert guardadas.status_code == 200
    assert guardadas.json()["pref_zona_horaria"] == "America/Argentina/Cordoba"
    assert guardadas.json()["pref_suscripciones"]["COBROS"] == []


@pytest.mark.asyncio
async def test_una_preferencia_que_el_catalogo_no_nombra_devuelve_422(
    cliente: httpx.AsyncClient,
):
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await cliente.put(
        "/usuarios/yo/preferencias",
        headers=_auth(token),
        json={"pref_suscripciones": {"NO_EXISTE": ["EMAIL"]}},
    )

    assert respuesta.status_code == 422


@pytest.mark.asyncio
async def test_el_alta_con_google_crea_la_cuenta_y_despues_la_reconoce(
    cliente: httpx.AsyncClient,
):
    """HU-E1-01 RN-02, through the simulated provider.

    Sign-up and sign-in are the same endpoint: whoever comes back from Google does not
    know whether they already have an account, and the second call must not create a
    second company for the same person.
    """
    url = await cliente.get("/auth/google/url", params={"state": "un-state"})
    assert url.status_code == 200
    assert "state=un-state" in url.json()["url"]

    primera = await cliente.post(
        "/auth/google/callback", json={"codigo": "simulado:ana@empresa.com"}
    )
    assert primera.status_code == 201, primera.text
    assert primera.json()["onboarding_completo"] is False

    segunda = await cliente.post(
        "/auth/google/callback", json={"codigo": "simulado:ana@empresa.com"}
    )
    assert segunda.status_code == 201
    assert segunda.json()["empresa_id"] == primera.json()["empresa_id"]
    assert segunda.json()["usuario_id"] == primera.json()["usuario_id"]


@pytest.mark.asyncio
async def test_un_codigo_de_google_invalido_no_crea_nada(cliente: httpx.AsyncClient):
    respuesta = await cliente.post("/auth/google/callback", json={"codigo": "4/0AY0e-g7"})

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "OAuthFallido"
