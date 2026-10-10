"""PostgreSQL side of the per-request session check.

Two classes, because they answer two different questions:

- `ConsultaDeUsuarioVigentePostgres` reads one row. It implements the port and knows SQL.
- `VerificadorDeSesionPostgres` owns the **lifetime** of that read: which connection it
  uses, how long each step may take, and, above all, that the connection is given back
  before the request goes on.

**What bounds each step (`CLAUDE.md` §5), and what does not.**

- *Connecting* is bounded by `TIMEOUT_DE_CONEXION_SEGUNDOS` (10 s), but that is only
  asyncpg's connect timeout: a managed database suspends idle compute and waking it takes
  longer than three seconds, which is why it is not shorter.
- *Waiting for a free pooled connection* is SQLAlchemy's `pool_timeout` (30 s by default;
  `crear_engine` does not configure it, and this unit does not change it).
- The `set_config` and `COMMIT` round trips have no limit of their own.
- *The user query*, with the connection in hand, is bounded by `TIMEOUT_DE_CONSULTA_SEGUNDOS`.
  A primary-key read that takes longer than that is a degraded database, not a sleeping one.
  Wrapping the whole check in that short limit would turn the first request of every morning
  into a 503. There is no retry: it would not save a cold start and would double the wait
  during an outage.

Every one of those failures is **fail-closed**: `verificar` raises `VerificacionNoDisponible`
and the middleware answers 503. That includes the asyncpg errors raised at connect time
(`CannotConnectNowError` while a database restarts, `TooManyConnectionsError`,
`InterfaceError`), which SQLAlchemy does not wrap. A **corrupt row** (a `rol` or `estado`
outside the enums) is deliberately *not* translated: it is a data-integrity error, not an
outage, and it escapes as `ValueError` (a 500, never a 2xx).
"""

from __future__ import annotations

import asyncio

import asyncpg
from sqlalchemy import exists, literal_column, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cheatsheet.contexts.identity.application.errors import VerificacionNoDisponible
from cheatsheet.contexts.identity.application.ports import EstadoActualDelUsuario
from cheatsheet.contexts.identity.application.verificacion_de_sesion import (
    IdentidadVigente,
    VerificarSesionVigente,
)
from cheatsheet.contexts.identity.domain.legal import CatalogoLegal
from cheatsheet.contexts.identity.domain.valores import EstadoUsuario, RolUsuario
from cheatsheet.contexts.identity.infrastructure.models import (
    AceptacionLegalORM,
    EmpresaORM,
    UsuarioORM,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

#: Seconds the user query may take once the connection is held. See the module docstring.
TIMEOUT_DE_CONSULTA_SEGUNDOS = 3.0

#: Failures of the database or the path to it. `SesionRevocada` is none of these, so it
#: passes through untouched. asyncpg's own errors are listed because SQLAlchemy does not wrap
#: the ones raised while connecting.
ERRORES_DE_INFRAESTRUCTURA = (
    SQLAlchemyError,
    OSError,
    TimeoutError,
    asyncpg.PostgresError,
    asyncpg.InterfaceError,
)


class ConsultaDeUsuarioVigentePostgres:
    """Implements `PortConsultaDeUsuarioVigente`: one statement, no locks.

    The statement joins `empresa` for the terms version on record and asks, with an `EXISTS`
    over the partial unique index of `aceptacion_legal`, whether this user accepted the privacy
    version in force. `'PRIVACIDAD'` is a literal in the SQL, not a bound parameter: the planner
    can only prove a partial index applicable from a literal, and a prepared statement's generic
    plan would otherwise fall back to scanning the table.

    It runs under Row-Level Security, so the policy already limits it to the company the
    session was opened for. There is deliberately no `FOR UPDATE`: this read must never
    make a request wait for, or block, anything that is administering the same user.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def estado_actual(
        self, usuario_id: UsuarioId, *, version_de_privacidad: str
    ) -> EstadoActualDelUsuario | None:
        acepto_privacidad = exists().where(
            AceptacionLegalORM.usuario_id == UsuarioORM.id,
            AceptacionLegalORM.documento == literal_column("'PRIVACIDAD'"),
            AceptacionLegalORM.version == version_de_privacidad,
        )
        resultado = await self._sesion.execute(
            select(
                UsuarioORM.empresa_id,
                UsuarioORM.rol,
                UsuarioORM.estado,
                EmpresaORM.terminos_version,
                acepto_privacidad.label("acepto_privacidad_vigente"),
            )
            .join(EmpresaORM, EmpresaORM.id == UsuarioORM.empresa_id)
            .where(UsuarioORM.id == usuario_id)
        )
        fila = resultado.one_or_none()
        if fila is None:
            return None
        return EstadoActualDelUsuario(
            empresa_id=EmpresaId(fila.empresa_id),
            rol=RolUsuario(fila.rol),
            estado=EstadoUsuario(fila.estado),
            terminos_version=fila.terminos_version,
            acepto_privacidad_vigente=bool(fila.acepto_privacidad_vigente),
        )


class VerificadorDeSesionPostgres:
    """Checks a token's claims against the database, and **returns the connection first**.

    The middleware that calls this wraps every route. If the check kept its connection
    while the route ran, each request would hold two and the pool would be exhausted at
    half the load, with the requests waiting on each other. So the session is opened,
    used and closed inside `verificar`, and nothing about it escapes.
    """

    def __init__(
        self,
        sesiones: async_sessionmaker[AsyncSession],
        *,
        catalogo: CatalogoLegal,
        reloj: Reloj,
        timeout_de_consulta: float = TIMEOUT_DE_CONSULTA_SEGUNDOS,
    ) -> None:
        self._sesiones = sesiones
        # Built once with the process (`api/main.py`); a request only looks versions up in it.
        self._catalogo = catalogo
        self._reloj = reloj
        self._timeout_de_consulta = timeout_de_consulta

    async def verificar(
        self, *, usuario_id: UsuarioId, empresa_id_del_token: EmpresaId
    ) -> IdentidadVigente:
        try:
            return await self._consultar(usuario_id, empresa_id_del_token)
        except ERRORES_DE_INFRAESTRUCTURA as error:
            raise VerificacionNoDisponible(error) from error

    async def _consultar(
        self, usuario_id: UsuarioId, empresa_id_del_token: EmpresaId
    ) -> IdentidadVigente:
        # The signed `empresa_id` is what scopes the session, so Row-Level Security limits
        # the lookup to that company; the use case then compares the stored one anyway.
        async with sesion_de_empresa(self._sesiones, empresa_id_del_token) as sesion:
            caso = VerificarSesionVigente(
                consulta=ConsultaDeUsuarioVigentePostgres(sesion),
                catalogo=self._catalogo,
                reloj=self._reloj,
            )
            async with asyncio.timeout(self._timeout_de_consulta):
                identidad = await caso.ejecutar(
                    usuario_id=usuario_id, empresa_id_del_token=empresa_id_del_token
                )
        return identidad
