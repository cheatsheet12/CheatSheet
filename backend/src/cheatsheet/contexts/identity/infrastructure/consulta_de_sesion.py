"""PostgreSQL side of the per-request session check.

Two classes, because they answer two different questions:

- `ConsultaDeUsuarioVigentePostgres` reads one row. It implements the port and knows SQL.
- `VerificadorDeSesionPostgres` owns the **lifetime** of that read: which connection it
  uses, how long each step may take, and, above all, that the connection is given back
  before the request goes on.

**Two time limits, one per step (`CLAUDE.md` §5), and they are not interchangeable.**
Taking a connection is bounded by `TIMEOUT_DE_CONEXION_SEGUNDOS` (10 s), the limit the whole
system already uses and the reason it is not shorter: a managed database suspends idle
compute, and waking it takes longer than three seconds. The user query, with the connection
already in hand, is bounded by `TIMEOUT_DE_CONSULTA_SEGUNDOS`. A primary-key read that takes
longer than that is a degraded database, not a sleeping one. Wrapping both in the short
limit would turn the first request of every morning into a 503. There is no retry: it would
not save a cold start and it would double the wait during an outage.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cheatsheet.contexts.identity.application.ports import EstadoActualDelUsuario
from cheatsheet.contexts.identity.application.verificacion_de_sesion import (
    IdentidadVigente,
    VerificarSesionVigente,
)
from cheatsheet.contexts.identity.domain.valores import EstadoUsuario, RolUsuario
from cheatsheet.contexts.identity.infrastructure.models import UsuarioORM
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

#: Seconds the user query may take once the connection is held. See the module docstring.
TIMEOUT_DE_CONSULTA_SEGUNDOS = 3.0


class ConsultaDeUsuarioVigentePostgres:
    """Implements `PortConsultaDeUsuarioVigente`: one statement, no locks.

    It runs under Row-Level Security, so the policy already limits it to the company the
    session was opened for. There is deliberately no `FOR UPDATE`: this read must never
    make a request wait for, or block, anything that is administering the same user.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def estado_actual(self, usuario_id: UsuarioId) -> EstadoActualDelUsuario | None:
        resultado = await self._sesion.execute(
            select(UsuarioORM.empresa_id, UsuarioORM.rol, UsuarioORM.estado).where(
                UsuarioORM.id == usuario_id
            )
        )
        fila = resultado.one_or_none()
        if fila is None:
            return None
        return EstadoActualDelUsuario(
            empresa_id=EmpresaId(fila.empresa_id),
            rol=RolUsuario(fila.rol),
            estado=EstadoUsuario(fila.estado),
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
        timeout_de_consulta: float = TIMEOUT_DE_CONSULTA_SEGUNDOS,
    ) -> None:
        self._sesiones = sesiones
        self._timeout_de_consulta = timeout_de_consulta

    async def verificar(
        self, *, usuario_id: UsuarioId, empresa_id_del_token: EmpresaId
    ) -> IdentidadVigente:
        # The signed `empresa_id` is what scopes the session, so Row-Level Security limits
        # the lookup to that company; the use case then compares the stored one anyway.
        # Taking the connection (the `set_config` inside) is bounded by the engine's own
        # connection timeout, not by the shorter limit below.
        async with sesion_de_empresa(self._sesiones, empresa_id_del_token) as sesion:
            caso = VerificarSesionVigente(consulta=ConsultaDeUsuarioVigentePostgres(sesion))
            async with asyncio.timeout(self._timeout_de_consulta):
                identidad = await caso.ejecutar(
                    usuario_id=usuario_id, empresa_id_del_token=empresa_id_del_token
                )
        return identidad
