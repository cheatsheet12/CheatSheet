"""El contrato de `ClienteViaMasterData`: que significa `False`.

Se arma con los casos de uso publicados de `master_data` y su repositorio en memoria, no con su
dominio: R3 tambien rige para los tests de este contexto. La barrera de empresa de verdad (RLS)
se prueba contra PostgreSQL en `tests/integracion/`.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.master_data.application.clientes import (
    CambiarEstadoDeCliente,
    DatosDeCliente,
    RegistrarCliente,
)
from cheatsheet.contexts.payments.infrastructure.clientes import ClienteViaMasterData
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario

from tests.conftest import INSTANTE_FIJO
from tests.contexts.master_data.conftest import (
    PadronFalso,
    PublicadorFalso,
    RepositorioClienteEnMemoria,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
RELOJ = RelojFijo(INSTANTE_FIJO)


async def _registrar(repositorio: RepositorioClienteEnMemoria) -> UUID:
    vista = await RegistrarCliente(
        clientes=repositorio, padron=PadronFalso(), publicador=PublicadorFalso(), reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        datos=DatosDeCliente(nombre="Rosa Diaz"),
    )
    return vista.cliente.id


async def test_un_cliente_activo_esta_activo() -> None:
    repositorio = RepositorioClienteEnMemoria()
    cliente_id = await _registrar(repositorio)

    assert await ClienteViaMasterData(repositorio).esta_activo(cliente_id) is True


async def test_un_cliente_inactivo_no_esta_activo() -> None:
    repositorio = RepositorioClienteEnMemoria()
    cliente_id = await _registrar(repositorio)
    await CambiarEstadoDeCliente(
        clientes=repositorio, publicador=PublicadorFalso(), reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente_id,
        activo=False,
    )

    assert await ClienteViaMasterData(repositorio).esta_activo(cliente_id) is False


async def test_un_cliente_inexistente_no_esta_activo() -> None:
    assert await ClienteViaMasterData(RepositorioClienteEnMemoria()).esta_activo(uuid4()) is False
