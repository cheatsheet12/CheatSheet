"""The per-request session check (HU-E1-05, HU-E1-06): cases 1 to 5 of the plan.

The token is a claim about the past. These tests pin down what the database says *now*
decides: the role, the status and the company.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
    VersionesEnVigor,
    versiones_en_vigor,
)
from cheatsheet.contexts.identity.domain.legal import CatalogoLegal, DocumentoLegal
from cheatsheet.contexts.identity.domain.valores import EstadoUsuario, RolUsuario
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import InvarianteViolada

from tests.conftest import INSTANTE_FIJO
from tests.contexts.identity.conftest import (
    VERSION_DE_PRIVACIDAD,
    VERSION_DE_TERMINOS,
    CatalogoLegalEnMemoria,
    ConsultaDeUsuarioVigenteEnMemoria,
    usuario_de_prueba,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def consulta() -> ConsultaDeUsuarioVigenteEnMemoria:
    return ConsultaDeUsuarioVigenteEnMemoria()


def _versiones() -> VersionesEnVigor:
    return versiones_en_vigor(
        CatalogoLegal(CatalogoLegalEnMemoria().versiones()), RelojFijo(INSTANTE_FIJO)
    )


class _Caso:
    """The use case with the versions in force already looked up, as its caller hands them."""

    def __init__(self, consulta: ConsultaDeUsuarioVigenteEnMemoria) -> None:
        self._caso = VerificarSesionVigente(consulta=consulta)

    async def ejecutar(
        self, *, usuario_id: UsuarioId, empresa_id_del_token: EmpresaId
    ) -> IdentidadVigente:
        return await self._caso.ejecutar(
            usuario_id=usuario_id, empresa_id_del_token=empresa_id_del_token, versiones=_versiones()
        )


def _caso(consulta: ConsultaDeUsuarioVigenteEnMemoria) -> _Caso:
    return _Caso(consulta)


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


# ------------------------------------------------------- HU-E1-03 RN-03, HU-E1-08 RN-05


async def test_un_usuario_al_dia_no_debe_ningun_documento(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    usuario = usuario_de_prueba(empresa_id)
    consulta.registrar(usuario)

    identidad = await _caso(consulta).ejecutar(
        usuario_id=usuario.id, empresa_id_del_token=empresa_id
    )

    assert identidad.pendientes == frozenset()


async def test_un_administrador_de_una_empresa_con_terminos_viejos_los_debe(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    usuario = usuario_de_prueba(empresa_id, rol=RolUsuario.ADMINISTRADOR)
    consulta.registrar(usuario, terminos="1.0")

    identidad = await _caso(consulta).ejecutar(
        usuario_id=usuario.id, empresa_id_del_token=empresa_id
    )

    assert identidad.pendientes == {DocumentoLegal.TERMINOS}


async def test_un_operador_no_se_bloquea_por_los_terminos_de_la_empresa(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    usuario = usuario_de_prueba(empresa_id, rol=RolUsuario.OPERADOR)
    consulta.registrar(usuario, terminos="1.0")

    identidad = await _caso(consulta).ejecutar(
        usuario_id=usuario.id, empresa_id_del_token=empresa_id
    )

    assert identidad.pendientes == frozenset()


async def test_quien_no_acepto_la_privacidad_vigente_la_debe(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    usuario = usuario_de_prueba(empresa_id, rol=RolUsuario.SOLO_LECTURA)
    consulta.registrar(usuario, privacidad_aceptada=())

    identidad = await _caso(consulta).ejecutar(
        usuario_id=usuario.id, empresa_id_del_token=empresa_id
    )

    assert identidad.pendientes == {DocumentoLegal.PRIVACIDAD}


async def test_la_consulta_recibe_la_version_vigente_de_hoy_y_no_la_futura(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    """The terms `2.0` of the test catalogue start in 2027: today's check must not ask for it."""
    usuario = usuario_de_prueba(empresa_id)
    consulta.registrar(usuario)

    await _caso(consulta).ejecutar(usuario_id=usuario.id, empresa_id_del_token=empresa_id)

    assert consulta.versiones_de_privacidad_pedidas == ["1.0"]
    assert consulta.consultas == 1


async def test_una_sesion_revocada_no_calcula_pendientes(
    consulta: ConsultaDeUsuarioVigenteEnMemoria, empresa_id: EmpresaId
):
    usuario = usuario_de_prueba(empresa_id, estado=EstadoUsuario.INACTIVO)
    consulta.registrar(usuario, terminos="1.0", privacidad_aceptada=())

    with pytest.raises(SesionRevocada):
        await _caso(consulta).ejecutar(usuario_id=usuario.id, empresa_id_del_token=empresa_id)


async def test_las_versiones_en_vigor_salen_del_catalogo_y_del_reloj():
    assert _versiones() == VersionesEnVigor(
        terminos=VERSION_DE_TERMINOS, privacidad=VERSION_DE_PRIVACIDAD
    )


async def test_sin_version_vigente_de_un_documento_no_hay_versiones_en_vigor():
    antes_de_todo = RelojFijo(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))

    with pytest.raises(InvarianteViolada):
        versiones_en_vigor(CatalogoLegal(CatalogoLegalEnMemoria().versiones()), antes_de_todo)
