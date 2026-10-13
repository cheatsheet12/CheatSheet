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

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.observability.application.errors import RegistroDuplicado
from cheatsheet.contexts.observability.application.ports import FiltrosDeBitacora
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
        detalle=dict(registro.detalle) if registro.detalle is not None else None,
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
        detalle=dict(fila.detalle) if fila.detalle is not None else None,
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

    async def listar(self, filtros: FiltrosDeBitacora) -> list[RegistroDeAuditoria]:
        consulta = _acotar(select(RegistroDeAuditoriaORM), filtros)
        consulta = (
            consulta.order_by(RegistroDeAuditoriaORM.timestamp.desc())
            .limit(filtros.limite)
            .offset(filtros.desplazamiento)
        )
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def listar_de_entidad(self, entidad: str) -> list[RegistroDeAuditoria]:
        """El timeline de HU-E12-02: todo lo que le pasó a una entidad, en orden.

        Ascendente y no descendente como el listado: un timeline se lee desde el principio, y
        que la pantalla tenga que darlo vuelta es cómo un paso termina fuera de lugar.
        """
        consulta = (
            select(RegistroDeAuditoriaORM)
            .where(RegistroDeAuditoriaORM.entidad_afectada == entidad)
            .order_by(RegistroDeAuditoriaORM.timestamp.asc())
        )
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def contar(self, filtros: FiltrosDeBitacora) -> int:
        # `count(*)` in the database rather than `len()` in the process: this table has one
        # row per operation the company ever performed, and a month of a busy one is not a
        # list worth building to measure it. The limit is deliberately not applied — a
        # count is not a page, and capping it would report a smaller number than the truth.
        consulta = _acotar(select(func.count()).select_from(RegistroDeAuditoriaORM), filtros)
        return int((await self._sesion.execute(consulta)).scalar_one())


def _acotar(consulta: Select[Any], filtros: FiltrosDeBitacora) -> Select[Any]:
    """The `WHERE` shared by the two reads, written once.

    Two statements that must agree on what they are talking about — a count and the list
    it counts — are the classic place for a filter to be applied to one and forgotten in
    the other, leaving a screen that says "43 operations" above 40 rows.
    """
    if filtros.desde is not None:
        consulta = consulta.where(RegistroDeAuditoriaORM.timestamp >= filtros.desde)
    if filtros.hasta is not None:
        consulta = consulta.where(RegistroDeAuditoriaORM.timestamp <= filtros.hasta)
    if filtros.modulos:
        consulta = consulta.where(
            RegistroDeAuditoriaORM.modulo.in_([uno.value for uno in filtros.modulos])
        )
    if filtros.resultados:
        consulta = consulta.where(
            RegistroDeAuditoriaORM.resultado.in_([uno.value for uno in filtros.resultados])
        )
    if filtros.iniciadores:
        consulta = consulta.where(
            RegistroDeAuditoriaORM.iniciador.in_([uno.value for uno in filtros.iniciadores])
        )
    if filtros.texto or filtros.clientes:
        consulta = consulta.where(or_(*_condiciones_de_busqueda(filtros)))
    return consulta


def _condiciones_de_busqueda(filtros: FiltrosDeBitacora) -> list[ColumnElement[bool]]:
    """Lo que «Buscar» puede encontrar; basta con que se cumpla una (HU-E12-01 RN-03).

    El texto se busca con `ILIKE` sobre las dos columnas donde está escrito qué se hizo y sobre
    qué. El patrón y los ids se pasan como parámetros y nunca interpolados: los escribe —o los
    elige— un usuario, que es exactamente la entrada que no se concatena en un SQL.

    Los clientes (#176) traen las operaciones sobre `cliente:<id>` y las que guardan ese
    `cliente_id` en su detalle, que es como un turno dice de quién es. El prefijo va en
    minúscula porque así lo escribe `master_data`, y así está todo el historial guardado.
    """
    condiciones: list[ColumnElement[bool]] = []
    if filtros.texto:
        patron = f"%{filtros.texto.strip()}%"
        condiciones.append(RegistroDeAuditoriaORM.accion.ilike(patron))
        condiciones.append(RegistroDeAuditoriaORM.entidad_afectada.ilike(patron))
    if filtros.clientes:
        ids = [str(uno) for uno in filtros.clientes]
        condiciones.append(
            RegistroDeAuditoriaORM.entidad_afectada.in_([f"cliente:{uno}" for uno in ids])
        )
        condiciones.append(RegistroDeAuditoriaORM.detalle["cliente_id"].astext.in_(ids))
    return condiciones
