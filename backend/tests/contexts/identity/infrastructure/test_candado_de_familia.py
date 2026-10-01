"""Shape of `tomar_con_familia_bloqueada` (case 8 of the refresh-concurrente unit).

This does not reproduce the race (that is `tests/integracion/test_refresh_concurrente.py`,
against PostgreSQL). It pins the order the fix depends on: family id as a *column*, then
the advisory lock, and only then the ORM load of the token, so the load is the first one in
the session and cannot come from a stale identity map.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.infrastructure.models import RefreshTokenORM
from cheatsheet.contexts.identity.infrastructure.repositories import (
    RepositorioRefreshTokenPostgres,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class _Resultado:
    def __init__(self, valor: Any) -> None:
        self._valor = valor

    def scalar_one_or_none(self) -> Any:
        return self._valor


@dataclass
class _SesionGrabadora:
    """Stands in for AsyncSession: records each statement compiled for PostgreSQL."""

    respuestas: list[Any]
    sentencias: list[str] = field(default_factory=list)

    async def execute(self, sentencia: Any) -> _Resultado:
        self.sentencias.append(
            " ".join(str(sentencia.compile(dialect=postgresql.dialect())).split())
        )
        return _Resultado(self.respuestas.pop(0))


def _fila(familia_id: Any) -> RefreshTokenORM:
    return RefreshTokenORM(
        id=uuid4(),
        familia_id=familia_id,
        empresa_id=uuid4(),
        usuario_id=uuid4(),
        hash_del_token="h" * 64,
        expira_en=datetime(2030, 1, 1, tzinfo=UTC),
        usado_en=None,
        revocado=False,
    )


async def test_toma_el_candado_entre_la_columna_y_la_carga_del_token() -> None:
    familia_id = uuid4()
    sesion = _SesionGrabadora(respuestas=[familia_id, None, _fila(familia_id)])

    repositorio = RepositorioRefreshTokenPostgres(cast(AsyncSession, sesion))
    token = await repositorio.tomar_con_familia_bloqueada("h" * 64)

    assert token is not None
    assert token.familia_id == familia_id
    primera, segunda, tercera = sesion.sentencias
    assert primera.startswith("SELECT refresh_token.familia_id FROM refresh_token")
    assert "refresh_token.hash_del_token" in primera
    assert "pg_advisory_xact_lock" in segunda
    assert "hashtext" in segunda
    assert tercera.startswith("SELECT refresh_token.id")


async def test_con_un_hash_desconocido_no_toma_ningun_candado() -> None:
    sesion = _SesionGrabadora(respuestas=[None])

    repositorio = RepositorioRefreshTokenPostgres(cast(AsyncSession, sesion))
    token = await repositorio.tomar_con_familia_bloqueada("x" * 64)

    assert token is None
    assert len(sesion.sentencias) == 1
    assert "pg_advisory_xact_lock" not in sesion.sentencias[0]
