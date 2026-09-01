"""PostgreSQL adapter for `PortRepositorioCliente`.

Nothing here filters by `empresa_id` except the listing, and that is not an omission:
every statement runs inside a session that has already set `app.current_empresa`, and
the RLS policy of migration 0008 does the filtering. A `WHERE empresa_id = …` alongside
it would be a second barrier that *looks* like the real one, and the day somebody forgot
to write it nothing would fail — the worst property a security check can have. The
listing passes the company id anyway, because it also drives the index its `COUNT` uses.

**Two things guard RN-03, and they are not redundant.** The unique index is what
*prevents* a duplicate: it cannot lose a race with a second tab. The lookup before the
insert is what *names* it — the acceptance criterion asks the screen to offer the
duplicate, not merely to mention it, and by the time the index fires the session is
unusable and no second query can be made.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.master_data.application.errors import ClienteDuplicado
from cheatsheet.contexts.master_data.domain.cliente import Cliente, FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.servicio import FiltrosDeServicio, Servicio
from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.contexts.master_data.infrastructure.models import (
    INDICE_CUIT_UNICO,
    ClienteCategoriaORM,
    ClienteORM,
    ServicioCategoriaORM,
    ServicioORM,
)
from cheatsheet.shared.contacto import Email, Telefono
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CUIT, CondicionIVA

MENSAJE_DUPLICADO = "Ya existe un cliente con ese CUIT."


def _a_dominio(fila: ClienteORM) -> Cliente:
    return Cliente(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        nombre=fila.nombre,
        origen=OrigenDato(fila.origen),
        creado_en=fila.created_at,
        actualizado_en=fila.updated_at,
        cuit=CUIT(fila.cuit) if fila.cuit else None,
        condicion_iva=CondicionIVA(fila.condicion_iva) if fila.condicion_iva else None,
        contacto_whatsapp=Telefono(fila.contacto_whatsapp) if fila.contacto_whatsapp else None,
        contacto_email=Email(fila.contacto_email) if fila.contacto_email else None,
        presente_en_planilla=fila.presente_en_planilla,
        referencia_fila_planilla=fila.referencia_fila_planilla,
        activo=fila.activo,
    )


def _volcar(cliente: Cliente, fila: ClienteORM) -> None:
    fila.empresa_id = cliente.empresa_id
    fila.nombre = cliente.nombre
    fila.cuit = cliente.cuit.valor if cliente.cuit else None
    fila.condicion_iva = cliente.condicion_iva.value if cliente.condicion_iva else None
    fila.contacto_whatsapp = str(cliente.contacto_whatsapp) if cliente.contacto_whatsapp else None
    fila.contacto_email = str(cliente.contacto_email) if cliente.contacto_email else None
    fila.origen = cliente.origen.value
    fila.presente_en_planilla = cliente.presente_en_planilla
    fila.referencia_fila_planilla = cliente.referencia_fila_planilla
    fila.activo = cliente.activo
    fila.created_at = cliente.creado_en
    fila.updated_at = cliente.actualizado_en


Consulta = Select[tuple[ClienteORM]]


def _filtrar(consulta: Consulta, filtros: FiltrosDeCliente) -> Consulta:
    """The three filters PAN-DM-01 offers. The category one arrives with its own unit."""
    if filtros.texto:
        patron = f"%{filtros.texto.lower()}%"
        consulta = consulta.where(
            or_(func.lower(ClienteORM.nombre).like(patron), ClienteORM.cuit.like(patron))
        )
    if filtros.origen is not None:
        consulta = consulta.where(ClienteORM.origen == filtros.origen.value)
    if filtros.solo_activos:
        consulta = consulta.where(ClienteORM.activo.is_(True))
    if filtros.categoria_id is not None:
        # HU-E4-04: «filtrable por esa categoria». Un JOIN y no un `IN (subconsulta)`
        # porque la clave primaria compuesta del enlace ya garantiza una fila por par:
        # el JOIN no puede duplicar clientes.
        consulta = consulta.join(
            ClienteCategoriaORM, ClienteCategoriaORM.cliente_id == ClienteORM.id
        ).where(ClienteCategoriaORM.categoria_id == filtros.categoria_id)
    return consulta


class RepositorioClientePostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, cliente: Cliente) -> None:
        await self._exigir_cuit_libre(cliente)
        fila = ClienteORM(id=cliente.id)
        _volcar(cliente, fila)
        self._sesion.add(fila)
        await self._descargar()

    async def guardar(self, cliente: Cliente) -> None:
        fila = await self._sesion.get(ClienteORM, cliente.id)
        if fila is None:
            await self.agregar(cliente)
            return
        await self._exigir_cuit_libre(cliente)
        _volcar(cliente, fila)
        await self._descargar()

    async def _exigir_cuit_libre(self, cliente: Cliente) -> None:
        """Name the duplicate before the index has to stop it. See the module docstring."""
        if cliente.cuit is None:
            return
        existente = await self.buscar_por_cuit(cliente.cuit.valor)
        if existente is not None and existente.id != cliente.id:
            raise ClienteDuplicado(MENSAJE_DUPLICADO, cliente_existente_id=existente.id)

    async def _descargar(self) -> None:
        """`flush`, with the one integrity error this table can raise translated.

        Only the CUIT index becomes a domain error. Anything else — a broken foreign key,
        a null in a NOT NULL column — is a bug, and a bug must not reach the user dressed
        up as a business rule.
        """
        try:
            await self._sesion.flush()
        except IntegrityError as exc:
            if INDICE_CUIT_UNICO not in str(exc.orig):
                raise
            raise ClienteDuplicado(MENSAJE_DUPLICADO) from exc

    async def buscar_por_id(self, cliente_id: UUID) -> Cliente | None:
        fila = await self._sesion.get(ClienteORM, cliente_id)
        return _a_dominio(fila) if fila is not None else None

    async def buscar_por_cuit(self, cuit: str) -> Cliente | None:
        fila = await self._sesion.scalar(select(ClienteORM).where(ClienteORM.cuit == cuit))
        return _a_dominio(fila) if fila is not None else None

    async def listar(
        self, *, empresa_id: EmpresaId, filtros: FiltrosDeCliente, pagina: Pagina
    ) -> tuple[Sequence[Cliente], int]:
        base = select(ClienteORM).where(ClienteORM.empresa_id == empresa_id)
        filtrada = _filtrar(base, filtros)
        total = await self._sesion.scalar(select(func.count()).select_from(filtrada.subquery()))
        filas = await self._sesion.scalars(
            filtrada.order_by(ClienteORM.nombre).limit(pagina.limite).offset(pagina.desplazamiento)
        )
        return [_a_dominio(fila) for fila in filas], int(total or 0)


def _servicio_a_dominio(fila: ServicioORM) -> Servicio:
    return Servicio(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        nombre=fila.nombre,
        precio=fila.precio,
        alicuota_iva=AlicuotaIVA.desde_tasa(fila.alicuota_iva),
        origen=OrigenDato(fila.origen),
        creado_en=fila.created_at,
        actualizado_en=fila.updated_at,
        agendable=fila.agendable,
        duracion_estandar_min=fila.duracion_estandar_min,
        presente_en_planilla=fila.presente_en_planilla,
        activo=fila.activo,
    )


def _volcar_servicio(servicio: Servicio, fila: ServicioORM) -> None:
    fila.empresa_id = servicio.empresa_id
    fila.nombre = servicio.nombre
    fila.precio = servicio.precio
    fila.alicuota_iva = servicio.alicuota_iva.tasa
    fila.agendable = servicio.agendable
    fila.duracion_estandar_min = servicio.duracion_estandar_min
    fila.origen = servicio.origen.value
    fila.presente_en_planilla = servicio.presente_en_planilla
    fila.activo = servicio.activo
    fila.created_at = servicio.creado_en
    fila.updated_at = servicio.actualizado_en


ConsultaDeServicio = Select[tuple[ServicioORM]]


def _filtrar_servicios(
    consulta: ConsultaDeServicio, filtros: FiltrosDeServicio
) -> ConsultaDeServicio:
    if filtros.texto:
        consulta = consulta.where(func.lower(ServicioORM.nombre).like(f"%{filtros.texto.lower()}%"))
    if filtros.agendable is not None:
        consulta = consulta.where(ServicioORM.agendable.is_(filtros.agendable))
    if filtros.solo_activos:
        consulta = consulta.where(ServicioORM.activo.is_(True))
    if filtros.categoria_id is not None:
        consulta = consulta.join(
            ServicioCategoriaORM, ServicioCategoriaORM.servicio_id == ServicioORM.id
        ).where(ServicioCategoriaORM.categoria_id == filtros.categoria_id)
    return consulta


class RepositorioServicioPostgres:
    """Implements `PortRepositorioServicio`.

    Shorter than the client one because there is nothing to translate: no unique index to
    catch, no external lookup to name. The company filter is the RLS policy, as always.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, servicio: Servicio) -> None:
        fila = ServicioORM(id=servicio.id)
        _volcar_servicio(servicio, fila)
        self._sesion.add(fila)
        await self._sesion.flush()

    async def guardar(self, servicio: Servicio) -> None:
        fila = await self._sesion.get(ServicioORM, servicio.id)
        if fila is None:
            await self.agregar(servicio)
            return
        _volcar_servicio(servicio, fila)
        await self._sesion.flush()

    async def buscar_por_id(self, servicio_id: UUID) -> Servicio | None:
        fila = await self._sesion.get(ServicioORM, servicio_id)
        return _servicio_a_dominio(fila) if fila is not None else None

    async def listar(
        self, *, empresa_id: EmpresaId, filtros: FiltrosDeServicio, pagina: Pagina
    ) -> tuple[Sequence[Servicio], int]:
        base = select(ServicioORM).where(ServicioORM.empresa_id == empresa_id)
        filtrada = _filtrar_servicios(base, filtros)
        total = await self._sesion.scalar(select(func.count()).select_from(filtrada.subquery()))
        filas = await self._sesion.scalars(
            filtrada.order_by(ServicioORM.nombre).limit(pagina.limite).offset(pagina.desplazamiento)
        )
        return [_servicio_a_dominio(fila) for fila in filas], int(total or 0)
