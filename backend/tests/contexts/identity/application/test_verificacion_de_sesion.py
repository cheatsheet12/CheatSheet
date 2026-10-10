"""The per-request session check (HU-E1-05, HU-E1-06): cases 1 to 5 of the plan.

The token is a claim about the past. These tests pin down what the database says *now*
decides: the role, the status and the company.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.application.errors import (
    MotivoDeRevocacion,
    SesionInvalida,
    SesionRevocada,
)
from cheatsheet.contexts.identity.application.verificacion_de_sesion import (
    IdentidadVigente,
    VerificarSesionVigente,
)
from cheatsheet.contexts.identity.domain.valores import EstadoUsuario, RolUsuario
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

from tests.contexts.identity.conftest import ConsultaDeUsuarioVigenteEnMemoria, usuario_de_prueba

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consulta() -> ConsultaDeUsuarioVigenteEnMemoria:
    return ConsultaDeUsuarioVigenteEnMemoria()


def _caso(consulta: ConsultaDeUsuarioVigenteEnMemoria) -> VerificarSesionVigente:
    return VerificarSesionVigente(consulta=consulta)


async def test_un_usuario_activo_opera_con_el_rol_de_la_base_y_no_el_del_token(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    """Case 1. The token said ADMINISTRADOR when it was issued; the row says OPERADOR now."""
    usuario = usuario_de_prueba(empresa_id, rol=RolUsuario.OPERADOR)
    consulta.registrar(usuario)

    identidad = await _caso(consulta).ejecutar(
        usuario_id=usuario.id, empresa_id_del_token=empresa_id
    )

    assert identidad == IdentidadVigente(
        empresa_id=empresa_id, usuario_id=usuario.id, rol=RolUsuario.OPERADOR
    )


async def test_un_usuario_inactivo_deja_de_operar(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    """Case 2 (HU-E1-06): the next request after a deactivation is refused."""
    usuario = usuario_de_prueba(empresa_id, estado=EstadoUsuario.INACTIVO)
    consulta.registrar(usuario)

    with pytest.raises(SesionRevocada) as error:
        await _caso(consulta).ejecutar(usuario_id=usuario.id, empresa_id_del_token=empresa_id)

    assert error.value.motivo is MotivoDeRevocacion.USUARIO_INACTIVO


async def test_un_usuario_invitado_no_opera_con_un_token(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    """Case 3. Only `ACTIVO` operates: somebody who has not accepted yet is not a member."""
    usuario = usuario_de_prueba(empresa_id, estado=EstadoUsuario.INVITADO)
    consulta.registrar(usuario)

    with pytest.raises(SesionRevocada) as error:
        await _caso(consulta).ejecutar(usuario_id=usuario.id, empresa_id_del_token=empresa_id)

    assert error.value.motivo is MotivoDeRevocacion.USUARIO_INACTIVO


async def test_sin_fila_la_sesion_esta_revocada(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    """Case 4: deleted, or hidden by Row-Level Security because it is another company's."""
    with pytest.raises(SesionRevocada) as error:
        await _caso(consulta).ejecutar(
            usuario_id=UsuarioId(uuid4()), empresa_id_del_token=empresa_id
        )

    assert error.value.motivo is MotivoDeRevocacion.USUARIO_INEXISTENTE


async def test_la_fila_de_otra_empresa_que_la_del_token_revoca_la_sesion(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    """Case 5. If the stored company and the claimed one disagree, neither is trusted."""
    usuario = usuario_de_prueba(empresa_id)
    consulta.registrar(usuario)

    with pytest.raises(SesionRevocada) as error:
        await _caso(consulta).ejecutar(
            usuario_id=usuario.id, empresa_id_del_token=EmpresaId(uuid4())
        )

    assert error.value.motivo is MotivoDeRevocacion.EMPRESA_NO_COINCIDE


async def test_una_sesion_revocada_es_una_sesion_invalida(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    """Anything that already handles `SesionInvalida` handles this one too."""
    with pytest.raises(SesionInvalida):
        await _caso(consulta).ejecutar(
            usuario_id=UsuarioId(uuid4()), empresa_id_del_token=empresa_id
        )
