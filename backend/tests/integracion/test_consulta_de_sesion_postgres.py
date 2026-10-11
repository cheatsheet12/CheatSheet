"""The per-request session check against a real PostgreSQL: cases 14 to 16.

Row-Level Security is what makes the lookup company-scoped, and an in-memory double cannot
say anything about it. Kept apart from `test_identidad_postgres.py`, which is already at the
repository's file-length ceiling.
"""

from __future__ import annotations

from typing import Any

import pytest
from cheatsheet.contexts.identity.application.errors import MotivoDeRevocacion, SesionRevocada
from cheatsheet.contexts.identity.application.ports import EstadoActualDelUsuario
from cheatsheet.contexts.identity.domain.valores import EstadoUsuario, RolUsuario
from cheatsheet.contexts.identity.infrastructure.consulta_de_sesion import (
    ConsultaDeUsuarioVigentePostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import UsuarioId
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import (
    VERSION_DE_PRIVACIDAD,
    VERSION_DE_TERMINOS,
    verificador_de_sesion,
)
from tests.integracion.test_identidad_postgres import _crear_cuenta

pytestmark = [requiere_base, pytest.mark.integration]


async def _como_dueno(engine_dueno: AsyncEngine, sentencia: str, **parametros: Any) -> None:
    """Change a row without going through the code under test."""
    async with engine_dueno.begin() as conexion:
        await conexion.execute(text(sentencia), parametros)


@pytest.mark.asyncio
async def test_el_adaptador_devuelve_rol_estado_y_empresa_de_un_usuario_de_la_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    """Case 14, and it sees a change made behind its back: there is no cache to go stale."""
    empresa_id, usuario_id = await _crear_cuenta(sesiones, "ana@empresa.com")

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        antes = await ConsultaDeUsuarioVigentePostgres(sesion).estado_actual(
            UsuarioId(usuario_id), version_de_privacidad=VERSION_DE_PRIVACIDAD
        )
    await _como_dueno(
        engine_dueno,
        "UPDATE usuario SET rol = 'OPERADOR', estado = 'INACTIVO' WHERE id = :id",
        id=usuario_id,
    )
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        despues = await ConsultaDeUsuarioVigentePostgres(sesion).estado_actual(
            UsuarioId(usuario_id), version_de_privacidad=VERSION_DE_PRIVACIDAD
        )

    assert antes == EstadoActualDelUsuario(
        empresa_id=empresa_id,
        rol=RolUsuario.ADMINISTRADOR,
        estado=EstadoUsuario.ACTIVO,
        terminos_version=VERSION_DE_TERMINOS,
        acepto_privacidad_vigente=True,
    )
    assert despues == EstadoActualDelUsuario(
        empresa_id=empresa_id,
        rol=RolUsuario.OPERADOR,
        estado=EstadoUsuario.INACTIVO,
        terminos_version=VERSION_DE_TERMINOS,
        acepto_privacidad_vigente=True,
    )


@pytest.mark.asyncio
async def test_desde_la_sesion_de_otra_empresa_el_usuario_no_existe(
    sesiones: async_sessionmaker[AsyncSession],
):
    """Case 15. The row is there; Row-Level Security does not let company B see it."""
    _, usuario_de_a = await _crear_cuenta(sesiones, "ana@empresa-a.com")
    empresa_b, _ = await _crear_cuenta(sesiones, "beto@empresa-b.com")

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        visto = await ConsultaDeUsuarioVigentePostgres(sesion).estado_actual(
            UsuarioId(usuario_de_a), version_de_privacidad=VERSION_DE_PRIVACIDAD
        )

    assert visto is None


@pytest.mark.asyncio
async def test_el_verificador_trata_el_usuario_de_otra_empresa_como_inexistente(
    sesiones: async_sessionmaker[AsyncSession],
):
    """The token names company B but its `sub` is A's user: refused, without B learning
    anything about A (the end-to-end version is case 22)."""
    _, usuario_de_a = await _crear_cuenta(sesiones, "ana@empresa-a.com")
    empresa_b, _ = await _crear_cuenta(sesiones, "beto@empresa-b.com")

    with pytest.raises(SesionRevocada) as error:
        await verificador_de_sesion(sesiones).verificar(
            usuario_id=UsuarioId(usuario_de_a), empresa_id_del_token=empresa_b
        )

    assert error.value.motivo is MotivoDeRevocacion.USUARIO_INEXISTENTE


@pytest.mark.asyncio
async def test_la_verificacion_es_una_sola_sentencia_y_no_toma_bloqueos(
    sesiones: async_sessionmaker[AsyncSession], engine_aplicacion: AsyncEngine
):
    """Case 16. It runs on every request, so an N+1 would multiply, and a row lock would make
    a request wait for whoever is administering that user."""
    empresa_id, usuario_id = await _crear_cuenta(sesiones, "ana@empresa.com")
    sentencias: list[str] = []

    def registrar(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        sentencias.append(statement)

    event.listen(engine_aplicacion.sync_engine, "before_cursor_execute", registrar)
    try:
        identidad = await verificador_de_sesion(sesiones).verificar(
            usuario_id=UsuarioId(usuario_id), empresa_id_del_token=empresa_id
        )
    finally:
        event.remove(engine_aplicacion.sync_engine, "before_cursor_execute", registrar)

    consultas = [s for s in sentencias if "set_config" not in s]
    assert identidad.rol is RolUsuario.ADMINISTRADOR
    assert len(consultas) == 1, consultas
    assert consultas[0].lstrip().upper().startswith("SELECT")
    assert "FOR UPDATE" not in consultas[0].upper()
    assert "FOR SHARE" not in consultas[0].upper()
