"""ACL sobre `master_data`: servicios y clientes, en el vocabulario de `scheduling`.

Dos preguntas sobre un servicio —¿es agendable? ¿cuánto dura?— y una sobre un cliente —¿a qué
número le escribo?—. `scheduling` no ve el precio del servicio, ni su IVA, ni el CUIT del
cliente, ni su condición fiscal. La regla R3 lo obliga y el tamaño de este archivo lo hace
evidente.

**Nada de acá importa el dominio de `master_data`.** Se llaman sus servicios de aplicación y
sus puertos, y lo que devuelven se lee por atributo y se traduce a los DTO de este contexto,
que es lo mismo que hizo `SaldoViaBilling` en el épico 6. Que el objeto del otro lado sea un
`Servicio` es un detalle que este archivo deliberadamente no nombra.

**Lo que esta capa decide es qué significa `None`.** Un servicio inexistente, uno de otra
empresa y uno que no es agendable se colapsan a `None`: para un turno los tres significan lo
mismo, y distinguirlos no le daría a nadie una acción distinta.
"""

from __future__ import annotations

from uuid import UUID

from cheatsheet.contexts.master_data.application.ports import (
    PortRepositorioCliente,
    PortRepositorioServicio,
)
from cheatsheet.contexts.master_data.application.servicios import ListarServicios
from cheatsheet.contexts.scheduling.application.ports import ServicioAgendable
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.roles import RolUsuario


class CatalogoViaMasterData:
    """`PortCatalogoDeServicios`, respaldado por el repositorio publicado de `master_data`."""

    def __init__(
        self,
        servicios: PortRepositorioServicio,
        *,
        empresa_id: EmpresaId,
        rol: RolUsuario,
    ) -> None:
        self._servicios = servicios
        self._empresa_id = empresa_id
        # El rol viaja porque `ListarServicios` exige permiso de lectura, y este ACL actúa en
        # nombre de quien hizo el pedido — no con una identidad de servicio que saltearía el
        # control.
        self._rol = rol

    async def buscar_agendable(self, servicio_id: UUID) -> ServicioAgendable | None:
        servicio = await self._servicios.buscar_por_id(servicio_id)
        if servicio is None or not servicio.agendable:
            return None
        duracion = servicio.duracion_estandar_min
        if duracion is None:
            # `master_data` exige la duración para todo servicio agendable, así que esto no
            # debería pasar. Si pasara, tratarlo como no agendable es lo correcto: un turno sin
            # duración no tiene franja, y no hay nada que reservar.
            return None
        return ServicioAgendable(
            id=servicio.id, nombre=servicio.nombre, duracion_estandar_min=duracion
        )

    async def listar_agendables(self) -> list[ServicioAgendable]:
        listado = await ListarServicios(servicios=self._servicios).ejecutar(
            empresa_id=self._empresa_id, rol=self._rol
        )
        return [
            ServicioAgendable(
                id=uno.id, nombre=uno.nombre, duracion_estandar_min=uno.duracion_estandar_min
            )
            for uno in listado.servicios
            if uno.agendable and uno.activo and uno.duracion_estandar_min is not None
        ]


class ClientesViaMasterData:
    """`PortDirectorioDeClientes`. Devuelve `(nombre, teléfono)` o `None`.

    `None` **no es un error**: HU-E7-02 RN-03 dice «si tiene número registrado», así que un
    cliente sin WhatsApp es un camino previsto por la historia. Confundirlo con una falla haría
    que cancelar el turno de alguien sin teléfono fallara.
    """

    def __init__(self, clientes: PortRepositorioCliente, *, empresa_id: EmpresaId) -> None:
        self._clientes = clientes
        self._empresa_id = empresa_id

    async def contacto_de(self, cliente_id: UUID) -> tuple[str, str] | None:
        cliente = await self._clientes.buscar_por_id(cliente_id)
        if cliente is None or cliente.contacto_whatsapp is None:
            return None
        return cliente.nombre, str(cliente.contacto_whatsapp)


__all__ = ["CatalogoViaMasterData", "ClientesViaMasterData"]
