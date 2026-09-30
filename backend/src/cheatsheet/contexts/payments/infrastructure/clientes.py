"""ACL sobre `master_data`: un cliente, en el vocabulario de `payments`.

Una sola pregunta: ¿hay a quien cobrarle? `payments` no ve el CUIT, el contacto ni la condicion
fiscal del cliente. Es el mismo esquema que `scheduling/infrastructure/catalogo.py`: se usa el
puerto publicado en la capa de aplicacion de `master_data` y nada de su dominio (R3).

**Lo que esta capa decide es que significa `False`.** Un cliente inexistente, uno de otra
empresa y uno inactivo se colapsan: bajo RLS los dos primeros son la misma respuesta, y para un
cobro los tres significan lo mismo. Distinguirlos le diria a una empresa que un id ajeno es real.
"""

from __future__ import annotations

from uuid import UUID

from cheatsheet.contexts.master_data.application.ports import PortRepositorioCliente


class ClienteViaMasterData:
    """`PortClienteDeCobro`, respaldado por el repositorio publicado de `master_data`."""

    def __init__(self, clientes: PortRepositorioCliente) -> None:
        self._clientes = clientes

    async def esta_activo(self, cliente_id: UUID) -> bool:
        cliente = await self._clientes.buscar_por_id(cliente_id)
        return cliente is not None and cliente.activo


__all__ = ["ClienteViaMasterData"]
