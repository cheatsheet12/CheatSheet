"""Dobles en memoria para los puertos de `master_data`.

Escritos a mano y no con `unittest.mock`, por la razón que da `tests/conftest.py`: un
`Mock` satisface cualquier interfaz, incluida una que ya no existe. Estos implementan los
`Protocol` de verdad, así que el día que un puerto cambie fallan al tipar en vez de
seguir de acuerdo con algo que se fue.

`RepositorioClienteEnMemoria` reproduce **el único comportamiento del adaptador real que
le importa al caso de uso**: que un CUIT repetido dentro de la misma empresa levante
`ClienteDuplicado` con el id del que ya estaba. Lo demás —RLS, índice parcial, orden— se
prueba contra PostgreSQL de verdad en `tests/integracion/`, porque ninguna de esas tres
cosas se puede fingir.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import pytest
from cheatsheet.contexts.master_data.application.errors import ClienteDuplicado
from cheatsheet.contexts.master_data.application.ports import (
    DatosFiscalesDePadron,
    PadronNoDisponible,
)
from cheatsheet.contexts.master_data.domain.cliente import Cliente, FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.servicio import FiltrosDeServicio, Servicio
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.fiscal import CondicionIVA

#: Un CUIT estructuralmente válido: 30-71234567-1, dígito verificador con los pesos de ARCA.
CUIT_VALIDO = "30712345671"
#: El mismo número con el último dígito cambiado.
CUIT_DIGITO_MALO = "30712345670"
#: Otro CUIT válido: 20-12345678-6.
OTRO_CUIT_VALIDO = "20123456786"

DEL_PADRON = DatosFiscalesDePadron(
    razon_social="PANADERIA DONA ROSA SRL",
    condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
    activo=True,
)


class RepositorioClienteEnMemoria:
    """Implementa `PortRepositorioCliente`."""

    def __init__(self) -> None:
        self.clientes: dict[UUID, Cliente] = {}

    async def agregar(self, cliente: Cliente) -> None:
        self._exigir_cuit_libre(cliente)
        self.clientes[cliente.id] = cliente

    async def guardar(self, cliente: Cliente) -> None:
        self._exigir_cuit_libre(cliente)
        self.clientes[cliente.id] = cliente

    def _exigir_cuit_libre(self, cliente: Cliente) -> None:
        if cliente.cuit is None:
            return
        for otro in self.clientes.values():
            mismo_cuit = otro.cuit is not None and otro.cuit.valor == cliente.cuit.valor
            if mismo_cuit and otro.id != cliente.id and otro.empresa_id == cliente.empresa_id:
                raise ClienteDuplicado(
                    "Ya existe un cliente con ese CUIT.", cliente_existente_id=otro.id
                )

    async def buscar_por_id(self, cliente_id: UUID) -> Cliente | None:
        return self.clientes.get(cliente_id)

    async def buscar_por_cuit(self, cuit: str) -> Cliente | None:
        return next(
            (c for c in self.clientes.values() if c.cuit is not None and c.cuit.valor == cuit),
            None,
        )

    async def listar(
        self, *, empresa_id: EmpresaId, filtros: FiltrosDeCliente, pagina: Pagina
    ) -> tuple[Sequence[Cliente], int]:
        encontrados = [c for c in self.clientes.values() if c.empresa_id == empresa_id]
        if filtros.texto:
            texto = filtros.texto.lower()
            encontrados = [
                c
                for c in encontrados
                if texto in c.nombre.lower() or (c.cuit is not None and texto in c.cuit.valor)
            ]
        if filtros.origen is not None:
            encontrados = [c for c in encontrados if c.origen is filtros.origen]
        if filtros.solo_activos:
            encontrados = [c for c in encontrados if c.activo]
        encontrados.sort(key=lambda c: c.nombre)
        recorte = encontrados[pagina.desplazamiento : pagina.desplazamiento + pagina.limite]
        return recorte, len(encontrados)


class PadronFalso:
    """Implementa `PortPadron`. Tres desenlaces, que es todo el vocabulario del puerto."""

    def __init__(
        self,
        *,
        datos: DatosFiscalesDePadron | None = DEL_PADRON,
        excepcion: Exception | None = None,
    ) -> None:
        self.datos = datos
        self.excepcion = excepcion
        self.llamadas = 0
        self.ultimo_cuit: str | None = None

    async def consultar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosFiscalesDePadron | None:
        del empresa_id
        self.llamadas += 1
        self.ultimo_cuit = cuit
        if self.excepcion is not None:
            raise self.excepcion
        return self.datos


def padron_sin_conectar() -> PadronFalso:
    """El caso normal de una empresa que nunca configuró ARCA: no se pudo preguntar."""
    return PadronFalso(excepcion=PadronNoDisponible("La empresa no tiene ARCA conectada"))


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


@pytest.fixture
def clientes() -> RepositorioClienteEnMemoria:
    return RepositorioClienteEnMemoria()


@pytest.fixture
def padron() -> PadronFalso:
    return PadronFalso()


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


class RepositorioServicioEnMemoria:
    """Implementa `PortRepositorioServicio`.

    Más simple que el de clientes porque el puerto lo es: no hay unicidad que reproducir.
    """

    def __init__(self) -> None:
        self.servicios: dict[UUID, Servicio] = {}

    async def agregar(self, servicio: Servicio) -> None:
        self.servicios[servicio.id] = servicio

    async def guardar(self, servicio: Servicio) -> None:
        self.servicios[servicio.id] = servicio

    async def buscar_por_id(self, servicio_id: UUID) -> Servicio | None:
        return self.servicios.get(servicio_id)

    async def listar(
        self, *, empresa_id: EmpresaId, filtros: FiltrosDeServicio, pagina: Pagina
    ) -> tuple[Sequence[Servicio], int]:
        encontrados = [s for s in self.servicios.values() if s.empresa_id == empresa_id]
        if filtros.texto:
            texto = filtros.texto.lower()
            encontrados = [s for s in encontrados if texto in s.nombre.lower()]
        if filtros.agendable is not None:
            encontrados = [s for s in encontrados if s.agendable is filtros.agendable]
        if filtros.solo_activos:
            encontrados = [s for s in encontrados if s.activo]
        encontrados.sort(key=lambda s: s.nombre)
        recorte = encontrados[pagina.desplazamiento : pagina.desplazamiento + pagina.limite]
        return recorte, len(encontrados)


@pytest.fixture
def servicios() -> RepositorioServicioEnMemoria:
    return RepositorioServicioEnMemoria()
