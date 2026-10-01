"""PostgreSQL adapter for refresh tokens (ADR-011).

Rotation is read-check-write, so two requests on the same token can interleave and both
win. `tomar_con_familia_bloqueada` serializes them: it takes a transaction-scoped
advisory lock on the token's family before the token is read. The lock is released when
the transaction ends, which is owned by the unit of work, never by this repository.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import String, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.infrastructure.models import RefreshTokenORM
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

# First key of `pg_advisory_xact_lock(int4, int4)`: this project's refresh-family
# namespace (ASCII "RF" in the high bytes). The second key is `hashtext(familia_id)`.
# A hash collision only makes two families wait for each other; it exposes no data.
ESPACIO_FAMILIA_REFRESH = 0x5246_0001


class RepositorioRefreshTokenPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, token: RefreshToken) -> None:
        self._sesion.add(
            RefreshTokenORM(
                id=token.id,
                familia_id=token.familia_id,
                empresa_id=token.empresa_id,
                usuario_id=token.usuario_id,
                hash_del_token=token.hash_del_token,
                expira_en=token.expira_en,
                usado_en=token.usado_en,
                revocado=token.revocado,
            )
        )
        await self._sesion.flush()

    async def guardar(self, token: RefreshToken) -> None:
        fila = await self._sesion.get(RefreshTokenORM, token.id)
        if fila is None:
            await self.agregar(token)
            return
        fila.usado_en = token.usado_en
        fila.revocado = token.revocado
        await self._sesion.flush()

    async def buscar_por_hash(self, hash_del_token: str) -> RefreshToken | None:
        return await self._cargar(hash_del_token)

    async def tomar_con_familia_bloqueada(self, hash_del_token: str) -> RefreshToken | None:
        """Lock the token's family, then read the token.

        Order matters. (1) Only the `familia_id` *column* is selected: no entity enters the
        session's identity map. (2) An unknown hash takes no lock. (3) The advisory lock.
        (4) The ORM load of the token is the first in this session, so it is fresh and
        includes everything committed by whoever held the lock before.
        """
        consulta = select(RefreshTokenORM.familia_id).where(
            RefreshTokenORM.hash_del_token == hash_del_token
        )
        familia_id = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if familia_id is None:
            return None
        await self._sesion.execute(
            select(
                func.pg_advisory_xact_lock(
                    ESPACIO_FAMILIA_REFRESH, func.hashtext(cast(familia_id, String))
                )
            )
        )
        return await self._cargar(hash_del_token)

    async def _cargar(self, hash_del_token: str) -> RefreshToken | None:
        consulta = select(RefreshTokenORM).where(RefreshTokenORM.hash_del_token == hash_del_token)
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if fila is None:
            return None
        return RefreshToken(
            id=fila.id,
            familia_id=fila.familia_id,
            empresa_id=EmpresaId(fila.empresa_id),
            usuario_id=UsuarioId(fila.usuario_id),
            hash_del_token=fila.hash_del_token,
            expira_en=fila.expira_en,
            usado_en=fila.usado_en,
            revocado=fila.revocado,
        )

    async def revocar_familia(self, familia_id: UUID) -> int:
        resultado = await self._sesion.execute(
            update(RefreshTokenORM)
            .where(RefreshTokenORM.familia_id == familia_id)
            .where(RefreshTokenORM.revocado.is_(False))
            .values(revocado=True)
        )
        await self._sesion.flush()
        return int(resultado.rowcount or 0)

    async def revocar_de_usuario(self, usuario_id: UsuarioId) -> int:
        """Every live session of one user — HU-E1-06 RN-01.

        Families, not just the current one: someone signed in on a phone and a laptop has
        two, and deactivating them has to reach both.
        """
        resultado = await self._sesion.execute(
            update(RefreshTokenORM)
            .where(RefreshTokenORM.usuario_id == usuario_id)
            .where(RefreshTokenORM.revocado.is_(False))
            .values(revocado=True)
        )
        await self._sesion.flush()
        return int(resultado.rowcount or 0)
