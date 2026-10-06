"""Finding out which company a credential belongs to, before any transaction is scoped.

Three operations in this system happen **before there is a tenant**: signing in, rotating
a refresh token, and accepting an invitation. In all three the caller holds a credential
and the company is precisely what has to be discovered from it.

**This module exists because getting that wrong is silent.** The previous version of the
sign-in path opened the transaction with an invented `EmpresaId(uuid4())`, looked the user
up through the `SECURITY DEFINER` function — which works, because those functions ignore
Row-Level Security — and then wrote the refresh token row with the *real* `empresa_id`
while `app.current_empresa` still held the invented one. The policy's `WITH CHECK`
rejects that `INSERT`, and the `UPDATE` in sign-out does something worse: its `USING`
clause matches no rows, so the revocation does not fail, it just does not happen. A
sign-out that does not sign anybody out.

So: **resolve first, in a session that declares no company and can therefore write
nothing, then open the real unit of work with the answer.** Two transactions instead of
one, which is the price of not having a tenant yet.

Each function below returns an `EmpresaId` and nothing else. The `SECURITY DEFINER`
functions they call are narrow for the same reason as the two from migration 0002: they
are the only holes in the barrier, so each one returns the minimum that makes its caller
work, and is named so it shows up in any audit.
"""

from __future__ import annotations

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cheatsheet.contexts.identity.domain.valores import Email
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.shared.empresa import EmpresaId

CONSULTA_EMPRESA_DE_EMAIL = text("SELECT empresa_id FROM buscar_usuario_para_login(:email)")
CONSULTA_EMPRESA_DE_REFRESH = text("SELECT buscar_empresa_de_refresh(:hash)")
CONSULTA_EMPRESA_DE_INVITACION = text("SELECT buscar_empresa_de_invitacion(:hash)")


async def _resolver(
    sesiones: async_sessionmaker[AsyncSession], consulta: TextClause, parametros: dict[str, str]
) -> EmpresaId | None:
    async with sesion_sin_empresa(sesiones) as sesion:
        resultado = await sesion.execute(consulta, parametros)
        # `scalar_one_or_none` would raise on the extra rows these queries cannot return,
        # and `scalar` on a function that returned NULL gives None either way.
        valor = resultado.scalar()
    return EmpresaId(valor) if valor is not None else None


async def empresa_de_email(
    sesiones: async_sessionmaker[AsyncSession], email: Email
) -> EmpresaId | None:
    """Sign-in. `None` means no account with that email — the caller answers with the
    same `CredencialesInvalidas` it would give for a wrong password, so the endpoint
    never becomes an account enumerator."""
    return await _resolver(sesiones, CONSULTA_EMPRESA_DE_EMAIL, {"email": str(email)})


async def empresa_de_refresh(
    sesiones: async_sessionmaker[AsyncSession], hash_del_token: str
) -> EmpresaId | None:
    """Rotation and sign-out. Takes the **hash**, never the token itself."""
    return await _resolver(sesiones, CONSULTA_EMPRESA_DE_REFRESH, {"hash": hash_del_token})


async def empresa_de_invitacion(
    sesiones: async_sessionmaker[AsyncSession], hash_del_token: str
) -> EmpresaId | None:
    """Accepting an invitation. Takes the **hash**, never the token itself."""
    return await _resolver(sesiones, CONSULTA_EMPRESA_DE_INVITACION, {"hash": hash_del_token})
