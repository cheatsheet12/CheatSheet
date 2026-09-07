"""PostgreSQL adapter for `PortRegistroDeAuditoria`.

The mapping between the ORM row and the aggregate is written by hand, in both
directions, and that is deliberate: the aggregate is a frozen dataclass and the row is
a mutable ORM instance. Letting SQLAlchemy hydrate the aggregate directly would mean
giving the domain an identity map and a framework dependency — which rule R1 forbids,
for exactly this reason.

`empresa_id` is never added to a `WHERE` clause here. Row-Level Security already scopes
every statement to `app.current_empresa` (see `platform/database.py`), and writing the
filter again in the application would create a second, weaker copy of the rule that can
drift from the policy.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.observability.application.errors import RegistroDuplicado
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.contexts.observability.infrastructure.models import RegistroDeAuditoriaORM
from cheatsheet.shared.auditoria import Iniciador, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId


def _a_orm(registro: RegistroDeAuditoria) -> RegistroDeAuditoriaORM:
    return RegistroDeAuditoriaORM(
        id=registro.id,
        evento_id=registro.evento_id,
        empresa_id=registro.empresa_id,
        usuario_id=registro.usuario_id,
        modulo=registro.modulo.value,
        accion=registro.accion,
        entidad_afectada=registro.entidad_afectada,
        resultado=registro.resultado.value,
        direccion_ip=registro.direccion_ip,
        iniciador=registro.iniciador.value,
        timestamp=registro.timestamp,
    )


def _a_dominio(fila: RegistroDeAuditoriaORM) -> RegistroDeAuditoria:
    return RegistroDeAuditoria(
        id=fila.id,
        evento_id=fila.evento_id,
        empresa_id=EmpresaId(fila.empresa_id),
        usuario_id=UsuarioId(fila.usuario_id) if fila.usuario_id is not None else None,
        modulo=Modulo(fila.modulo),
        accion=fila.accion,
        entidad_afectada=fila.entidad_afectada,
        resultado=Resultado(fila.resultado),
        direccion_ip=fila.direccion_ip,
        iniciador=Iniciador(fila.iniciador),
        timestamp=fila.timestamp,
    )


class RepositorioDeAuditoriaPostgres:
    """Implements `PortRegistroDeAuditoria`. Append and read — there is no update."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, registro: RegistroDeAuditoria) -> None:
        # The insert runs inside a SAVEPOINT. Auditing shares the transaction of the
        # operation it describes, so a plain rollback here would undo that operation
        # too — a redelivered event would cancel real business work. The savepoint
        # scopes the failure to this one statement.
        try:
            async with self._sesion.begin_nested():
                self._sesion.add(_a_orm(registro))
                await self._sesion.flush()
        except IntegrityError as exc:
            # The unique index on evento_id fired: a concurrent delivery got here
            # first. Expected under at-least-once delivery, not an anomaly.
            raise RegistroDuplicado(registro.evento_id) from exc

    async def buscar_por_evento(self, evento_id: UUID) -> RegistroDeAuditoria | None:
        consulta = select(RegistroDeAuditoriaORM).where(
            RegistroDeAuditoriaORM.evento_id == evento_id
        )
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        return _a_dominio(fila) if fila is not None else None

    async def buscar_por_id(self, registro_id: UUID) -> RegistroDeAuditoria | None:
        fila = await self._sesion.get(RegistroDeAuditoriaORM, registro_id)
        return _a_dominio(fila) if fila is not None else None
