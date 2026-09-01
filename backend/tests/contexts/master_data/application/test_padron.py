"""El botón «Validar contra ARCA» del formulario de cliente.

Un caso de uso que no escribe nada y cuyo único trabajo es no mentir sobre cuál de las
tres respuestas dio el padrón.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.master_data.application.errors import PermisoDenegado
from cheatsheet.contexts.master_data.application.padron import (
    ConsultarPadronParaCliente,
    EstadoDeConsulta,
    VistaDePadron,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.master_data.conftest import (
    CUIT_VALIDO,
    PadronFalso,
    padron_sin_conectar,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())


async def _consultar(
    padron: PadronFalso, *, cuit: str = CUIT_VALIDO, rol: RolUsuario = RolUsuario.OPERADOR
) -> VistaDePadron:
    return await ConsultarPadronParaCliente(padron=padron).ejecutar(
        empresa_id=EMPRESA, cuit=cuit, rol=rol
    )


async def test_encontrado_devuelve_los_datos(padron: PadronFalso) -> None:
    vista = await _consultar(padron)

    assert vista.estado is EstadoDeConsulta.ENCONTRADO
    assert vista.datos is not None


async def test_no_encontrado_no_trae_datos_ni_motivo() -> None:
    vista = await _consultar(PadronFalso(datos=None))

    assert vista.estado is EstadoDeConsulta.NO_ENCONTRADO
    assert vista.datos is None
    assert vista.motivo is None


async def test_no_disponible_trae_el_motivo_y_no_los_datos() -> None:
    """Lo que la pantalla convierte en «no se pudo validar contra ARCA»."""
    vista = await _consultar(padron_sin_conectar())

    assert vista.estado is EstadoDeConsulta.NO_DISPONIBLE
    assert vista.motivo == "La empresa no tiene ARCA conectada"


async def test_un_cuit_mal_formado_no_gasta_una_consulta(padron: PadronFalso) -> None:
    with pytest.raises(EntradaInvalida):
        await _consultar(padron, cuit="123")

    assert padron.llamadas == 0


async def test_solo_lectura_puede_consultar(padron: PadronFalso) -> None:
    """No escribe nada, y la respuesta es sobre un número: alcanza con permiso de lectura."""
    vista = await _consultar(padron, rol=RolUsuario.SOLO_LECTURA)

    assert vista.estado is EstadoDeConsulta.ENCONTRADO


async def test_un_rol_desconocido_no_pasa(padron: PadronFalso) -> None:
    """`exigir_lectura` es una lista blanca, no una lista negra."""

    class RolInventado:
        pass

    with pytest.raises(PermisoDenegado):
        await ConsultarPadronParaCliente(padron=padron).ejecutar(
            empresa_id=EMPRESA,
            cuit=CUIT_VALIDO,
            rol=RolInventado(),  # type: ignore[arg-type]  # a propósito: no es un RolUsuario
        )
