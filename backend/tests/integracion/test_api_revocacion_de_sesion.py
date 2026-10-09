"""Immediate session revocation, end to end against a real PostgreSQL (cases 17 to 24).

The whole stack in one process: ASGI app, `EmpresaMiddleware` with the **real** per-request
check, the routers, the use cases, the repositories and Row-Level Security. The access token
is never refreshed or re-issued between the administrative change and the request that must
feel it: that is what HU-E1-05 and HU-E1-06 ask for, and what the token's 15-minute lifetime
used to make false.

Case 25 needs no new test: `test_api_sesiones.py` and `test_refresh_concurrente.py` already
cover reuse detection and the concurrent-refresh race, and they run unchanged through the
per-request check, which is the guard the plan asks for.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.identity.infrastructure.seguridad import (
    EmisorDeTokensJWT,
    hashear_token_opaco,
)
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.workers import tasks_identity
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
_SIN_SESION = {"error": "NoAutenticado", "detalle": "Se requiere iniciar sesion."}


class DespachadorEspia:
    """Stands in for Celery. Keeps the invitation token the endpoint would have sent."""

    def __init__(self) -> None:
        self.tareas: list[dict[str, Any]] = []

    def send_task(self, nombre: str, **kwargs: Any) -> None:
        self.tareas.append({"nombre": nombre, **kwargs})


@dataclass(frozen=True)
class Miembro:
    """One signed-in user: the session the API returned, and the ids that matter."""

    usuario_id: str
    empresa_id: str
    access_token: str
    refresh_token: str

    @property
    def cabeceras(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


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
async def cliente(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        yield cliente
    await recursos.cerrar()


def _miembro(cuerpo: dict[str, Any]) -> Miembro:
    return Miembro(
        usuario_id=str(cuerpo["usuario_id"]),
        empresa_id=str(cuerpo["empresa_id"]),
        access_token=str(cuerpo["access_token"]),
        refresh_token=str(cuerpo["refresh_token"]),
    )


async def _registrar(cliente: httpx.AsyncClient, email: str) -> Miembro:
    respuesta = await cliente.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return _miembro(respuesta.json())


async def _ingresar(cliente: httpx.AsyncClient, email: str) -> Miembro:
    respuesta = await cliente.post("/auth/login", json={"email": email, "contrasena": CONTRASENA})
    assert respuesta.status_code == 200, respuesta.text
    return _miembro(respuesta.json())


async def _incorporar(
    cliente: httpx.AsyncClient,
    despachador: DespachadorEspia,
    admin: Miembro,
    email: str,
    rol: str,
) -> Miembro:
    """Invite somebody into the administrator's company, accept, and sign them in."""
    invitacion = await cliente.post(
        "/usuarios/invitaciones", headers=admin.cabeceras, json={"email": email, "rol": rol}
    )
    assert invitacion.status_code == 201, invitacion.text
    aceptacion = await cliente.post(
        "/auth/invitaciones/aceptar",
        json={
            "token": despachador.tareas[-1]["kwargs"]["token"],
            "nombre": "Beto Gomez",
            "contrasena": CONTRASENA,
        },
    )
    assert aceptacion.status_code == 201, aceptacion.text
    return await _ingresar(cliente, email)


async def _invitar(cliente: httpx.AsyncClient, quien: Miembro, email: str) -> httpx.Response:
    """An action only an Administrator may take."""
    return await cliente.post(
        "/usuarios/invitaciones",
        headers=quien.cabeceras,
        json={"email": email, "rol": "OPERADOR"},
    )


async def _desactivar(cliente: httpx.AsyncClient, admin: Miembro, objetivo: Miembro) -> None:
    respuesta = await cliente.post(
        f"/usuarios/{objetivo.usuario_id}/desactivacion", headers=admin.cabeceras
    )
    assert respuesta.status_code == 200, respuesta.text


async def _cambiar_rol(
    cliente: httpx.AsyncClient, admin: Miembro, objetivo: Miembro, rol: str
) -> None:
    respuesta = await cliente.patch(
        f"/usuarios/{objetivo.usuario_id}/rol", headers=admin.cabeceras, json={"rol": rol}
    )
    assert respuesta.status_code == 200, respuesta.text


# ------------------------------------------------ caso 17: desactivar corta la siguiente solicitud


@pytest.mark.asyncio
async def test_la_siguiente_solicitud_de_un_usuario_desactivado_es_401(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia
):
    """HU-E1-06: the access token is the one issued before the deactivation and it is still
    inside its 15 minutes. It stops working all the same."""
    admin = await _registrar(cliente, "ana@empresa.com")
    operador = await _incorporar(cliente, despachador, admin, "beto@empresa.com", "OPERADOR")
    assert (await cliente.get("/usuarios", headers=operador.cabeceras)).status_code == 200

    await _desactivar(cliente, admin, operador)

    respuesta = await cliente.get("/usuarios", headers=operador.cabeceras)
    assert respuesta.status_code == 401
    assert respuesta.json() == _SIN_SESION
    # And the administrator, whose token is just as old, is unaffected.
    assert (await cliente.get("/usuarios", headers=admin.cabeceras)).status_code == 200


# ------------------------------- caso 18: ni el refresh ni ninguna familia sobreviven


@pytest.mark.asyncio
async def test_tras_desactivar_el_refresh_es_rechazado_y_todas_las_familias_quedan_revocadas(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia, engine_dueno: AsyncEngine
):
    admin = await _registrar(cliente, "ana@empresa.com")
    operador = await _incorporar(cliente, despachador, admin, "beto@empresa.com", "OPERADOR")
    otro_dispositivo = await _ingresar(cliente, "beto@empresa.com")

    await _desactivar(cliente, admin, operador)

    for sesion in (operador, otro_dispositivo):
        refrescar = await cliente.post(
            "/auth/refresh", json={"refresh_token": sesion.refresh_token}
        )
        # Not asserting the number: `SesionInvalida` maps to 409 today (hallazgo 4), and
        # changing it is another unit's decision. It is a 4xx with that error, never a 200.
        assert 400 <= refrescar.status_code < 500, refrescar.text
        assert refrescar.json()["error"] == "SesionInvalida"

    async with engine_dueno.connect() as conexion:
        total = (
            await conexion.execute(
                text("SELECT count(*) FROM refresh_token WHERE usuario_id = :u"),
                {"u": uuid.UUID(operador.usuario_id)},
            )
        ).scalar_one()
        vivos = (
            await conexion.execute(
                text("SELECT count(*) FROM refresh_token WHERE usuario_id = :u AND NOT revocado"),
                {"u": uuid.UUID(operador.usuario_id)},
            )
        ).scalar_one()
    assert total >= 2, "the test needs two sign-ins to mean anything"
    assert vivos == 0


# ---------------------------------------- casos 19 y 20: el rol vale en la siguiente solicitud


@pytest.mark.asyncio
async def test_un_administrador_degradado_pierde_las_acciones_de_administrador_con_el_mismo_token(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia
):
    """Case 19 (HU-E1-05): the token still says ADMINISTRADOR; the database says OPERADOR."""
    admin = await _registrar(cliente, "ana@empresa.com")
    otro = await _incorporar(cliente, despachador, admin, "beto@empresa.com", "ADMINISTRADOR")
    assert (await _invitar(cliente, otro, "carla@empresa.com")).status_code == 201

    await _cambiar_rol(cliente, admin, otro, "OPERADOR")

    respuesta = await _invitar(cliente, otro, "diego@empresa.com")
    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "PermisoDenegado"
    # Still a member: reading is open to every role.
    assert (await cliente.get("/usuarios", headers=otro.cabeceras)).status_code == 200


@pytest.mark.asyncio
async def test_un_operador_promovido_puede_actuar_como_administrador_con_el_mismo_token(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia
):
    """Case 20: the other direction. No need to sign in again to feel the promotion."""
    admin = await _registrar(cliente, "ana@empresa.com")
    operador = await _incorporar(cliente, despachador, admin, "beto@empresa.com", "OPERADOR")
    assert (await _invitar(cliente, operador, "carla@empresa.com")).status_code == 403

    await _cambiar_rol(cliente, admin, operador, "ADMINISTRADOR")

    assert (await _invitar(cliente, operador, "carla@empresa.com")).status_code == 201


# ---------------------------------------------- caso 21: la reactivación es un comportamiento fijado


@pytest.mark.asyncio
async def test_reactivar_dentro_de_los_15_minutos_devuelve_el_acceso_con_el_rol_previo(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia
):
    """Accepted behaviour (question 4 of the plan): HU-E1-06 RN-04 says a reactivated user
    recovers access with the role they had, and the token's lifetime bounds the window. This
    test makes it deliberate instead of accidental."""
    admin = await _registrar(cliente, "ana@empresa.com")
    operador = await _incorporar(cliente, despachador, admin, "beto@empresa.com", "OPERADOR")
    await _desactivar(cliente, admin, operador)
    assert (await cliente.get("/usuarios", headers=operador.cabeceras)).status_code == 401

    reactivacion = await cliente.post(
        f"/usuarios/{operador.usuario_id}/reactivacion", headers=admin.cabeceras
    )
    assert reactivacion.status_code == 200, reactivacion.text

    assert (await cliente.get("/usuarios", headers=operador.cabeceras)).status_code == 200
    # With the role they had, not a broader one.
    assert (await _invitar(cliente, operador, "carla@empresa.com")).status_code == 403


# ------------------------------------- caso 22: la empresa del token tiene que ser la del usuario


@pytest.mark.asyncio
async def test_un_token_con_el_usuario_de_una_empresa_y_la_empresa_de_otra_es_401(
    cliente: httpx.AsyncClient,
):
    """Defence in depth: the signature vouches for the claims, and the claims are still
    checked against the row. Scoped to company B, the user of A does not exist."""
    ana = await _registrar(cliente, "ana@empresa-a.com")
    beto = await _registrar(cliente, "beto@empresa-b.com")
    settings = _settings()
    falsificado = EmisorDeTokensJWT(
        secreto=settings.jwt_secret, vida_acceso=timedelta(minutes=15)
    ).emitir_acceso(
        usuario_id=UsuarioId(uuid.UUID(ana.usuario_id)),
        empresa_id=EmpresaId(uuid.UUID(beto.empresa_id)),
        rol="ADMINISTRADOR",
        ahora=datetime.now(UTC),
    )

    respuesta = await cliente.get(
        "/usuarios", headers={"Authorization": f"Bearer {falsificado.valor}"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == _SIN_SESION
    assert "beto@empresa-b.com" not in respuesta.text


# ------------------------------------ caso 23: un refresh creado después de desactivar no sirve


@pytest.mark.asyncio
async def test_un_refresh_vivo_creado_despues_de_la_desactivacion_es_rechazado_al_usarse(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia, engine_dueno: AsyncEngine
):
    """The race: a refresh in flight when the Administrator deactivates the user can still
    insert a live token after the revocation swept the old ones. It must not be usable.
    The row is inserted as the owner, which is what 'created after' amounts to."""
    admin = await _registrar(cliente, "ana@empresa.com")
    operador = await _incorporar(cliente, despachador, admin, "beto@empresa.com", "OPERADOR")
    await _desactivar(cliente, admin, operador)
    tardio = "refresh-creado-despues-de-la-desactivacion-fake"
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            text(
                "INSERT INTO refresh_token "
                "(id, familia_id, empresa_id, usuario_id, hash_del_token, expira_en, revocado) "
                "VALUES (:id, :familia, :empresa, :usuario, :hash, :vence, false)"
            ),
            {
                "id": uuid.uuid4(),
                "familia": uuid.uuid4(),
                "empresa": uuid.UUID(operador.empresa_id),
                "usuario": uuid.UUID(operador.usuario_id),
                "hash": hashear_token_opaco(tardio),
                "vence": datetime.now(UTC) + timedelta(days=30),
            },
        )

    refrescar = await cliente.post("/auth/refresh", json={"refresh_token": tardio})

    assert 400 <= refrescar.status_code < 500, refrescar.text
    assert refrescar.json()["error"] == "SesionInvalida"


# ------------------------------------------ caso 24: regresión, no se puede volver a ingresar


@pytest.mark.asyncio
async def test_un_usuario_desactivado_no_puede_iniciar_sesion_con_su_contrasena(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia
):
    admin = await _registrar(cliente, "ana@empresa.com")
    operador = await _incorporar(cliente, despachador, admin, "beto@empresa.com", "OPERADOR")
    await _desactivar(cliente, admin, operador)

    ingreso = await cliente.post(
        "/auth/login", json={"email": "beto@empresa.com", "contrasena": CONTRASENA}
    )

    assert 400 <= ingreso.status_code < 500, ingreso.text
    assert ingreso.json()["error"] == "CredencialesInvalidas"
