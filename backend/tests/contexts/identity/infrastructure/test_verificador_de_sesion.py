"""`VerificadorDeSesionPostgres` and its two time limits, without a database (cases 9 and 27).

The limits are scaled down (milliseconds instead of 3 s and 10 s) because what matters is the
*shape*: the short limit covers the user query and **not** taking the connection. A fake
session that sleeps stands in for each step, so the test is about which `await` sits under
which timeout and not about how fast a machine is.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.application.errors import MotivoDeRevocacion, SesionRevocada
from cheatsheet.contexts.identity.application.verificacion_de_sesion import IdentidadVigente
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.contexts.identity.infrastructure.consulta_de_sesion import (
    TIMEOUT_DE_CONSULTA_SEGUNDOS,
    VerificadorDeSesionPostgres,
)
from cheatsheet.platform.database import TIMEOUT_DE_CONEXION_SEGUNDOS
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

from tests.contexts.identity.base_falsa import EscenarioDeBase, fabrica_de_sesiones, fila

#: The scaled-down query limit, and a delay that is clearly beyond it but well under any
#: real limit.
LIMITE = 0.05
DEMORA = 0.15


def _verificador(escenario: EscenarioDeBase) -> VerificadorDeSesionPostgres:
    return VerificadorDeSesionPostgres(fabrica_de_sesiones(escenario), timeout_de_consulta=LIMITE)


@pytest.mark.asyncio
async def test_devuelve_el_rol_de_la_fila_y_entrega_la_conexion_antes_de_volver():
    """The connection is back with the pool by the time the caller sees the identity: the
    route runs afterwards and must not find the pool short of the connection the check held."""
    empresa_id = EmpresaId(uuid4())
    usuario_id = UsuarioId(uuid4())
    escenario = EscenarioDeBase(fila=fila(empresa_id))

    identidad = await _verificador(escenario).verificar(
        usuario_id=usuario_id, empresa_id_del_token=empresa_id
    )

    assert identidad == IdentidadVigente(
        empresa_id=empresa_id, usuario_id=usuario_id, rol=RolUsuario.OPERADOR
    )
    assert (escenario.abiertas, escenario.cerradas) == (0, 1)
    assert escenario.confirmaciones == 1


@pytest.mark.asyncio
async def test_la_sesion_se_abre_para_la_empresa_firmada_en_el_token():
    """Row-Level Security is scoped by the claim; the use case then compares the row to it."""
    empresa_id = EmpresaId(uuid4())
    escenario = EscenarioDeBase(fila=fila(empresa_id))

    await _verificador(escenario).verificar(
        usuario_id=UsuarioId(uuid4()), empresa_id_del_token=empresa_id
    )

    assert escenario.empresas_anunciadas == [str(empresa_id)]


@pytest.mark.asyncio
async def test_una_consulta_mas_lenta_que_el_limite_es_un_timeout_y_libera_la_conexion():
    """Case 9. Connection in hand, the query exceeds its limit: an error the middleware turns
    into a 503, with the transaction rolled back and the connection returned."""
    empresa_id = EmpresaId(uuid4())
    escenario = EscenarioDeBase(fila=fila(empresa_id), demora_de_consulta=DEMORA)

    with pytest.raises(TimeoutError):
        await _verificador(escenario).verificar(
            usuario_id=UsuarioId(uuid4()), empresa_id_del_token=empresa_id
        )

    assert escenario.reversiones == 1
    assert escenario.confirmaciones == 0
    assert (escenario.abiertas, escenario.cerradas) == (0, 1)


@pytest.mark.asyncio
async def test_una_toma_de_conexion_lenta_pero_dentro_de_su_limite_no_es_un_error():
    """Case 27. A database waking up takes longer than the query limit to hand over a
    connection. That wait is not under the short limit, so the request is verified."""
    empresa_id = EmpresaId(uuid4())
    escenario = EscenarioDeBase(fila=fila(empresa_id), demora_de_conexion=DEMORA)

    identidad = await _verificador(escenario).verificar(
        usuario_id=UsuarioId(uuid4()), empresa_id_del_token=empresa_id
    )

    assert identidad.rol is RolUsuario.OPERADOR
    assert escenario.confirmaciones == 1


@pytest.mark.asyncio
async def test_una_sesion_revocada_revierte_y_libera_la_conexion():
    empresa_id = EmpresaId(uuid4())
    escenario = EscenarioDeBase(fila=fila(empresa_id, estado="INACTIVO"))

    with pytest.raises(SesionRevocada) as error:
        await _verificador(escenario).verificar(
            usuario_id=UsuarioId(uuid4()), empresa_id_del_token=empresa_id
        )

    assert error.value.motivo is MotivoDeRevocacion.USUARIO_INACTIVO
    assert (escenario.abiertas, escenario.cerradas) == (0, 1)


def test_el_limite_de_la_consulta_es_mas_corto_que_el_de_la_conexion():
    """The invariant the module docstring depends on: if someone ever swaps these, the first
    request of the day on a suspended database is a 503 again."""
    assert TIMEOUT_DE_CONSULTA_SEGUNDOS == 3.0
    assert TIMEOUT_DE_CONSULTA_SEGUNDOS < TIMEOUT_DE_CONEXION_SEGUNDOS
