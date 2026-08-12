"""PostgreSQL adapter for `PortRegistroDeAuditoria`.

The mapping between the ORM row and the aggregate is written by hand, in both
directions, and that is deliberate: the aggregate is a frozen dataclass with value
objects and the row is flat columns. Letting SQLAlchemy hydrate the aggregate
directly would mean giving the domain a mutable identity map and a framework
dependency — which rule R1 forbids, for exactly this reason.

`tenant_id` is never added to a `WHERE` clause here. Row-Level Security already
scopes every statement to `app.current_tenant` (see `platform/database.py`), and
writing the filter again in the application would create a second, weaker copy of the
rule that can drift from the policy.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.observability.application.errors import RegistroDuplicado
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.contexts.observability.infrastructure.models import RegistroDeAuditoriaORM
from cheatsheet.shared.auditoria import (
    EntidadAfectada,
    Iniciador,
    Modulo,
    Resultado,
    TipoDeIniciador,
)
from cheatsheet.shared.tenant import TenantId, UserId


def _a_orm(registro: RegistroDeAuditoria) -> RegistroDeAuditoriaORM:
    return RegistroDeAuditoriaORM(
        id=registro.id,
        evento_id=registro.evento_id,
        tenant_id=registro.tenant_id,
        modulo=registro.modulo.value,
        operacion=registro.operacion,
        entidad_tipo=registro.entidad_afectada.tipo,
        entidad_identificador=registro.entidad_afectada.identificador,
        iniciador_tipo=registro.iniciador.tipo.value,
        iniciador_user_id=registro.iniciador.user_id,
        iniciador_referencia=registro.iniciador.referencia,
        resultado=registro.resultado.value,
        ocurrido_en=registro.ocurrido_en,
        detalle=dict(registro.detalle),
    )


def _a_dominio(fila: RegistroDeAuditoriaORM) -> RegistroDeAuditoria:
    detalle: dict[str, Any] = fila.detalle or {}
    return RegistroDeAuditoria(
        id=fila.id,
        evento_id=fila.evento_id,
        tenant_id=TenantId(fila.tenant_id),
        modulo=Modulo(fila.modulo),
        operacion=fila.operacion,
        entidad_afectada=EntidadAfectada(
            tipo=fila.entidad_tipo, identificador=fila.entidad_identificador
        ),
        iniciador=Iniciador(
            tipo=TipoDeIniciador(fila.iniciador_tipo),
            user_id=UserId(fila.iniciador_user_id) if fila.iniciador_user_id else None,
            referencia=fila.iniciador_referencia,
        ),
        resultado=Resultado(fila.resultado),
        ocurrido_en=fila.ocurrido_en,
        detalle={clave: str(valor) for clave, valor in detalle.items()},
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
