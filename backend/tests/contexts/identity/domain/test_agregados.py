"""`Empresa`, `Usuario` and the refresh chain, at the domain level."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import (
    CUIT,
    CondicionIVA,
    Email,
    HashDeContrasena,
    RolUsuario,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

from tests.conftest import INSTANTE_FIJO
from tests.contexts.identity.conftest import CUIT_VALIDO


def _empresa() -> Empresa:
    return Empresa(id=EmpresaId(uuid4()))


def _completar(empresa: Empresa) -> None:
    empresa.completar_datos_fiscales(
        razon_social="Panaderia Dona Rosa SRL",
        cuit=CUIT(CUIT_VALIDO),
        condicion_iva=CondicionIVA.MONOTRIBUTO,
        nombre_responsable="Rosa Gimenez",
        email_contacto=Email("rosa@panaderia.com"),
    )


def test_una_empresa_recien_creada_no_completo_el_onboarding():
    """The state HU-E1-01 creates at step 1, which the DER's NOT NULLs did not admit."""
    empresa = _empresa()

    assert empresa.onboarding_completo is False
    assert empresa.datos_fiscales_completos is False
    assert empresa.cuit is None


def test_con_datos_fiscales_y_terminos_el_onboarding_esta_completo():
    empresa = _empresa()
    _completar(empresa)
    empresa.aceptar_terminos("1.0", INSTANTE_FIJO)

    assert empresa.onboarding_completo is True


def test_con_datos_fiscales_pero_sin_terminos_todavia_no():
    empresa = _empresa()
    _completar(empresa)

    assert empresa.onboarding_completo is False


def test_una_razon_social_vacia_es_rechazada():
    empresa = _empresa()

    with pytest.raises(EntradaInvalida, match="razon social"):
        empresa.completar_datos_fiscales(
            razon_social="   ",
            cuit=CUIT(CUIT_VALIDO),
            condicion_iva=CondicionIVA.EXENTO,
            nombre_responsable="Rosa",
            email_contacto=Email("rosa@panaderia.com"),
        )


def test_un_responsable_vacio_es_rechazado():
    """HU-E1-02 RN-03 lists it among the mandatory fields."""
    empresa = _empresa()

    with pytest.raises(EntradaInvalida, match="responsable"):
        empresa.completar_datos_fiscales(
            razon_social="Panaderia",
            cuit=CUIT(CUIT_VALIDO),
            condicion_iva=CondicionIVA.EXENTO,
            nombre_responsable=" ",
            email_contacto=Email("rosa@panaderia.com"),
        )


def test_si_cambia_la_version_de_terminos_hay_que_reaceptar():
    """HU-E1-03 RN-03."""
    empresa = _empresa()
    empresa.aceptar_terminos("1.0", INSTANTE_FIJO)

    assert empresa.debe_reaceptar_terminos("1.0") is False
    assert empresa.debe_reaceptar_terminos("2.0") is True


def test_una_empresa_sin_terminos_debe_aceptarlos():
    assert _empresa().debe_reaceptar_terminos("1.0") is True


def test_aceptar_terminos_guarda_version_y_fecha():
    empresa = _empresa()
    empresa.aceptar_terminos("2.1", INSTANTE_FIJO)

    assert empresa.terminos is not None
    assert empresa.terminos.version == "2.1"
    assert empresa.terminos.fecha == INSTANTE_FIJO


def test_una_empresa_sin_onboarding_no_es_operativa():
    with pytest.raises(InvarianteViolada, match="onboarding"):
        _empresa().exigir_operativa()


def test_una_empresa_desactivada_no_es_operativa():
    empresa = _empresa()
    _completar(empresa)
    empresa.aceptar_terminos("1.0", INSTANTE_FIJO)
    empresa.desactivar()

    with pytest.raises(InvarianteViolada, match="desactivada"):
        empresa.exigir_operativa()


def test_una_empresa_completa_y_activa_es_operativa():
    empresa = _empresa()
    _completar(empresa)
    empresa.aceptar_terminos("1.0", INSTANTE_FIJO)

    empresa.exigir_operativa()


def _usuario(**overrides: object) -> Usuario:
    base: dict[str, object] = {
        "id": UsuarioId(uuid4()),
        "empresa_id": EmpresaId(uuid4()),
        "email": Email("ana@empresa.com"),
        "nombre": "Ana Perez",
        "rol": RolUsuario.ADMINISTRADOR,
    }
    base.update(overrides)
    return Usuario(**base)  # type: ignore[arg-type]  # kwargs built above


def test_un_usuario_sin_nombre_es_rechazado():
    """PAN-USR-01 lists the name; the DER does not have it (gap H1)."""
    with pytest.raises(EntradaInvalida, match="nombre"):
        _usuario(nombre="  ")


def test_el_nombre_se_normaliza_sin_espacios():
    assert _usuario(nombre="  Ana Perez  ").nombre == "Ana Perez"


def test_un_usuario_de_google_no_puede_autenticarse_con_contrasena():
    """No password was ever chosen on this platform, so there is nothing to verify."""
    usuario = _usuario(hash_de_contrasena=None)

    assert usuario.puede_autenticarse_con_contrasena is False


def test_un_usuario_con_contrasena_si_puede():
    usuario = _usuario(hash_de_contrasena=HashDeContrasena("hash::x"))

    assert usuario.puede_autenticarse_con_contrasena is True


def test_un_usuario_desactivado_no_puede_operar():
    """HU-E1-06 RN-01."""
    with pytest.raises(InvarianteViolada, match="desactivado"):
        _usuario(activo=False).exigir_activo()


def test_quien_registra_la_empresa_la_administra():
    assert _usuario().es_administrador is True
    assert _usuario(rol=RolUsuario.SOLO_LECTURA).es_administrador is False


def test_las_preferencias_se_actualizan_de_a_una():
    """HU-E1-07: changing the language must not reset the timezone."""
    usuario = _usuario()
    zona_original = usuario.pref_zona_horaria

    usuario.actualizar_preferencias(idioma="en-US", zona_horaria=None)

    assert usuario.pref_idioma == "en-US"
    assert usuario.pref_zona_horaria == zona_original


def test_cambiar_la_contrasena_reemplaza_el_hash():
    usuario = _usuario()

    usuario.cambiar_contrasena(HashDeContrasena("hash::nueva"))

    assert usuario.hash_de_contrasena is not None
    assert usuario.hash_de_contrasena.valor == "hash::nueva"


def _refresh(**overrides: object) -> RefreshToken:
    base: dict[str, object] = {
        "id": uuid4(),
        "familia_id": uuid4(),
        "empresa_id": EmpresaId(uuid4()),
        "usuario_id": UsuarioId(uuid4()),
        "hash_del_token": "h::abc",
        "expira_en": INSTANTE_FIJO + timedelta(days=30),
    }
    base.update(overrides)
    return RefreshToken(**base)  # type: ignore[arg-type]  # kwargs built above


def test_un_refresh_nuevo_es_utilizable():
    assert _refresh().es_utilizable(INSTANTE_FIJO) is True


def test_un_refresh_usado_deja_de_ser_utilizable():
    token = _refresh()
    token.marcar_usado(INSTANTE_FIJO)

    assert token.fue_usado is True
    assert token.es_utilizable(INSTANTE_FIJO) is False


def test_un_refresh_revocado_deja_de_ser_utilizable():
    token = _refresh()
    token.revocar()

    assert token.es_utilizable(INSTANTE_FIJO) is False


def test_un_refresh_vencido_deja_de_ser_utilizable():
    token = _refresh(expira_en=INSTANTE_FIJO - timedelta(seconds=1))

    assert token.esta_vencido(INSTANTE_FIJO) is True
    assert token.es_utilizable(INSTANTE_FIJO) is False


def test_un_refresh_debe_guardarse_hasheado():
    """Storing the token itself would make a database dump a set of live sessions."""
    with pytest.raises(EntradaInvalida, match="hasheado"):
        _refresh(hash_del_token="  ")


def test_un_refresh_exige_vencimiento_con_zona_horaria():
    with pytest.raises(EntradaInvalida, match="zona horaria"):
        _refresh(expira_en=datetime(2026, 9, 1))  # noqa: DTZ001 — that is the case
