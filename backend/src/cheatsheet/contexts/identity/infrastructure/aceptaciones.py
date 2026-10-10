"""PostgreSQL adapter for the record of legal acceptances (HU-E1-08 RN-02).

Only `INSERT` and `SELECT`: the application role has no `UPDATE` or `DELETE` on the table
(migration 0041), so an acceptance can be added and read, never rewritten.
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.identity.domain.legal import AceptacionLegal, DocumentoLegal
from cheatsheet.contexts.identity.infrastructure.models import AceptacionLegalORM
from cheatsheet.shared.empresa import UsuarioId


class RepositorioAceptacionLegalPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, aceptacion: AceptacionLegal) -> None:
        self._sesion.add(
            AceptacionLegalORM(
                id=aceptacion.id,
                empresa_id=aceptacion.empresa_id,
                usuario_id=aceptacion.usuario_id,
                documento=aceptacion.documento.value,
                version=aceptacion.version,
                fecha_aceptacion=aceptacion.fecha_aceptacion,
            )
        )
        await self._sesion.flush()

    async def acepto(self, usuario_id: UsuarioId, documento: DocumentoLegal, version: str) -> bool:
        consulta = select(
            exists().where(
                AceptacionLegalORM.usuario_id == usuario_id,
                AceptacionLegalORM.documento == documento.value,
                AceptacionLegalORM.version == version,
            )
        )
        return bool((await self._sesion.execute(consulta)).scalar())
