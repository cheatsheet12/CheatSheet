"""The invitation aggregate, the user's three states, and the notification preferences.

Cases 1 to 5 of the `usuarios-y-preferencias` plan. All pure domain: no repository, no
clock beyond the instant each test passes in.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.domain.invitacion import Invitacion
from cheatsheet.contexts.identity.domain.usuario import NOMBRE_PENDIENTE, Usuario
from cheatsheet.contexts.identity.domain.valores import (
    CanalDeNotificacion,
    CategoriaDeNotificacion,
    Email,
    EstadoUsuario,
    HashDeContrasena,
    PreferenciasDeNotificacion,
    RolUsuario,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

from tests.conftest import INSTANTE_FIJO

HASH = HashDeContrasena("hash::una-contrasena-larga")


def _invitado() -> Usuario:
    return Usuario(
        id=UsuarioId(uuid4()),
        empresa_id=EmpresaId(uuid4()),
        email=Email("nuevo@empresa.com"),
        nombre=NOMBRE_PENDIENTE,
        rol=RolUsuario.OPERADOR,
        estado=EstadoUsuario.INVITADO,
    )


def _invitacion(**overrides: object) -> Invitacion:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EmpresaId(uuid4()),
        "usuario_id": UsuarioId(uuid4()),
        "hash_del_token": "h::un-token",
        "expira_en": INSTANTE_FIJO + timedelta(days=7),
        "invitado_por": UsuarioId(uuid4()),
    }
    base.update(overrides)
    return Invitacion(**base)  # type: ignore[arg-type]  # kwargs built above


# ---------------------------------------------------------------- caso 1: transiciones


def test_aceptar_una_invitacion_deja_al_usuario_activo_y_con_contrasena():
    usuario = _invitado()

    usuario.aceptar_invitacion(nombre="Ana Perez", hash_de_contrasena=HASH)

    assert usuario.estado is EstadoUsuario.ACTIVO
    assert usuario.nombre == "Ana Perez"
    assert usuario.puede_autenticarse_con_contrasena


def test_no_se_puede_aceptar_dos_veces_la_misma_invitacion():
    """Replaying it would be a password reset with no proof of who is asking."""
    usuario = _invitado()
    usuario.aceptar_invitacion(nombre="Ana Perez", hash_de_contrasena=HASH)

    with pytest.raises(InvarianteViolada):
        usuario.aceptar_invitacion(nombre="Otra", hash_de_contrasena=HASH)


def test_una_invitacion_pendiente_se_revoca_no_se_desactiva():
    with pytest.raises(InvarianteViolada, match="revoca"):
        _invitado().desactivar()


def test_solo_se_reactiva_a_quien_esta_inactivo():
    usuario = _invitado()
    usuario.aceptar_invitacion(nombre="Ana Perez", hash_de_contrasena=HASH)

    with pytest.raises(InvarianteViolada):
        usuario.reactivar()


def test_un_invitado_administrador_no_cuenta_como_administrador_activo():
    """The reason `estado` replaced the boolean: an invited admin is not an admin yet."""
    usuario = _invitado()
    usuario.rol = RolUsuario.ADMINISTRADOR

    assert usuario.es_administrador
    assert not usuario.es_administrador_activo


# ------------------------------------------------------------- caso 2: el rol se conserva


def test_reactivar_devuelve_el_rol_previo_y_no_uno_por_defecto():
    """HU-E1-06 RN-04. It works because deactivating never erased the role."""
    usuario = _invitado()
    usuario.aceptar_invitacion(nombre="Ana Perez", hash_de_contrasena=HASH)
    usuario.cambiar_rol(RolUsuario.SOLO_LECTURA)

    usuario.desactivar()
    usuario.reactivar()

    assert usuario.rol is RolUsuario.SOLO_LECTURA
    assert usuario.estado is EstadoUsuario.ACTIVO


# ---------------------------------------------------- casos 3 y 4: preferencias a jsonb


def test_las_preferencias_van_y_vuelven_de_jsonb_sin_perder_nada():
    originales = PreferenciasDeNotificacion(
        frozenset(
            {
                (CategoriaDeNotificacion.FACTURACION, CanalDeNotificacion.EMAIL),
                (CategoriaDeNotificacion.AGENDA, CanalDeNotificacion.PANEL),
            }
        )
    )

    recuperadas = PreferenciasDeNotificacion.desde_json(originales.a_json())

    assert recuperadas == originales
    assert recuperadas.recibe(CategoriaDeNotificacion.FACTURACION, CanalDeNotificacion.EMAIL)
    assert not recuperadas.recibe(CategoriaDeNotificacion.FACTURACION, CanalDeNotificacion.PANEL)


def test_por_defecto_un_usuario_recibe_todo():
    todas = PreferenciasDeNotificacion.todas()

    assert all(
        todas.recibe(categoria, canal)
        for categoria in CategoriaDeNotificacion
        for canal in CanalDeNotificacion
    )


@pytest.mark.parametrize(
    "crudo",
    [
        {"NO_EXISTE": ["EMAIL"]},
        {"FACTURACION": ["TELEGRAMA"]},
        {"FACTURACION": "EMAIL"},
        {"FACTURACION": [7]},
        ["FACTURACION"],
    ],
    ids=[
        "categoria-desconocida",
        "canal-desconocido",
        "canales-no-lista",
        "canal-no-texto",
        "no-es-objeto",
    ],
)
def test_una_preferencia_que_el_catalogo_no_nombra_es_rechazada(crudo: object):
    """The column is `jsonb` and accepts any shape; this is the only gate."""
    with pytest.raises(EntradaInvalida):
        PreferenciasDeNotificacion.desde_json(crudo)


# ------------------------------------------------------------------- caso 5: vigencia


def test_una_invitacion_recien_emitida_es_utilizable():
    assert _invitacion().es_utilizable(INSTANTE_FIJO)


def test_una_invitacion_vencida_no_es_utilizable():
    invitacion = _invitacion(expira_en=INSTANTE_FIJO)

    assert invitacion.esta_vencida(INSTANTE_FIJO)
    assert not invitacion.es_utilizable(INSTANTE_FIJO)


def test_una_invitacion_aceptada_no_es_utilizable_de_nuevo():
    invitacion = _invitacion()
    invitacion.aceptar(INSTANTE_FIJO)

    assert not invitacion.es_utilizable(INSTANTE_FIJO)
    with pytest.raises(InvarianteViolada):
        invitacion.aceptar(INSTANTE_FIJO)


def test_una_invitacion_revocada_no_es_utilizable():
    invitacion = _invitacion()
    invitacion.revocar()

    assert not invitacion.es_utilizable(INSTANTE_FIJO)


def test_una_invitacion_aceptada_ya_no_se_puede_revocar():
    """Taking access away from someone who has been working is deactivating them."""
    invitacion = _invitacion()
    invitacion.aceptar(INSTANTE_FIJO)

    with pytest.raises(InvarianteViolada):
        invitacion.revocar()


def test_reenviar_invalida_el_token_anterior():
    invitacion = _invitacion(hash_del_token="h::viejo")

    invitacion.reemplazar_token("h::nuevo", INSTANTE_FIJO + timedelta(days=7))

    assert invitacion.hash_del_token == "h::nuevo"


def test_no_se_puede_reenviar_una_invitacion_que_ya_no_esta_pendiente():
    invitacion = _invitacion()
    invitacion.revocar()

    with pytest.raises(InvarianteViolada):
        invitacion.reemplazar_token("h::nuevo", INSTANTE_FIJO + timedelta(days=7))


def test_una_invitacion_sin_hash_es_rechazada():
    """The token is a credential: storing it in clear text is the mistake this prevents."""
    with pytest.raises(EntradaInvalida):
        _invitacion(hash_del_token="   ")


def test_un_vencimiento_sin_zona_horaria_es_rechazado():
    with pytest.raises(EntradaInvalida):
        _invitacion(expira_en=INSTANTE_FIJO.replace(tzinfo=None))
