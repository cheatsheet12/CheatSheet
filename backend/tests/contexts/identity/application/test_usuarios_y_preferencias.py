"""The user administration and preference use cases (HU-E1-04 … HU-E1-07).

Cases 6 to 25 of the `usuarios-y-preferencias` plan. Everything runs on the in-memory
doubles of `conftest.py`: no database, no mail server, no network.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.application.errors import (
    EmailYaRegistrado,
    InvitacionInvalida,
    PermisoDenegado,
    UltimoAdministradorActivo,
)
from cheatsheet.contexts.identity.application.invitaciones import (
    AceptarInvitacion,
    InvitacionEmitida,
    InvitarUsuario,
    ReenviarInvitacion,
    RevocarInvitacion,
)
from cheatsheet.contexts.identity.application.preferencias import (
    ActualizarPreferencias,
    VerPreferencias,
)
from cheatsheet.contexts.identity.application.usuarios import (
    CambiarRolDeUsuario,
    DesactivarUsuario,
    ListarUsuarios,
    ReactivarUsuario,
)
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import NOMBRE_PENDIENTE, Usuario
from cheatsheet.contexts.identity.domain.valores import (
    CanalDeNotificacion,
    CategoriaDeNotificacion,
    Email,
    EstadoUsuario,
    PreferenciasDeNotificacion,
    RolUsuario,
)
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida

from tests.conftest import INSTANTE_FIJO
from tests.contexts.identity.conftest import CONTRASENA, usuario_de_prueba

pytestmark = pytest.mark.asyncio

VIDA = timedelta(days=7)


def _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador) -> InvitarUsuario:
    return InvitarUsuario(
        usuarios=usuarios,
        invitaciones=invitaciones,
        tokens=tokens_de_invitacion,
        publicador=publicador,
        vida_invitacion=VIDA,
    )


def _reenviar(usuarios, invitaciones, tokens_de_invitacion, publicador) -> ReenviarInvitacion:
    return ReenviarInvitacion(
        usuarios=usuarios,
        invitaciones=invitaciones,
        tokens=tokens_de_invitacion,
        publicador=publicador,
        vida_invitacion=VIDA,
    )


def _cambiar_rol(empresas, usuarios, publicador) -> CambiarRolDeUsuario:
    return CambiarRolDeUsuario(empresas=empresas, usuarios=usuarios, publicador=publicador)


def _desactivar(empresas, usuarios, refrescos, publicador) -> DesactivarUsuario:
    return DesactivarUsuario(
        empresas=empresas, usuarios=usuarios, refrescos=refrescos, publicador=publicador
    )


async def _admin(usuarios, empresa_id: EmpresaId) -> Usuario:
    admin = usuario_de_prueba(empresa_id, email="admin@empresa.com")
    await usuarios.agregar(admin)
    return admin


# ------------------------------------------------------------------ invitar (casos 6-9)


async def test_invitar_crea_al_usuario_en_invitado_y_sin_contrasena(
    usuarios, invitaciones, tokens_de_invitacion, publicador
):
    """Caso 8. Inventing a password would be inventing a credential nobody picked."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)

    emitida = await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        email=Email("nuevo@empresa.com"),
        rol=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )

    assert emitida.usuario.estado is EstadoUsuario.INVITADO
    assert emitida.usuario.hash_de_contrasena is None
    assert emitida.usuario.nombre == NOMBRE_PENDIENTE
    assert emitida.invitacion.expira_en == INSTANTE_FIJO + VIDA


async def test_el_token_de_invitacion_solo_se_guarda_hasheado(
    usuarios, invitaciones, tokens_de_invitacion, publicador
):
    """The clear-text token exists once, in memory, in the request that created it."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)

    emitida = await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        email=Email("nuevo@empresa.com"),
        rol=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )

    assert emitida.token_en_claro
    assert emitida.invitacion.hash_del_token != emitida.token_en_claro
    # The double's digest is reversible on purpose; that the *real* one is not is
    # checked in `infrastructure/test_tokens_invitacion.py`.
    assert await invitaciones.buscar_por_hash(emitida.token_en_claro) is None


async def test_invitar_un_email_que_ya_existe_en_la_empresa_se_rechaza(
    usuarios, invitaciones, tokens_de_invitacion, publicador
):
    """Caso 6 — HU-E1-04 RN-03."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)

    with pytest.raises(EmailYaRegistrado):
        await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=admin.id,
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            email=admin.email,
            rol=RolUsuario.OPERADOR,
            ahora=INSTANTE_FIJO,
        )


async def test_invitar_un_email_de_otra_empresa_tambien_se_rechaza(
    usuarios, invitaciones, tokens_de_invitacion, publicador
):
    """Caso 7. The column is unique platform-wide, so the check has to be global or the
    INSERT fails later with a constraint error nobody can act on."""
    otra_empresa = EmpresaId(uuid4())
    await usuarios.agregar(usuario_de_prueba(otra_empresa, email="ocupado@otra.com"))
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)

    with pytest.raises(EmailYaRegistrado):
        await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=admin.id,
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            email=Email("ocupado@otra.com"),
            rol=RolUsuario.OPERADOR,
            ahora=INSTANTE_FIJO,
        )


@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
async def test_quien_no_es_administrador_no_puede_invitar(
    usuarios, invitaciones, tokens_de_invitacion, publicador, rol: RolUsuario
):
    """Caso 9. The router hides the button; this is what actually refuses."""
    empresa_id = EmpresaId(uuid4())

    with pytest.raises(PermisoDenegado):
        await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=UsuarioId(uuid4()),
            rol_del_ejecutor=rol,
            email=Email("nuevo@empresa.com"),
            rol=RolUsuario.OPERADOR,
            ahora=INSTANTE_FIJO,
        )


# ------------------------------------------------------- reenviar y revocar (casos 11-13)


async def test_reenviar_invalida_el_token_anterior(
    usuarios, invitaciones, tokens_de_invitacion, publicador
):
    """Caso 11. Resending must not leave two live keys to the same door."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    primera = await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        email=Email("nuevo@empresa.com"),
        rol=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )

    segunda = await _reenviar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        invitacion_id=primera.invitacion.id,
        ahora=INSTANTE_FIJO,
    )

    assert segunda.token_en_claro != primera.token_en_claro
    viejo = tokens_de_invitacion.hashear(primera.token_en_claro)
    assert await invitaciones.buscar_por_hash(viejo) is None


async def test_revocar_libera_el_email_para_volver_a_invitar(
    usuarios, invitaciones, tokens_de_invitacion, publicador
):
    """Caso 12 — the reason the user row is deleted and not deactivated."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    emitida = await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        email=Email("nuevo@empresa.com"),
        rol=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )

    await RevocarInvitacion(
        usuarios=usuarios, invitaciones=invitaciones, publicador=publicador
    ).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        invitacion_id=emitida.invitacion.id,
        ahora=INSTANTE_FIJO,
    )

    assert await usuarios.buscar_por_email(Email("nuevo@empresa.com")) is None
    # And inviting the same person again now works.
    await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        email=Email("nuevo@empresa.com"),
        rol=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )


async def test_una_invitacion_ya_aceptada_no_se_reenvia_ni_se_revoca(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
):
    """Caso 13 — HU-E1-04 RN-04."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    emitida = await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        email=Email("nuevo@empresa.com"),
        rol=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )
    await AceptarInvitacion(
        usuarios=usuarios,
        invitaciones=invitaciones,
        tokens=tokens_de_invitacion,
        hasher=hasher,
        emisor=emisor,
        publicador=publicador,
    ).ejecutar(
        token=emitida.token_en_claro,
        nombre="Ana Perez",
        contrasena=CONTRASENA,
        ahora=INSTANTE_FIJO,
    )

    from cheatsheet.shared.errors import InvarianteViolada

    with pytest.raises(InvarianteViolada):
        await _reenviar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=admin.id,
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            invitacion_id=emitida.invitacion.id,
            ahora=INSTANTE_FIJO,
        )
    with pytest.raises(InvarianteViolada):
        await RevocarInvitacion(
            usuarios=usuarios, invitaciones=invitaciones, publicador=publicador
        ).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=admin.id,
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            invitacion_id=emitida.invitacion.id,
            ahora=INSTANTE_FIJO,
        )


async def test_una_invitacion_de_otra_empresa_no_existe(usuarios, invitaciones, publicador):
    """Row-Level Security is what makes this true in production; the repository double
    reproduces the same answer."""
    with pytest.raises(EntradaInvalida):
        await RevocarInvitacion(
            usuarios=usuarios, invitaciones=invitaciones, publicador=publicador
        ).ejecutar(
            empresa_id=EmpresaId(uuid4()),
            ejecutor_id=UsuarioId(uuid4()),
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            invitacion_id=uuid4(),
            ahora=INSTANTE_FIJO,
        )


# ----------------------------------------------------------------- aceptar (casos 14-17)


async def _emitir_invitacion(
    usuarios, invitaciones, tokens_de_invitacion, publicador
) -> InvitacionEmitida:
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    return await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        email=Email("nuevo@empresa.com"),
        rol=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )


def _aceptar(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
) -> AceptarInvitacion:
    return AceptarInvitacion(
        usuarios=usuarios,
        invitaciones=invitaciones,
        tokens=tokens_de_invitacion,
        hasher=hasher,
        emisor=emisor,
        publicador=publicador,
    )


async def test_aceptar_fija_la_contrasena_activa_la_cuenta_y_devuelve_sesion(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
):
    """Caso 14. Accepting is what turns an invitation into an account."""
    emitida = await _emitir_invitacion(usuarios, invitaciones, tokens_de_invitacion, publicador)

    sesion = await _aceptar(
        usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
    ).ejecutar(
        token=emitida.token_en_claro,
        nombre="Ana Perez",
        contrasena=CONTRASENA,
        ahora=INSTANTE_FIJO,
    )

    usuario = await usuarios.buscar_por_id(emitida.usuario.id)
    assert usuario is not None
    assert usuario.estado is EstadoUsuario.ACTIVO
    assert usuario.nombre == "Ana Perez"
    assert hasher.verificar(CONTRASENA, usuario.hash_de_contrasena)
    assert sesion.access_token
    assert sesion.refresh_token


async def test_el_mismo_token_no_sirve_dos_veces(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
):
    """Caso 15."""
    emitida = await _emitir_invitacion(usuarios, invitaciones, tokens_de_invitacion, publicador)
    servicio = _aceptar(usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador)
    await servicio.ejecutar(
        token=emitida.token_en_claro,
        nombre="Ana Perez",
        contrasena=CONTRASENA,
        ahora=INSTANTE_FIJO,
    )

    with pytest.raises(InvitacionInvalida):
        await servicio.ejecutar(
            token=emitida.token_en_claro,
            nombre="Otra",
            contrasena=CONTRASENA,
            ahora=INSTANTE_FIJO,
        )


async def test_un_token_vencido_se_rechaza(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
):
    """Caso 16."""
    emitida = await _emitir_invitacion(usuarios, invitaciones, tokens_de_invitacion, publicador)

    with pytest.raises(InvitacionInvalida):
        await _aceptar(
            usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
        ).ejecutar(
            token=emitida.token_en_claro,
            nombre="Ana Perez",
            contrasena=CONTRASENA,
            ahora=INSTANTE_FIJO + VIDA + timedelta(seconds=1),
        )


async def test_un_token_inventado_se_rechaza_igual_que_uno_vencido(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
):
    """One error for every rejection: whoever holds a token that is not theirs learns
    only that it does not work."""
    with pytest.raises(InvitacionInvalida):
        await _aceptar(
            usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
        ).ejecutar(
            token="no-existe",
            nombre="Ana Perez",
            contrasena=CONTRASENA,
            ahora=INSTANTE_FIJO,
        )


async def test_aceptar_con_una_contrasena_corta_se_rechaza(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
):
    """Caso 17 — the same 8-character minimum as signing up."""
    emitida = await _emitir_invitacion(usuarios, invitaciones, tokens_de_invitacion, publicador)

    with pytest.raises(EntradaInvalida):
        await _aceptar(
            usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador
        ).ejecutar(
            token=emitida.token_en_claro,
            nombre="Ana Perez",
            contrasena="corta",
            ahora=INSTANTE_FIJO,
        )


# ------------------------------------------------- el ultimo administrador (casos 18-21)


async def test_no_se_le_puede_quitar_el_rol_al_unico_administrador_activo(
    empresas, usuarios, publicador
):
    """Caso 18 — HU-E1-05 RN-02."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)

    with pytest.raises(UltimoAdministradorActivo):
        await _cambiar_rol(empresas, usuarios, publicador).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=admin.id,
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            usuario_id=admin.id,
            rol_nuevo=RolUsuario.OPERADOR,
            ahora=INSTANTE_FIJO,
        )
    assert admin.rol is RolUsuario.ADMINISTRADOR


async def test_no_se_puede_desactivar_al_unico_administrador_activo(
    empresas, usuarios, refrescos, publicador
):
    """Caso 19 — HU-E1-06 RN-03."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)

    with pytest.raises(UltimoAdministradorActivo):
        await _desactivar(empresas, usuarios, refrescos, publicador).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=admin.id,
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            usuario_id=admin.id,
            ahora=INSTANTE_FIJO,
        )
    assert admin.activo


async def test_un_administrador_invitado_no_cuenta_para_el_invariante(
    empresas, usuarios, refrescos, publicador
):
    """Caso 20. With a boolean `activo` this is the case that silently passed: an invited
    administrator would look like one the company already has."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    await usuarios.agregar(
        usuario_de_prueba(
            empresa_id,
            estado=EstadoUsuario.INVITADO,
            email="pendiente@empresa.com",
            con_contrasena=False,
        )
    )

    with pytest.raises(UltimoAdministradorActivo):
        await _desactivar(empresas, usuarios, refrescos, publicador).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=admin.id,
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            usuario_id=admin.id,
            ahora=INSTANTE_FIJO,
        )


async def test_con_dos_administradores_activos_degradar_a_uno_se_permite(
    empresas, usuarios, publicador
):
    """Caso 21."""
    empresa_id = EmpresaId(uuid4())
    primero = await _admin(usuarios, empresa_id)
    segundo = usuario_de_prueba(empresa_id, email="otro@empresa.com")
    await usuarios.agregar(segundo)

    resultado = await _cambiar_rol(empresas, usuarios, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=primero.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        usuario_id=segundo.id,
        rol_nuevo=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )

    assert resultado.rol is RolUsuario.OPERADOR


async def test_las_operaciones_del_invariante_bloquean_la_empresa_primero(
    empresas, usuarios, refrescos, publicador
):
    """The check-then-act race is only closed if the lock comes before the count."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    segundo = usuario_de_prueba(empresa_id, email="otro@empresa.com")
    await usuarios.agregar(segundo)

    await _desactivar(empresas, usuarios, refrescos, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        usuario_id=segundo.id,
        ahora=INSTANTE_FIJO,
    )

    assert empresas.bloqueadas == [empresa_id]


@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
async def test_quien_no_es_administrador_no_puede_cambiar_un_rol(
    empresas, usuarios, publicador, rol: RolUsuario
):
    """Caso 10 — HU-E1-05 RN-03."""
    empresa_id = EmpresaId(uuid4())
    afectado = await _admin(usuarios, empresa_id)

    with pytest.raises(PermisoDenegado):
        await _cambiar_rol(empresas, usuarios, publicador).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=UsuarioId(uuid4()),
            rol_del_ejecutor=rol,
            usuario_id=afectado.id,
            rol_nuevo=RolUsuario.OPERADOR,
            ahora=INSTANTE_FIJO,
        )


# ---------------------------------------------- desactivar, reactivar y auditar (22-24)


async def test_desactivar_revoca_los_refresh_del_usuario(
    empresas, usuarios, refrescos, publicador, tokens
):
    """Caso 22 — HU-E1-06 RN-01. Without this, "immediately" would mean "when the access
    token expires"."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    victima = usuario_de_prueba(empresa_id, email="otro@empresa.com", rol=RolUsuario.OPERADOR)
    await usuarios.agregar(victima)
    await refrescos.agregar(
        RefreshToken(
            id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=victima.id,
            familia_id=uuid4(),
            hash_del_token="h::vivo",
            expira_en=INSTANTE_FIJO + timedelta(days=30),
        )
    )

    await _desactivar(empresas, usuarios, refrescos, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        usuario_id=victima.id,
        ahora=INSTANTE_FIJO,
    )

    assert all(token.revocado for token in refrescos.tokens.values())
    assert victima.estado is EstadoUsuario.INACTIVO


async def test_reactivar_devuelve_al_usuario_con_su_rol(empresas, usuarios, refrescos, publicador):
    """HU-E1-06 RN-04, through the use case this time."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    otro = usuario_de_prueba(empresa_id, email="otro@empresa.com", rol=RolUsuario.SOLO_LECTURA)
    await usuarios.agregar(otro)
    await _desactivar(empresas, usuarios, refrescos, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        usuario_id=otro.id,
        ahora=INSTANTE_FIJO,
    )

    resultado = await ReactivarUsuario(usuarios=usuarios, publicador=publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        usuario_id=otro.id,
        ahora=INSTANTE_FIJO,
    )

    assert resultado.estado is EstadoUsuario.ACTIVO
    assert resultado.rol is RolUsuario.SOLO_LECTURA


async def test_cambiar_rol_y_desactivar_publican_su_evento_auditable(
    empresas, usuarios, refrescos, publicador
):
    """Caso 23 — HU-E1-05 RN-04: affected user, previous role, new role and executor."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    otro = usuario_de_prueba(empresa_id, email="otro@empresa.com")
    await usuarios.agregar(otro)

    await _cambiar_rol(empresas, usuarios, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        usuario_id=otro.id,
        rol_nuevo=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
        direccion_ip="203.0.113.7",
    )
    await _desactivar(empresas, usuarios, refrescos, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        usuario_id=otro.id,
        ahora=INSTANTE_FIJO,
    )

    eventos = [e for e in publicador.eventos if isinstance(e, EventoAuditable)]
    cambio = next(e for e in eventos if e.accion == "cambiar_rol_de_usuario")
    assert cambio.usuario_id == admin.id  # the executor, per RN-04
    assert str(otro.id) in cambio.entidad_afectada
    assert "ADMINISTRADOR->OPERADOR" in cambio.entidad_afectada
    assert cambio.direccion_ip == "203.0.113.7"
    assert any(e.accion == "desactivar_usuario" for e in eventos)


async def test_cambiar_al_mismo_rol_no_escribe_nada(empresas, usuarios, publicador):
    """An idempotent no-op should not produce an audit entry that says something changed."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)

    await _cambiar_rol(empresas, usuarios, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        usuario_id=admin.id,
        rol_nuevo=RolUsuario.ADMINISTRADOR,
        ahora=INSTANTE_FIJO,
    )

    assert publicador.eventos == []


async def test_el_listado_solo_trae_usuarios_de_la_empresa_del_ejecutor(
    usuarios, invitaciones, tokens_de_invitacion, publicador
):
    """Caso 24."""
    empresa_id = EmpresaId(uuid4())
    admin = await _admin(usuarios, empresa_id)
    await usuarios.agregar(usuario_de_prueba(EmpresaId(uuid4()), email="ajeno@otra.com"))
    emitida = await _invitar(usuarios, invitaciones, tokens_de_invitacion, publicador).ejecutar(
        empresa_id=empresa_id,
        ejecutor_id=admin.id,
        rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
        email=Email("nuevo@empresa.com"),
        rol=RolUsuario.OPERADOR,
        ahora=INSTANTE_FIJO,
    )

    filas = await ListarUsuarios(usuarios=usuarios, invitaciones=invitaciones).ejecutar(
        empresa_id=empresa_id
    )

    emails = {str(fila.usuario.email) for fila in filas}
    assert emails == {"admin@empresa.com", "nuevo@empresa.com"}
    pendiente = next(f for f in filas if f.usuario.id == emitida.usuario.id)
    # PAN-USR-01 needs the id on the row to offer "resend" and "revoke".
    assert pendiente.invitacion_id == emitida.invitacion.id
    assert next(f for f in filas if f.usuario.id == admin.id).invitacion_id is None


# -------------------------------------------------------------- preferencias (caso 25)


async def test_las_preferencias_de_un_usuario_no_tocan_las_de_otro(usuarios):
    """Caso 25 — HU-E1-07 RN-01."""
    empresa_id = EmpresaId(uuid4())
    ana = await _admin(usuarios, empresa_id)
    beto = usuario_de_prueba(empresa_id, email="beto@empresa.com")
    await usuarios.agregar(beto)
    solo_facturacion = PreferenciasDeNotificacion(
        frozenset({(CategoriaDeNotificacion.FACTURACION, CanalDeNotificacion.EMAIL)})
    )

    await ActualizarPreferencias(usuarios=usuarios).ejecutar(
        usuario_id=ana.id,
        idioma="es-AR",
        zona_horaria="America/Argentina/Cordoba",
        suscripciones=solo_facturacion,
    )

    assert ana.pref_zona_horaria == "America/Argentina/Cordoba"
    assert beto.pref_zona_horaria != "America/Argentina/Cordoba"
    assert beto.pref_suscripciones == PreferenciasDeNotificacion.todas()


async def test_guardar_un_solo_campo_no_revierte_los_otros(usuarios):
    """`None` means "leave this one alone" — the pattern where a stale form quietly
    reverts a setting changed in another tab."""
    empresa_id = EmpresaId(uuid4())
    ana = await _admin(usuarios, empresa_id)
    await ActualizarPreferencias(usuarios=usuarios).ejecutar(
        usuario_id=ana.id, zona_horaria="America/Argentina/Cordoba"
    )

    resultado = await ActualizarPreferencias(usuarios=usuarios).ejecutar(
        usuario_id=ana.id, idioma="es-AR"
    )

    assert resultado.pref_zona_horaria == "America/Argentina/Cordoba"


async def test_ver_preferencias_devuelve_las_actuales(usuarios):
    """The first acceptance criterion of HU-E1-07."""
    empresa_id = EmpresaId(uuid4())
    ana = await _admin(usuarios, empresa_id)

    resultado = await VerPreferencias(usuarios=usuarios).ejecutar(usuario_id=ana.id)

    assert resultado.pref_idioma == ana.pref_idioma
    assert resultado.pref_suscripciones == PreferenciasDeNotificacion.todas()
