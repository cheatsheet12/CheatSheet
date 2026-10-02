"""The four things a company does with its service catalogue (HU-E4-02).

List, create, edit, and take out of circulation — the same four as the customer
catalogue, and **no delete**, for the same two reasons: ADR-007, and the fact that
`comprobante` and `turno` reference a service by id.

What is different here is the money. These use cases never compute with it: they receive
a `Decimal`, hand it to the aggregate, which quantises and validates, and store what
comes back. The multiplication belongs to `billing`.

`origen` is set once, at creation, and no operation here takes it as input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.master_data.application.autorizacion import (
    exigir_escritura,
    exigir_lectura,
)
from cheatsheet.contexts.master_data.application.errors import ServicioNoEncontrado
from cheatsheet.contexts.master_data.application.ports import PortRepositorioServicio
from cheatsheet.contexts.master_data.domain.cliente import Pagina
from cheatsheet.contexts.master_data.domain.servicio import (
    FiltrosDeServicio,
    ListadoDeServicios,
    Servicio,
)
from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

ACCION_REGISTRADO = "servicio_registrado"
ACCION_EDITADO = "servicio_editado"
ACCION_DESACTIVADO = "servicio_desactivado"
ACCION_REACTIVADO = "servicio_reactivado"


@dataclass(frozen=True, slots=True)
class DatosDeServicio:
    """What PAN-DM-02's form sends.

    `precio` arrives as a `Decimal` already — the router builds it from the string the
    browser sent, so no float ever exists along the way. `duracion_estandar_min` may be
    `None` and the aggregate decides whether that is allowed, which depends on `agendable`.
    """

    nombre: str
    precio: Decimal
    alicuota_iva: AlicuotaIVA
    agendable: bool = False
    duracion_estandar_min: int | None = None


async def _auditar(
    publicador: PublicadorDeEventos,
    *,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId | None,
    ahora: datetime,
    accion: str,
    servicio_id: UUID,
    direccion_ip: str | None,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            ocurrido_en=ahora,
            modulo=Modulo.MASTER_DATA,
            accion=accion,
            entidad_afectada=f"servicio:{servicio_id}",
            resultado=Resultado.COMPLETADO,
            usuario_id=usuario_id,
            direccion_ip=direccion_ip,
        )
    )


class ListarServicios:
    """The catalogue of PAN-DM-02: name, price, VAT, duration and status."""

    def __init__(self, *, servicios: PortRepositorioServicio) -> None:
        self._servicios = servicios

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        rol: RolUsuario,
        filtros: FiltrosDeServicio | None = None,
        pagina: Pagina | None = None,
    ) -> ListadoDeServicios:
        exigir_lectura(rol)
        encontrados, total = await self._servicios.listar(
            empresa_id=empresa_id,
            filtros=filtros or FiltrosDeServicio(),
            pagina=pagina or Pagina(),
        )
        return ListadoDeServicios(servicios=tuple(encontrados), total=total)


class RegistrarServicio:
    """Create a service from the panel.

    «Queda disponible para el agente y para nuevos comprobantes» is the acceptance
    criterion, and it is satisfied by there being nowhere else to look: epic 5 and epic 8
    read this table.
    """

    def __init__(
        self,
        *,
        servicios: PortRepositorioServicio,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._servicios = servicios
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        datos: DatosDeServicio,
        direccion_ip: str | None = None,
    ) -> Servicio:
        exigir_escritura(rol)
        ahora = self._reloj.ahora()
        servicio = Servicio.registrar(
            id=uuid4(),
            empresa_id=empresa_id,
            nombre=datos.nombre,
            precio=datos.precio,
            alicuota_iva=datos.alicuota_iva,
            origen=OrigenDato.PANEL,
            momento=ahora,
            agendable=datos.agendable,
            duracion_estandar_min=datos.duracion_estandar_min,
        )
        await self._servicios.agregar(servicio)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=ahora,
            accion=ACCION_REGISTRADO,
            servicio_id=servicio.id,
            direccion_ip=direccion_ip,
        )
        return servicio


class EditarServicio:
    """Change a service's data. `origen` is not among the things that can change."""

    def __init__(
        self,
        *,
        servicios: PortRepositorioServicio,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._servicios = servicios
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        servicio_id: UUID,
        datos: DatosDeServicio,
        direccion_ip: str | None = None,
    ) -> Servicio:
        """Every field goes through the aggregate's own operation, none through a setter.

        Which is why turning a service non-bookable here is a single call that also drops
        the duration: the rule about the pair lives in one place.
        """
        exigir_escritura(rol)
        servicio = await self._servicios.buscar_por_id(servicio_id)
        if servicio is None:
            raise ServicioNoEncontrado(f"No existe el servicio {servicio_id}")
        ahora = self._reloj.ahora()
        servicio.renombrar(datos.nombre, ahora)
        servicio.cambiar_precio(datos.precio, ahora)
        servicio.cambiar_alicuota(datos.alicuota_iva, ahora)
        if datos.agendable:
            servicio.volver_agendable(_duracion_pedida(datos), ahora)
        else:
            servicio.dejar_de_ser_agendable(ahora)
        await self._servicios.guardar(servicio)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=ahora,
            accion=ACCION_EDITADO,
            servicio_id=servicio.id,
            direccion_ip=direccion_ip,
        )
        return servicio


def _duracion_pedida(datos: DatosDeServicio) -> int | None:
    """`volver_agendable` takes whatever the form sent, including nothing.

    The value is passed through untouched -- `None` included -- so the aggregate decides
    which of its two messages applies: «obligatoria» for an empty duration, the 5-to-480
    range message for anything typed. This function invents neither. (It used to map
    `None` to `0`, which was fine while `0` meant «obligatoria»; now `0` is out of range.)
    """
    return datos.duracion_estandar_min


class CambiarEstadoDeServicio:
    """RN-04: hides it from the active catalogue, touches no history."""

    def __init__(
        self,
        *,
        servicios: PortRepositorioServicio,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
    ) -> None:
        self._servicios = servicios
        self._publicador = publicador
        self._reloj = reloj

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        servicio_id: UUID,
        activo: bool,
        direccion_ip: str | None = None,
    ) -> Servicio:
        exigir_escritura(rol)
        servicio = await self._servicios.buscar_por_id(servicio_id)
        if servicio is None:
            raise ServicioNoEncontrado(f"No existe el servicio {servicio_id}")
        ahora = self._reloj.ahora()
        if activo:
            servicio.reactivar(ahora)
        else:
            servicio.desactivar(ahora)
        await self._servicios.guardar(servicio)
        await _auditar(
            self._publicador,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ahora=ahora,
            accion=ACCION_REACTIVADO if activo else ACCION_DESACTIVADO,
            servicio_id=servicio.id,
            direccion_ip=direccion_ip,
        )
        return servicio
