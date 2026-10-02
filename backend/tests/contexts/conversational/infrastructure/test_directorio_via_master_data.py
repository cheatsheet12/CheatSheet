"""`DirectorioViaMasterData`: el alta rápida del agente pasa por la normalización (HU-E4-05).

El agente no normaliza nada por su cuenta: llama a `RegistrarCliente`, y la regla vive en el
agregado (RN-07). Este test fija que ese camino existe y que el nombre provisorio del agente,
«WhatsApp 1234», tiene mayúsculas mezcladas y por lo tanto se preserva.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.infrastructure.acl import DirectorioViaMasterData
from cheatsheet.contexts.master_data.domain.valores import OrigenDato
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId

from tests.conftest import INSTANTE_FIJO
from tests.contexts.master_data.conftest import (
    PadronFalso,
    PublicadorFalso,
    RepositorioClienteEnMemoria,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
TELEFONO = "5491112345678"


def _directorio(clientes: RepositorioClienteEnMemoria) -> DirectorioViaMasterData:
    return DirectorioViaMasterData(
        clientes,
        padron=PadronFalso(),
        publicador=PublicadorFalso(),
        reloj=RelojFijo(INSTANTE_FIJO),
        empresa_id=EMPRESA,
        usuario_id=None,
    )


async def test_el_alta_rapida_guarda_el_nombre_normalizado_con_origen_agente() -> None:
    clientes = RepositorioClienteEnMemoria()

    cliente_id = await _directorio(clientes).alta_rapida(telefono=TELEFONO, nombre="maria gomez")

    guardado = clientes.clientes[cliente_id]
    assert guardado.nombre == "Maria Gomez"
    assert guardado.origen is OrigenDato.AGENTE


async def test_el_nombre_provisorio_del_agente_se_preserva() -> None:
    clientes = RepositorioClienteEnMemoria()

    cliente_id = await _directorio(clientes).alta_rapida(telefono=TELEFONO, nombre="WhatsApp 1234")

    assert clientes.clientes[cliente_id].nombre == "WhatsApp 1234"
