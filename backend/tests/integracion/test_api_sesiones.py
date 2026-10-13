"""Refresh-token reuse detection (ADR-011) against a real PostgreSQL.

`RefrescarSesion` revokes the whole family when it sees a token that was already rotated,
and then raises. The revocation only counts if it is **committed** before the error goes
out. The unit test with fakes could never see that: fakes have no transaction. So these
tests drive the real app and then look at the table as its owner — the role Row-Level
Security does not constrain — without going through the code under test.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import UUID

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
_ERROR_DE_REUSO = "ReusoDeRefreshDetectado"


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


async def _registrar(cliente: httpx.AsyncClient, email: str) -> dict[str, str]:
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
    cuerpo: dict[str, str] = respuesta.json()
    return cuerpo


async def _refrescar(cliente: httpx.AsyncClient, token: str) -> httpx.Response:
    return await cliente.post("/auth/refresh", json={"refresh_token": token})


async def _vivos(engine: AsyncEngine, empresa_id: str) -> int:
    """Refresh tokens of the company that are still not revoked, read as the owner."""
    async with engine.connect() as conexion:
        resultado = await conexion.execute(
            text("SELECT count(*) FROM refresh_token WHERE empresa_id = :e AND NOT revocado"),
            {"e": UUID(empresa_id)},
        )
        return int(resultado.scalar_one())


async def _reusar(cliente: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str, str]:
    """Sign up, rotate once, and return (session, R0, R1): R0 is now a used token."""
    sesion = await _registrar(cliente, email)
    r0 = sesion["refresh_token"]
    rotada = await _refrescar(cliente, r0)
    assert rotada.status_code == 200, rotada.text
    return sesion, r0, str(rotada.json()["refresh_token"])


@pytest.mark.asyncio
async def test_reusar_un_refresh_deja_al_hijo_sin_poder_refrescar(cliente: httpx.AsyncClient):
    _, r0, r1 = await _reusar(cliente, "ana@empresa.com")

    reuso = await _refrescar(cliente, r0)
    hijo = await _refrescar(cliente, r1)

    assert reuso.status_code == 409
    assert reuso.json()["error"] == _ERROR_DE_REUSO
    assert hijo.status_code != 200, "the child token survived the reuse: the revocation was lost"


@pytest.mark.asyncio
async def test_reusar_un_refresh_revoca_toda_la_familia_en_la_base(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    sesion, r0, _ = await _reusar(cliente, "ana@empresa.com")
    # R0 is used, not revoked: rotation marks it `usado_en`, so R0 and R1 both count here.
    assert await _vivos(engine_dueno, sesion["empresa_id"]) == 2

    await _refrescar(cliente, r0)

    assert await _vivos(engine_dueno, sesion["empresa_id"]) == 0


@pytest.mark.asyncio
async def test_otra_sesion_del_mismo_usuario_sigue_viva(cliente: httpx.AsyncClient):
    """Revoking the family must not become «revoke every session of the user»."""
    _, r0, _ = await _reusar(cliente, "ana@empresa.com")
    login = await cliente.post(
        "/auth/login", json={"email": "ana@empresa.com", "contrasena": CONTRASENA}
    )
    assert login.status_code == 200, login.text

    await _refrescar(cliente, r0)

    otra = await _refrescar(cliente, str(login.json()["refresh_token"]))
    assert otra.status_code == 200, otra.text


@pytest.mark.asyncio
async def test_reusar_un_token_de_una_empresa_no_toca_a_la_otra(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    _, r0, _ = await _reusar(cliente, "ana@empresa-a.com")
    otra = await _registrar(cliente, "beto@empresa-b.com")

    await _refrescar(cliente, r0)

    assert await _vivos(engine_dueno, otra["empresa_id"]) == 1
    assert (await _refrescar(cliente, otra["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_reusar_dos_veces_es_idempotente_y_no_da_500(cliente: httpx.AsyncClient):
    _, r0, _ = await _reusar(cliente, "ana@empresa.com")

    primera = await _refrescar(cliente, r0)
    segunda = await _refrescar(cliente, r0)

    assert primera.status_code == 409
    assert segunda.status_code == 409
    assert segunda.json()["error"] == _ERROR_DE_REUSO


@pytest.mark.asyncio
async def test_un_refresh_desconocido_sigue_dando_su_error_de_siempre(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    """Not caught too broadly: an unknown token is not reuse and revokes nothing."""
    sesion = await _registrar(cliente, "ana@empresa.com")

    respuesta = await _refrescar(cliente, "no-existe")

    assert respuesta.json()["error"] == "SesionInvalida"
    assert await _vivos(engine_dueno, sesion["empresa_id"]) == 1
