"""PostgreSQL adapter for `PortRepositorioPuntoDeVenta`.

Same two conventions as every repository here: the mapping is hand-written in both
directions so the domain keeps no framework dependency (R1), and `empresa_id` never reaches
a `WHERE` clause because Row-Level Security already scopes the statement.

**One method is different from anything else in this system: `tomar_para_emitir`.** It is
decision D14 made real — `SELECT … FOR UPDATE` on the point of sale's row, so two
simultaneous issues serialise instead of drawing the same fiscal number. It is the same
mechanism epic 1 used for «always at least one Administrador», and for the same reason:
it is the only check that cannot lose a race with a second tab.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.billing.application.errors import PuntoDeVentaDuplicado
from cheatsheet.contexts.billing.application.puntos_de_venta import MENSAJE_DUPLICADO
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta
from cheatsheet.contexts.billing.infrastructure.models import PuntoDeVentaORM
from cheatsheet.shared.empresa import EmpresaId


def _a_dominio(fila: PuntoDeVentaORM) -> PuntoDeVenta:
    return PuntoDeVenta(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        numero=fila.numero,
        descripcion=fila.descripcion,
        activo=fila.activo,
        numerador_por_tipo=dict(fila.numerador_por_tipo or {}),
        created_at=fila.created_at,
    )


class RepositorioPuntoDeVentaPostgres:
    """Points of sale, backed by PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, punto: PuntoDeVenta) -> None:
        self._sesion.add(
            PuntoDeVentaORM(
                id=punto.id,
                empresa_id=punto.empresa_id,
                numero=punto.numero,
                descripcion=punto.descripcion,
                activo=punto.activo,
                numerador_por_tipo=dict(punto.numerador_por_tipo),
                created_at=punto.created_at,
            )
        )
        try:
            await self._sesion.flush()
        except IntegrityError as exc:
            # The unique index, not a prior read. HU-E5-05's message, so it reaches the
            # screen: these errors derive from `EntradaInvalida` and answer 422.
            raise PuntoDeVentaDuplicado(MENSAJE_DUPLICADO) from exc

    async def guardar(self, punto: PuntoDeVenta) -> None:
        fila = await self._sesion.get(PuntoDeVentaORM, punto.id)
        if fila is None:
            raise LookupError(f"El punto de venta {punto.id} no existe para esta empresa")
        fila.descripcion = punto.descripcion
        fila.activo = punto.activo
        # Reassigned rather than mutated: SQLAlchemy does not track in-place changes to a
        # JSONB dict, and a counter that silently fails to persist is a document number
        # reused on the next request.
        fila.numerador_por_tipo = dict(punto.numerador_por_tipo)
        await self._sesion.flush()

    async def buscar_por_id(self, punto_id: UUID) -> PuntoDeVenta | None:
        fila = await self._sesion.get(PuntoDeVentaORM, punto_id)
        return _a_dominio(fila) if fila is not None else None

    async def listar(self) -> list[PuntoDeVenta]:
        sentencia = select(PuntoDeVentaORM).order_by(PuntoDeVentaORM.numero)
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def tomar_para_emitir(self, punto_id: UUID) -> PuntoDeVenta | None:
        """Decision D14: the row, **locked for the rest of the transaction**.

        `with_for_update()` and not `nowait`: a second issue on the same point should
        *wait* rather than fail. Waiting is slow and correct; failing would push the retry
        into the caller, and a retry that re-reads the counter is the race again.
        """
        sentencia = select(PuntoDeVentaORM).where(PuntoDeVentaORM.id == punto_id).with_for_update()
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return _a_dominio(fila) if fila is not None else None
