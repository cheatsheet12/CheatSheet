"""PostgreSQL adapter for the record of legal acceptances (HU-E1-08 RN-02).

Only `INSERT` and `SELECT`: the application role has no `UPDATE` or `DELETE` on the table
(migration 0041), so an acceptance can be added and read, never rewritten.
"""

from __future__ import annotations

from sqlalchemy import exists, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.identity.domain.legal import AceptacionLegal, DocumentoLegal
from cheatsheet.contexts.identity.infrastructure.models import AceptacionLegalORM
from cheatsheet.shared.empresa import UsuarioId

#: The conflict target of each document: the columns and predicate of the partial unique index of
#: migration 0041 that guards it, so PostgreSQL infers that index and no other. Anything else that
#: conflicts (the primary key, say) is not an "already accepted" and must surface as an error.
_OBJETIVO_DE_CONFLICTO = {
    DocumentoLegal.PRIVACIDAD: (["usuario_id", "version"], text("documento = 'PRIVACIDAD'")),
    DocumentoLegal.TERMINOS: (["empresa_id", "version"], text("documento = 'TERMINOS'")),
}


class RepositorioAceptacionLegalPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, aceptacion: AceptacionLegal) -> bool:
        """`INSERT ... ON CONFLICT (<index>) DO NOTHING`: the partial unique indexes decide a race.

        Two requests accepting the same version at once both pass the caller's check; the
        second insert is refused by the index and reports `False` instead of failing the
        transaction with an integrity error.
        """
        columnas, predicado = _OBJETIVO_DE_CONFLICTO[aceptacion.documento]
        resultado = await self._sesion.execute(
            insert(AceptacionLegalORM)
            .values(
                id=aceptacion.id,
                empresa_id=aceptacion.empresa_id,
                usuario_id=aceptacion.usuario_id,
                documento=aceptacion.documento.value,
                version=aceptacion.version,
                fecha_aceptacion=aceptacion.fecha_aceptacion,
            )
            .on_conflict_do_nothing(index_elements=columnas, index_where=predicado)
            .returning(AceptacionLegalORM.id)
        )
        return resultado.scalar_one_or_none() is not None

    async def acepto(self, usuario_id: UsuarioId, documento: DocumentoLegal, version: str) -> bool:
        consulta = select(
            exists().where(
                AceptacionLegalORM.usuario_id == usuario_id,
                AceptacionLegalORM.documento == documento.value,
                AceptacionLegalORM.version == version,
            )
        )
        return bool((await self._sesion.execute(consulta)).scalar())
