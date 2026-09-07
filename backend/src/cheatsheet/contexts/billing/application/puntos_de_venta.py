"""The use cases of HU-E5-05 — administering the points of sale a company invoices from.

**Only the Administrador**, and unlike the mapping of epic 4 that is not day-to-day work: a
point of sale is the fiscal numbering the company's documents carry. The guard sits in the
use case and not only in the router, for the reason `identity/application/autorizacion.py`
states and PRU-09 proved.

**RN-03 is checked against ARCA before a point can be activated**, and the two failure modes
are kept apart on purpose. «ARCA says this number is not yours» is a permanent no and blocks
the activation; «we could not ask ARCA» is worth trying again in a minute. Collapsing them
would either block a legitimate point during an outage or activate one ARCA never enabled —
and the second only shows up when the first invoice is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.billing.application.errors import (
    PuntoDeVentaInexistente,
    PuntoDeVentaNoHabilitado,
)
from cheatsheet.contexts.billing.application.ports import (
    PortHabilitacionDeArca,
    PortRepositorioPuntoDeVenta,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

#: HU-E5-05, word for word. A constant because the story writes it and a test asserts it.
MENSAJE_NO_HABILITADO = "El punto de venta no está habilitado en ARCA."
MENSAJE_DUPLICADO = "Ya existe un punto de venta con ese número."
MOTIVO_SOLO_ADMIN = "Solo un Administrador puede administrar los puntos de venta"


def _exigir_administrador(rol: RolUsuario) -> None:
    if rol is not RolUsuario.ADMINISTRADOR:
        raise EntradaInvalida(MOTIVO_SOLO_ADMIN)


@dataclass(frozen=True, slots=True)
class DatosDePuntoDeVenta:
    numero: int
    descripcion: str | None = None


class ListarPuntosDeVenta:
    """Every role reads. The listing of PAN-FAC-05 is a read like any other."""

    def __init__(self, puntos: PortRepositorioPuntoDeVenta) -> None:
        self._puntos = puntos

    async def ejecutar(self) -> list[PuntoDeVenta]:
        return await self._puntos.listar()


class RegistrarPuntoDeVenta:
    """Add a point of sale, **verified against ARCA before it can be used** (RN-03).

    The point is created active only if ARCA confirms it. Creating it inactive and letting
    somebody activate it later would be the same check in a different place; creating it
    active without asking would be a company discovering the problem when its first invoice
    is rejected with a code that talks about something else.
    """

    def __init__(
        self,
        *,
        puntos: PortRepositorioPuntoDeVenta,
        habilitacion: PortHabilitacionDeArca,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._puntos = puntos
        self._habilitacion = habilitacion
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        datos: DatosDePuntoDeVenta,
        ahora: datetime,
    ) -> PuntoDeVenta:
        _exigir_administrador(rol)

        habilitados = await self._habilitacion.puntos_habilitados(empresa_id=empresa_id)
        if not any(p.numero == datos.numero and p.puede_usarse for p in habilitados):
            raise PuntoDeVentaNoHabilitado(MENSAJE_NO_HABILITADO)

        punto = PuntoDeVenta(
            id=uuid4(),
            empresa_id=empresa_id,
            numero=datos.numero,
            descripcion=datos.descripcion,
            activo=True,
            created_at=ahora,
        )
        # The duplicate is caught by the unique index inside `agregar`, not by a read
        # first: a read-then-write loses to a second tab, and the number is the one thing
        # here that must not be duplicated.
        await self._puntos.agregar(punto)

        await self._publicar(
            punto, usuario_id=usuario_id, ahora=ahora, accion="alta_punto_de_venta"
        )
        return punto

    async def _publicar(
        self, punto: PuntoDeVenta, *, usuario_id: UsuarioId, ahora: datetime, accion: str
    ) -> None:
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=punto.empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.BILLING,
                accion=accion,
                entidad_afectada=f"PuntoDeVenta:{punto.id}",
                resultado=Resultado.COMPLETADO,
            )
        )


class CambiarEstadoDePuntoDeVenta:
    """RN-04 — deactivating stops new documents and keeps the ones already issued.

    Reactivating re-checks ARCA. A point can be blocked there after we recorded it, and
    letting somebody switch it back on from our own row would mean trusting a snapshot for
    a permission that lives at the AFIP.
    """

    def __init__(
        self,
        *,
        puntos: PortRepositorioPuntoDeVenta,
        habilitacion: PortHabilitacionDeArca,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._puntos = puntos
        self._habilitacion = habilitacion
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        punto_id: UUID,
        activo: bool,
        ahora: datetime,
    ) -> PuntoDeVenta:
        _exigir_administrador(rol)

        punto = await self._puntos.buscar_por_id(punto_id)
        if punto is None:
            raise PuntoDeVentaInexistente("El punto de venta no existe")

        if activo:
            habilitados = await self._habilitacion.puntos_habilitados(empresa_id=empresa_id)
            if not any(p.numero == punto.numero and p.puede_usarse for p in habilitados):
                raise PuntoDeVentaNoHabilitado(MENSAJE_NO_HABILITADO)
            punto.activar()
        else:
            # The counters survive. Reactivating must not restart the numbering: ARCA
            # remembers what it authorised even while we had the point switched off.
            punto.desactivar()

        await self._puntos.guardar(punto)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.BILLING,
                accion="activar_punto_de_venta" if activo else "desactivar_punto_de_venta",
                entidad_afectada=f"PuntoDeVenta:{punto.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return punto


__all__ = [
    "MENSAJE_DUPLICADO",
    "MENSAJE_NO_HABILITADO",
    "CambiarEstadoDePuntoDeVenta",
    "DatosDePuntoDeVenta",
    "ListarPuntosDeVenta",
    "RegistrarPuntoDeVenta",
]
