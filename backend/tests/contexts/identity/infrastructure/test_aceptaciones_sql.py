"""The SQL `agregar` sends: its conflict target is named, never implicit.

A bare `ON CONFLICT DO NOTHING` swallows *any* unique violation, a primary key included, and
reports "already accepted" for a row that was never written. The conflict target is the pair of
partial unique indexes of migration 0041, and it has to match their columns **and** predicate
for PostgreSQL to infer the index. These tests read the compiled statement; the race itself
is covered against a real database in `tests/integracion/test_aceptacion_legal_postgres.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.domain.legal import AceptacionLegal, DocumentoLegal
from cheatsheet.contexts.identity.infrastructure.aceptaciones import (
    RepositorioAceptacionLegalPostgres,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.expression import ClauseElement


class _Resultado:
    def scalar_one_or_none(self) -> object:
        return uuid4()


class _SesionQueGraba:
    def __init__(self) -> None:
        self.sentencias: list[ClauseElement] = []

    async def execute(self, sentencia: ClauseElement) -> _Resultado:
        self.sentencias.append(sentencia)
        return _Resultado()


def _sql(sentencia: ClauseElement) -> str:
    compilada = sentencia.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compilada).split())


async def _sql_de(documento: DocumentoLegal) -> str:
    sesion = _SesionQueGraba()
    aceptacion = AceptacionLegal(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        usuario_id=UsuarioId(uuid4()),
        documento=documento,
        version="1.0",
        fecha_aceptacion=datetime(2026, 11, 1, tzinfo=UTC),
    )
    await RepositorioAceptacionLegalPostgres(sesion).agregar(aceptacion)  # type: ignore[arg-type]
    assert len(sesion.sentencias) == 1
    return _sql(sesion.sentencias[0])


@pytest.mark.asyncio
async def test_la_privacidad_nombra_el_indice_por_usuario_y_version() -> None:
    sql = await _sql_de(DocumentoLegal.PRIVACIDAD)

    assert "ON CONFLICT (usuario_id, version) WHERE documento = 'PRIVACIDAD' DO NOTHING" in sql


@pytest.mark.asyncio
async def test_los_terminos_nombran_el_indice_por_empresa_y_version() -> None:
    sql = await _sql_de(DocumentoLegal.TERMINOS)

    assert "ON CONFLICT (empresa_id, version) WHERE documento = 'TERMINOS' DO NOTHING" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("documento", list(DocumentoLegal))
async def test_ningun_documento_usa_un_on_conflict_sin_objetivo(documento: DocumentoLegal) -> None:
    sql = await _sql_de(documento)

    assert "ON CONFLICT DO NOTHING" not in sql
    assert "ON CONFLICT (id)" not in sql


def test_los_indices_del_modelo_son_los_que_el_objetivo_nombra() -> None:
    """If somebody changes an index, the conflict target has to change with it."""
    from cheatsheet.contexts.identity.infrastructure.models import AceptacionLegalORM

    parciales: dict[str | None, Any] = {
        indice.name: indice
        for indice in cast(Table, AceptacionLegalORM.__table__).indexes
        if indice.unique
    }
    assert [c.name for c in parciales["uq_aceptacion_legal_privacidad"].columns] == [
        "usuario_id",
        "version",
    ]
    assert [c.name for c in parciales["uq_aceptacion_legal_terminos"].columns] == [
        "empresa_id",
        "version",
    ]
