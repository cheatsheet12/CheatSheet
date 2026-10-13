"""The block while a legal document is pending, end to end against PostgreSQL (cases 26, 29, 30).

HU-E1-03 RN-03 and HU-E1-08 RN-05: when the version in force changes, whoever owes it can read
the texts, accept and sign out, and nothing else. The catalogue ships one version of each
document, so "a new version appeared" is staged the way a deploy would leave the database: the
company's recorded terms and the person's privacy acceptance are set back as the owner role.
"""

from __future__ import annotations

import asyncio
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
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal
from cheatsheet.contexts.identity.infrastructure.consulta_de_sesion import (
    ConsultaDeUsuarioVigentePostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import UsuarioId
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import (
    CONSENTIMIENTO,
    VERSION_DE_PRIVACIDAD,
    VERSION_DE_TERMINOS,
)
from tests.integracion.test_identidad_postgres import _crear_cuenta

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
_BLOQUEO = "AceptacionLegalPendiente"
_TODAS = [
    {"documento": "PRIVACIDAD", "version": VERSION_DE_PRIVACIDAD},
    {"documento": "TERMINOS", "version": VERSION_DE_TERMINOS},
]


@pytest_asyncio.fixture
async def cliente(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )
    recursos = Recursos.crear(settings)
    transporte = httpx.ASGITransport(app=create_app(settings, recursos))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        yield cliente
    await recursos.cerrar()


async def _registrar(cliente: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str, str]:
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
    cuerpo = respuesta.json()
    cabeceras = {"Authorization": f"Bearer {cuerpo['access_token']}"}
    return cabeceras, str(cuerpo["empresa_id"]), str(cuerpo["usuario_id"])


async def _como_dueno(engine_dueno: AsyncEngine, sentencia: str, **parametros: Any) -> None:
    async with engine_dueno.begin() as conexion:
        await conexion.execute(text(sentencia), parametros)


async def _versiones(
    engine_dueno: AsyncEngine, documento: DocumentoLegal, empresa_id: str
) -> list[str]:
    async with engine_dueno.connect() as conexion:
        filas = await conexion.execute(
            text(
                "SELECT version FROM aceptacion_legal "
                "WHERE empresa_id = :e AND documento = :d ORDER BY version"
            ),
            {"e": empresa_id, "d": documento.value},
        )
        return [fila[0] for fila in filas]


async def _dejar_pendiente(engine_dueno: AsyncEngine, empresa_id: str, usuario_id: str) -> None:
    """What a deploy of two new versions leaves: the person's old policy, the company's old terms.

    The acceptances of the versions in force become acceptances of earlier ones, so history is
    what it would really be (case 30), not an empty table.
    """
    await _como_dueno(
        engine_dueno,
        "UPDATE aceptacion_legal SET version = '0.9' "
        "WHERE empresa_id = :e AND documento = 'PRIVACIDAD'",
        e=empresa_id,
    )
    await _como_dueno(
        engine_dueno,
        "UPDATE aceptacion_legal SET version = '1.0' "
        "WHERE empresa_id = :e AND documento = 'TERMINOS'",
        e=empresa_id,
    )
    await _como_dueno(
        engine_dueno,
        "UPDATE empresa SET terminos_version = '1.0' WHERE id = :e",
        e=empresa_id,
    )


# ------------------------------------------------------------------------------- case 26


@pytest.mark.asyncio
async def test_la_consulta_trae_terminos_y_privacidad_en_una_sentencia_bajo_rls(
    sesiones: async_sessionmaker[AsyncSession],
    engine_aplicacion: AsyncEngine,
    engine_dueno: AsyncEngine,
):
    empresa_id, usuario_id = await _crear_cuenta(sesiones, "ana@empresa.com")
    otra_empresa, _ = await _crear_cuenta(sesiones, "beto@otra.com")
    await _dejar_pendiente(engine_dueno, str(empresa_id), str(usuario_id))
    sentencias: list[str] = []

    def registrar(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        sentencias.append(statement)

    event.listen(engine_aplicacion.sync_engine, "before_cursor_execute", registrar)
    try:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            estado = await ConsultaDeUsuarioVigentePostgres(sesion).estado_actual(
                UsuarioId(usuario_id), version_de_privacidad=VERSION_DE_PRIVACIDAD
            )
    finally:
        event.remove(engine_aplicacion.sync_engine, "before_cursor_execute", registrar)
    async with sesion_de_empresa(sesiones, otra_empresa) as sesion:
        ajeno = await ConsultaDeUsuarioVigentePostgres(sesion).estado_actual(
            UsuarioId(usuario_id), version_de_privacidad=VERSION_DE_PRIVACIDAD
        )

    assert estado is not None
    assert estado.terminos_version == "1.0"
    assert estado.acepto_privacidad_vigente is False
    assert len([s for s in sentencias if "set_config" not in s]) == 1, sentencias
    assert ajeno is None, "another company's session must not see the user, nor the acceptance"


@pytest.mark.asyncio
async def test_la_privacidad_de_otra_version_no_cuenta_como_aceptada(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    empresa_id, usuario_id = await _crear_cuenta(sesiones, "ana@empresa.com")

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        consulta = ConsultaDeUsuarioVigentePostgres(sesion)
        vigente = await consulta.estado_actual(UsuarioId(usuario_id), version_de_privacidad="1.0")
        otra = await consulta.estado_actual(UsuarioId(usuario_id), version_de_privacidad="2.0")

    assert vigente is not None
    assert vigente.acepto_privacidad_vigente is True
    assert otra is not None
    assert otra.acepto_privacidad_vigente is False


# ------------------------------------------------------------ case 27 (real) and case 29


@pytest.mark.asyncio
async def test_con_pendientes_se_bloquea_todo_salvo_leer_aceptar_y_salir(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    cabeceras, empresa_id, usuario_id = await _registrar(cliente, "ana@empresa.com")
    assert (await cliente.get("/usuarios", headers=cabeceras)).status_code == 200
    antes = await cliente.get("/auth/empresa", headers=cabeceras)
    assert antes.json()["aceptaciones_pendientes"] == []

    await _dejar_pendiente(engine_dueno, empresa_id, usuario_id)

    bloqueada = await cliente.get("/usuarios", headers=cabeceras)
    assert bloqueada.status_code == 403
    assert bloqueada.json()["error"] == _BLOQUEO
    assert bloqueada.json()["pendientes"] == ["PRIVACIDAD", "TERMINOS"]
    assert (await cliente.put("/auth/empresa", headers=cabeceras, json={})).status_code == 403
    empresa = await cliente.get("/auth/empresa", headers=cabeceras)
    assert empresa.status_code == 200
    assert empresa.json()["aceptaciones_pendientes"] == ["PRIVACIDAD", "TERMINOS"]
    pendientes = await cliente.get("/legal/pendientes", headers=cabeceras)
    assert [p["documento"] for p in pendientes.json()["pendientes"]] == ["PRIVACIDAD", "TERMINOS"]
    assert (await cliente.get("/legal/terminos")).status_code == 200


@pytest.mark.asyncio
async def test_aceptar_desbloquea_en_la_solicitud_siguiente_y_repetir_no_duplica(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    """Case 29. The token is the one issued before the new versions existed."""
    cabeceras, empresa_id, usuario_id = await _registrar(cliente, "ana@empresa.com")
    await _dejar_pendiente(engine_dueno, empresa_id, usuario_id)
    assert (await cliente.get("/usuarios", headers=cabeceras)).status_code == 403

    aceptada = await cliente.post(
        "/legal/aceptaciones", headers=cabeceras, json={"documentos": _TODAS}
    )
    repetida = await cliente.post(
        "/legal/aceptaciones", headers=cabeceras, json={"documentos": _TODAS}
    )

    assert (aceptada.status_code, repetida.status_code) == (204, 204)
    assert (await cliente.get("/usuarios", headers=cabeceras)).status_code == 200
    assert (await cliente.get("/auth/empresa", headers=cabeceras)).json()[
        "aceptaciones_pendientes"
    ] == []
    assert await _versiones(engine_dueno, DocumentoLegal.PRIVACIDAD, empresa_id) == ["0.9", "1.0"]
    assert await _versiones(engine_dueno, DocumentoLegal.TERMINOS, empresa_id) == ["1.0", "1.1"]


@pytest.mark.asyncio
async def test_la_aceptacion_anterior_queda_en_el_historial(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    """Case 30 (RN-05: nothing is deleted, the new acceptance is added next to the old one)."""
    cabeceras, empresa_id, usuario_id = await _registrar(cliente, "ana@empresa.com")
    await _dejar_pendiente(engine_dueno, empresa_id, usuario_id)

    await cliente.post("/legal/aceptaciones", headers=cabeceras, json={"documentos": _TODAS})

    async with engine_dueno.connect() as conexion:
        total = (
            await conexion.execute(
                text("SELECT count(*) FROM aceptacion_legal WHERE empresa_id = :e"),
                {"e": empresa_id},
            )
        ).scalar_one()
        empresa = (
            await conexion.execute(
                text("SELECT terminos_version FROM empresa WHERE id = :e"), {"e": empresa_id}
            )
        ).scalar_one()
    assert total == 4
    assert empresa == VERSION_DE_TERMINOS


@pytest.mark.asyncio
async def test_aceptar_en_paralelo_deja_una_fila_y_un_evento_por_documento(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    """Two tabs, a double click: the indexes decide the race and nothing fails or doubles."""
    cabeceras, empresa_id, usuario_id = await _registrar(cliente, "ana@empresa.com")
    await _dejar_pendiente(engine_dueno, empresa_id, usuario_id)

    respuestas = await asyncio.gather(
        *(
            cliente.post("/legal/aceptaciones", headers=cabeceras, json={"documentos": _TODAS})
            for _ in range(5)
        )
    )

    assert [r.status_code for r in respuestas] == [204] * 5
    assert await _versiones(engine_dueno, DocumentoLegal.PRIVACIDAD, empresa_id) == ["0.9", "1.0"]
    assert await _versiones(engine_dueno, DocumentoLegal.TERMINOS, empresa_id) == ["1.0", "1.1"]
    async with engine_dueno.connect() as conexion:
        eventos = (
            await conexion.execute(
                text(
                    "SELECT accion, count(*) FROM registro_de_auditoria "
                    "WHERE empresa_id = :e AND accion IN "
                    "('aceptar_terminos', 'aceptar_politica_de_privacidad') GROUP BY accion"
                ),
                {"e": empresa_id},
            )
        ).all()
    # Registration wrote one of each; the five racing requests added exactly one more of each.
    assert {accion: total for accion, total in eventos} == {
        "aceptar_terminos": 2,
        "aceptar_politica_de_privacidad": 2,
    }


@pytest.mark.asyncio
async def test_un_operador_acepta_su_privacidad_pero_no_los_terminos(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    cabeceras, empresa_id, usuario_id = await _registrar(cliente, "ana@empresa.com")
    await _dejar_pendiente(engine_dueno, empresa_id, usuario_id)
    await _como_dueno(
        engine_dueno, "UPDATE usuario SET rol = 'OPERADOR' WHERE id = :u", u=usuario_id
    )

    # The terms are the company's: this Operador is blocked only by the policy.
    bloqueada = await cliente.get("/usuarios", headers=cabeceras)
    assert bloqueada.json()["pendientes"] == ["PRIVACIDAD"]
    terminos = await cliente.post(
        "/legal/aceptaciones", headers=cabeceras, json={"documentos": _TODAS}
    )
    assert terminos.status_code == 403
    assert await _versiones(engine_dueno, DocumentoLegal.TERMINOS, empresa_id) == ["1.0"]

    privacidad = await cliente.post(
        "/legal/aceptaciones", headers=cabeceras, json={"documentos": _TODAS[:1]}
    )

    assert privacidad.status_code == 204
    assert (await cliente.get("/auth/empresa", headers=cabeceras)).status_code == 200
    assert await _versiones(engine_dueno, DocumentoLegal.PRIVACIDAD, empresa_id) == ["0.9", "1.0"]


@pytest.mark.asyncio
async def test_aceptar_una_version_que_no_es_la_vigente_es_409_y_no_escribe(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    cabeceras, empresa_id, usuario_id = await _registrar(cliente, "ana@empresa.com")
    await _dejar_pendiente(engine_dueno, empresa_id, usuario_id)

    respuesta = await cliente.post(
        "/legal/aceptaciones",
        headers=cabeceras,
        json={"documentos": [{"documento": "PRIVACIDAD", "version": "0.9"}]},
    )

    assert respuesta.status_code == 409
    assert await _versiones(engine_dueno, DocumentoLegal.PRIVACIDAD, empresa_id) == ["0.9"]
    assert (await cliente.get("/usuarios", headers=cabeceras)).status_code == 403


@pytest.mark.asyncio
async def test_cerrar_sesion_y_renovarla_siguen_funcionando_con_pendientes(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    respuesta = await cliente.post(
        "/auth/registro",
        json={
            "email": "ana@empresa.com",
            "contrasena": CONTRASENA,
            "nombre": "Ana Perez",
            "consentimiento": CONSENTIMIENTO,
        },
    )
    sesion = respuesta.json()
    await _dejar_pendiente(engine_dueno, str(sesion["empresa_id"]), str(sesion["usuario_id"]))

    renovada = await cliente.post("/auth/refresh", json={"refresh_token": sesion["refresh_token"]})
    assert renovada.status_code == 200
    cerrada = await cliente.post(
        "/auth/logout", json={"refresh_token": renovada.json()["refresh_token"]}
    )
    assert cerrada.status_code == 204


@pytest.mark.asyncio
async def test_un_usuario_nuevo_no_nace_bloqueado(cliente: httpx.AsyncClient):
    """Registering accepts the versions in force, so the first request is not a 403."""
    cabeceras, _, _ = await _registrar(cliente, f"{uuid.uuid4().hex[:8]}@empresa.com")

    assert (await cliente.get("/usuarios", headers=cabeceras)).status_code == 200
