"""Concurrent refresh and logout (ADR-011) against a real PostgreSQL.

Rotation assumes every refresh token is used once, but that only holds when requests arrive
one at a time. These tests make two of them overlap **deterministically**, never with a
`sleep`:

* **A** is a rotation opened by hand (`sesion_de_empresa` + the Postgres repositories +
  `RefrescarSesion`) that stays inside its transaction until the test lets it commit.
* **B** is a real HTTP request, launched as a task while A is still open.
* The test polls `pg_locks` as the owner until some backend is waiting for a lock. Whatever
  B waits on (a row lock today, a per-family advisory lock once serialized), the poll sees
  it, so the scenario is the same before and after the fix. Then A commits and B finishes.

The database is inspected as the owner, with no code under test in between.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos, UnidadDeTrabajo, construir_publicador
from cheatsheet.api.main import create_app
from cheatsheet.contexts.identity.application.sesiones import RefrescarSesion, Sesion
from cheatsheet.contexts.identity.infrastructure.ensamblado import Identidad
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId, empresa_id_desde
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
_ERROR_DE_REUSO = "ReusoDeRefreshDetectado"
_ESPERA_DE_BLOQUEO_S = 5.0
_ESPERA_DE_RESPUESTA_S = 10.0

LlamadaDeB = Callable[[], Coroutine[Any, Any, httpx.Response]]


@dataclass(frozen=True, slots=True)
class Entorno:
    cliente: httpx.AsyncClient
    recursos: Recursos


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest_asyncio.fixture
async def entorno(esquema_migrado: None) -> AsyncIterator[Entorno]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        yield Entorno(cliente=cliente, recursos=recursos)
    await recursos.cerrar()


async def _registrar(cliente: httpx.AsyncClient, email: str) -> dict[str, str]:
    respuesta = await cliente.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo: dict[str, str] = respuesta.json()
    return cuerpo


async def _refrescar(cliente: httpx.AsyncClient, token: str) -> httpx.Response:
    return await cliente.post("/auth/refresh", json={"refresh_token": token})


async def _cerrar_sesion(cliente: httpx.AsyncClient, token: str) -> httpx.Response:
    return await cliente.post("/auth/logout", json={"refresh_token": token})


async def _vivos(engine: AsyncEngine, empresa_id: str) -> int:
    """Refresh tokens of the company that are still not revoked, read as the owner."""
    async with engine.connect() as conexion:
        resultado = await conexion.execute(
            text("SELECT count(*) FROM refresh_token WHERE empresa_id = :e AND NOT revocado"),
            {"e": UUID(empresa_id)},
        )
        return int(resultado.scalar_one())


async def _contar_locks(engine: AsyncEngine, condicion: str) -> int:
    """Count `pg_locks` rows. `condicion` is one of the literals below, never user input."""
    consultas = {
        "esperando": "SELECT count(*) FROM pg_locks WHERE NOT granted",
        "advisory": "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'",
    }
    async with engine.connect() as conexion:
        return int((await conexion.execute(text(consultas[condicion]))).scalar_one())


async def _una_rotacion(cliente: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str, str]:
    """Sign up, rotate once, and return (session, R0, R1): R0 is a used token now."""
    sesion = await _registrar(cliente, email)
    r0 = sesion["refresh_token"]
    rotada = await _refrescar(cliente, r0)
    assert rotada.status_code == 200, rotada.text
    return sesion, r0, str(rotada.json()["refresh_token"])


@asynccontextmanager
async def _rotacion_abierta(
    recursos: Recursos, empresa_id: str, token: str
) -> AsyncIterator[Sesion]:
    """Rotate `token` and stay inside the transaction: nothing is committed until the exit."""
    empresa = EmpresaId(empresa_id_desde(empresa_id))
    async with sesion_de_empresa(recursos.sesiones, empresa) as sesion:
        unidad = UnidadDeTrabajo(
            sesion=sesion,
            publicador=construir_publicador(sesion, empresa),
            reloj=recursos.reloj,
        )
        piezas = Identidad.armar(unidad, recursos.settings)
        yield await RefrescarSesion(
            usuarios=piezas.usuarios,
            refrescos=piezas.refrescos,
            tokens=piezas.tokens,
            emisor=piezas.emisor,
        ).ejecutar(refresh_token=token, ahora=unidad.reloj.ahora())


async def _esperar_un_bloqueo(engine: AsyncEngine, b: asyncio.Task[httpx.Response]) -> None:
    """Poll until some backend waits for a lock; fail loudly instead of hanging."""
    limite = asyncio.get_running_loop().time() + _ESPERA_DE_BLOQUEO_S
    while asyncio.get_running_loop().time() < limite:
        assert not b.done(), (
            "request B finished without ever waiting for a lock: the scenario did not overlap "
            "with transaction A, so the test would prove nothing"
        )
        if await _contar_locks(engine, "esperando") >= 1:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"no backend waited for a lock within {_ESPERA_DE_BLOQUEO_S} s")


async def _rotar_con_b_en_espera(
    entorno: Entorno, engine: AsyncEngine, empresa_id: str, token_de_a: str, b: LlamadaDeB
) -> tuple[Sesion, httpx.Response]:
    """A rotates `token_de_a` and stays open, B starts, B blocks, A commits, B finishes."""
    tarea: asyncio.Task[httpx.Response] | None = None
    try:
        async with _rotacion_abierta(entorno.recursos, empresa_id, token_de_a) as hijo_de_a:
            tarea = asyncio.create_task(b())
            await _esperar_un_bloqueo(engine, tarea)
        return hijo_de_a, await asyncio.wait_for(tarea, _ESPERA_DE_RESPUESTA_S)
    finally:
        # A always ends (the context manager above); B never outlives the test.
        if tarea is not None and not tarea.done():
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)


@pytest.mark.asyncio
async def test_dos_refresh_del_mismo_token_dejan_la_familia_revocada(
    entorno: Entorno, engine_dueno: AsyncEngine
):
    """Form 1: A and B rotate R0 at once. B must see R0 used, and the child must die."""
    sesion = await _registrar(entorno.cliente, "ana@empresa.com")
    r0 = sesion["refresh_token"]

    hijo_de_a, b = await _rotar_con_b_en_espera(
        entorno,
        engine_dueno,
        sesion["empresa_id"],
        r0,
        lambda: _refrescar(entorno.cliente, r0),
    )

    assert b.status_code == 409, f"B rotated the same token as A: {b.status_code} {b.text}"
    assert b.json()["error"] == _ERROR_DE_REUSO
    assert await _vivos(engine_dueno, sesion["empresa_id"]) == 0, "a second child stayed alive"
    hijo = await _refrescar(entorno.cliente, hijo_de_a.refresh_token)
    assert hijo.status_code != 200, "the child that A issued survived the reuse"


@pytest.mark.asyncio
async def test_reusar_r0_mientras_se_rota_r1_revoca_tambien_a_r2(
    entorno: Entorno, engine_dueno: AsyncEngine
):
    """Form 2: reuse detected while the child is being rotated must reach R2 as well."""
    sesion, r0, r1 = await _una_rotacion(entorno.cliente, "ana@empresa.com")

    hijo_de_a, b = await _rotar_con_b_en_espera(
        entorno,
        engine_dueno,
        sesion["empresa_id"],
        r1,
        lambda: _refrescar(entorno.cliente, r0),
    )

    assert b.status_code == 409, b.text
    assert b.json()["error"] == _ERROR_DE_REUSO
    assert await _vivos(engine_dueno, sesion["empresa_id"]) == 0, "R2 was not revoked"
    nieto = await _refrescar(entorno.cliente, hijo_de_a.refresh_token)
    assert nieto.status_code != 200, "R2 still refreshes after the family was revoked"


@pytest.mark.asyncio
async def test_logout_mientras_se_rota_deja_sin_sesion_al_hijo_nuevo(
    entorno: Entorno, engine_dueno: AsyncEngine
):
    """Form 3: «I signed out» must be true even for the child issued during the sign-out."""
    sesion, _, r1 = await _una_rotacion(entorno.cliente, "ana@empresa.com")

    hijo_de_a, b = await _rotar_con_b_en_espera(
        entorno,
        engine_dueno,
        sesion["empresa_id"],
        r1,
        lambda: _cerrar_sesion(entorno.cliente, r1),
    )

    assert b.status_code == 204, b.text
    assert await _vivos(engine_dueno, sesion["empresa_id"]) == 0, "R2 survived the logout"
    hijo = await _refrescar(entorno.cliente, hijo_de_a.refresh_token)
    assert hijo.status_code != 200, "R2 still refreshes after the logout"


@pytest.mark.asyncio
async def test_una_rafaga_de_refresh_no_deja_dos_hijos_vivos_ni_da_5xx(
    entorno: Entorno, engine_dueno: AsyncEngine
):
    sesion = await _registrar(entorno.cliente, "ana@empresa.com")

    respuestas = await asyncio.wait_for(
        asyncio.gather(*(_refrescar(entorno.cliente, sesion["refresh_token"]) for _ in range(5))),
        _ESPERA_DE_RESPUESTA_S,
    )

    estados = [r.status_code for r in respuestas]
    assert all(estado < 500 for estado in estados), f"a request failed (deadlock?): {estados}"
    assert estados.count(200) <= 1, f"more than one rotation of the same token won: {estados}"
    if 409 in estados:
        assert await _vivos(engine_dueno, sesion["empresa_id"]) == 0


@pytest.mark.asyncio
async def test_otra_familia_y_otra_empresa_no_esperan_a_la_que_esta_rotando(
    entorno: Entorno,
):
    """The lock is per family: a rotation held open blocks neither a sibling family nor
    another company."""
    primera = await _registrar(entorno.cliente, "ana@empresa-a.com")
    login = await entorno.cliente.post(
        "/auth/login", json={"email": "ana@empresa-a.com", "contrasena": CONTRASENA}
    )
    assert login.status_code == 200, login.text
    otra_empresa = await _registrar(entorno.cliente, "beto@empresa-b.com")

    async with _rotacion_abierta(entorno.recursos, primera["empresa_id"], primera["refresh_token"]):
        hermana, ajena = await asyncio.wait_for(
            asyncio.gather(
                _refrescar(entorno.cliente, str(login.json()["refresh_token"])),
                _refrescar(entorno.cliente, otra_empresa["refresh_token"]),
            ),
            _ESPERA_DE_BLOQUEO_S,
        )

    assert hermana.status_code == 200, hermana.text
    assert ajena.status_code == 200, ajena.text


@pytest.mark.asyncio
async def test_rotar_tres_familias_a_la_vez_responde_200_en_todas(entorno: Entorno):
    primera = await _registrar(entorno.cliente, "ana@empresa-a.com")
    login = await entorno.cliente.post(
        "/auth/login", json={"email": "ana@empresa-a.com", "contrasena": CONTRASENA}
    )
    assert login.status_code == 200, login.text
    otra_empresa = await _registrar(entorno.cliente, "beto@empresa-b.com")

    respuestas = await asyncio.wait_for(
        asyncio.gather(
            _refrescar(entorno.cliente, primera["refresh_token"]),
            _refrescar(entorno.cliente, str(login.json()["refresh_token"])),
            _refrescar(entorno.cliente, otra_empresa["refresh_token"]),
        ),
        _ESPERA_DE_RESPUESTA_S,
    )

    assert [r.status_code for r in respuestas] == [200, 200, 200]


@pytest.mark.asyncio
async def test_un_refresh_rechazado_suelta_el_lock_de_la_familia(
    entorno: Entorno, engine_dueno: AsyncEngine
):
    sesion = await _registrar(entorno.cliente, "ana@empresa.com")
    empresa = UUID(sesion["empresa_id"])
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            text(
                "UPDATE refresh_token SET expira_en = now() - interval '1 hour' WHERE empresa_id = :e"
            ),
            {"e": empresa},
        )

    rechazado = await _refrescar(entorno.cliente, sesion["refresh_token"])

    assert rechazado.json()["error"] == "SesionInvalida", rechazado.text
    assert await _contar_locks(engine_dueno, "advisory") == 0, "the rejected refresh kept a lock"
    assert await _contar_locks(engine_dueno, "esperando") == 0
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            text(
                "UPDATE refresh_token SET expira_en = now() + interval '30 days' WHERE empresa_id = :e"
            ),
            {"e": empresa},
        )
    siguiente = await asyncio.wait_for(
        _refrescar(entorno.cliente, sesion["refresh_token"]), _ESPERA_DE_BLOQUEO_S
    )
    assert siguiente.status_code == 200, siguiente.text
