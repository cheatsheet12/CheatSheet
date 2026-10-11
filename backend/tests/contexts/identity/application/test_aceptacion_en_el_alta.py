"""Consent at sign-up and at accepting an invitation (HU-E1-03 RN-02, HU-E1-08 RN-02/03/04)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.application.aceptaciones import Consentimiento
from cheatsheet.contexts.identity.application.errors import (
    ConsentimientoRequerido,
    VersionLegalDesactualizada,
)
from cheatsheet.contexts.identity.application.registro import (
    EmpresaRegistrada,
    RegistrarConGoogle,
    RegistrarEmpresa,
)
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal
from cheatsheet.contexts.identity.domain.valores import Email, EstadoUsuario
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

from tests.conftest import INSTANTE_FIJO
from tests.contexts.identity.application.test_usuarios_y_preferencias import (
    _aceptar,
    _emitir_invitacion,
)
from tests.contexts.identity.conftest import (
    CONSENTIMIENTO,
    CONTRASENA,
    VERSION_DE_PRIVACIDAD,
    VERSION_DE_TERMINOS,
)

pytestmark = pytest.mark.asyncio


def _registrar(empresas, usuarios, hasher, publicador, registrador) -> RegistrarEmpresa:
    return RegistrarEmpresa(
        empresas=empresas,
        usuarios=usuarios,
        hasher=hasher,
        publicador=publicador,
        registrador=registrador,
    )


async def _registro(
    caso: RegistrarEmpresa, consentimiento: Consentimiento | None, **kw: str
) -> EmpresaRegistrada:
    return await caso.ejecutar(
        empresa_id=EmpresaId(uuid4()),
        email=Email("ana@empresa.com"),
        contrasena=CONTRASENA,
        nombre="Ana Perez",
        consentimiento=consentimiento,
        ahora=INSTANTE_FIJO,
        **kw,
    )


# ------------------------------------------------------------------------------ case 12


async def test_registro_sin_consentimiento_es_422_y_no_crea_nada(
    empresas, usuarios, hasher, publicador, registrador, aceptaciones
):
    caso = _registrar(empresas, usuarios, hasher, publicador, registrador)

    with pytest.raises(ConsentimientoRequerido) as error:
        await _registro(caso, None)

    assert isinstance(error.value, EntradaInvalida)
    assert "Debe aceptar los términos y condiciones para continuar." in str(error.value)
    assert not empresas.empresas
    assert not usuarios.usuarios
    assert not aceptaciones.aceptaciones
    assert not publicador.eventos


@pytest.mark.parametrize(
    ("consentimiento", "mensaje"),
    [
        (
            Consentimiento(version_terminos=None, version_privacidad=VERSION_DE_PRIVACIDAD),
            "Debe aceptar los términos y condiciones para continuar.",
        ),
        (
            Consentimiento(version_terminos=VERSION_DE_TERMINOS, version_privacidad=None),
            "Debe aceptar la política de privacidad para continuar.",
        ),
    ],
)
async def test_cada_casilla_se_exige_con_su_propio_mensaje(
    empresas, usuarios, hasher, publicador, registrador, consentimiento, mensaje
):
    caso = _registrar(empresas, usuarios, hasher, publicador, registrador)

    with pytest.raises(ConsentimientoRequerido, match=mensaje):
        await _registro(caso, consentimiento)

    assert not usuarios.usuarios


# ------------------------------------------------------------------------------ case 13


@pytest.mark.parametrize(
    "consentimiento",
    [
        Consentimiento(version_terminos="1.0", version_privacidad=VERSION_DE_PRIVACIDAD),
        Consentimiento(version_terminos="2.0", version_privacidad=VERSION_DE_PRIVACIDAD),
        Consentimiento(version_terminos=VERSION_DE_TERMINOS, version_privacidad="9.9"),
    ],
    ids=["terminos-anteriores", "terminos-futuros", "privacidad-desconocida"],
)
async def test_una_version_que_no_es_la_vigente_es_409_y_no_crea_nada(
    empresas, usuarios, hasher, publicador, registrador, aceptaciones, consentimiento
):
    caso = _registrar(empresas, usuarios, hasher, publicador, registrador)

    with pytest.raises(VersionLegalDesactualizada) as error:
        await _registro(caso, consentimiento)

    assert isinstance(error.value, InvarianteViolada)
    assert not empresas.empresas
    assert not usuarios.usuarios
    assert not aceptaciones.aceptaciones
    assert not publicador.eventos


# ------------------------------------------------------------------------------ case 14


async def test_registro_valido_deja_estado_filas_y_eventos(
    empresas, usuarios, hasher, publicador, registrador, aceptaciones
):
    caso = _registrar(empresas, usuarios, hasher, publicador, registrador)

    registrada = await _registro(caso, CONSENTIMIENTO, direccion_ip="190.0.0.1")

    empresa, usuario = registrada.empresa, registrada.usuario
    assert empresa.terminos is not None
    assert empresa.terminos.version == VERSION_DE_TERMINOS
    assert empresa.terminos.fecha == INSTANTE_FIJO
    filas = {(a.documento, a.version): a for a in aceptaciones.aceptaciones}
    assert set(filas) == {
        (DocumentoLegal.TERMINOS, VERSION_DE_TERMINOS),
        (DocumentoLegal.PRIVACIDAD, VERSION_DE_PRIVACIDAD),
    }
    assert all(a.usuario_id == usuario.id for a in filas.values())
    assert all(a.empresa_id == empresa.id for a in filas.values())
    assert all(a.fecha_aceptacion == INSTANTE_FIJO for a in filas.values())
    eventos = {e.accion: e for e in publicador.eventos if isinstance(e, EventoAuditable)}
    assert set(eventos) == {
        "registrar_empresa",
        "aceptar_terminos",
        "aceptar_politica_de_privacidad",
    }
    terminos = eventos["aceptar_terminos"]
    assert terminos.entidad_afectada == f"Empresa:{empresa.id} terminos {VERSION_DE_TERMINOS}"
    assert terminos.detalle == {"documento": "TERMINOS", "version": VERSION_DE_TERMINOS}
    privacidad = eventos["aceptar_politica_de_privacidad"]
    assert privacidad.entidad_afectada == f"Usuario:{usuario.id} privacidad {VERSION_DE_PRIVACIDAD}"
    assert privacidad.detalle == {"documento": "PRIVACIDAD", "version": VERSION_DE_PRIVACIDAD}
    assert terminos.usuario_id == privacidad.usuario_id == usuario.id
    assert terminos.direccion_ip == privacidad.direccion_ip == "190.0.0.1"


# ------------------------------------------------------------------------------ case 15


def _google(empresas, usuarios, publicador, registrador) -> RegistrarConGoogle:
    return RegistrarConGoogle(
        empresas=empresas, usuarios=usuarios, publicador=publicador, registrador=registrador
    )


async def test_google_sin_consentimiento_no_crea_la_cuenta(
    empresas, usuarios, publicador, registrador, aceptaciones, perfil_de_google
):
    with pytest.raises(ConsentimientoRequerido):
        await _google(empresas, usuarios, publicador, registrador).ejecutar(
            empresa_id=EmpresaId(uuid4()),
            email=perfil_de_google.email,
            nombre=perfil_de_google.nombre,
            consentimiento=None,
            ahora=INSTANTE_FIJO,
        )

    assert not empresas.empresas
    assert not usuarios.usuarios
    assert not aceptaciones.aceptaciones


async def test_google_con_consentimiento_registra_lo_mismo_que_el_alta_con_email(
    empresas, usuarios, publicador, registrador, aceptaciones, perfil_de_google
):
    registrada = await _google(empresas, usuarios, publicador, registrador).ejecutar(
        empresa_id=EmpresaId(uuid4()),
        email=perfil_de_google.email,
        nombre=perfil_de_google.nombre,
        consentimiento=CONSENTIMIENTO,
        ahora=INSTANTE_FIJO,
    )

    assert registrada.empresa.terminos is not None
    assert registrada.empresa.terminos.version == VERSION_DE_TERMINOS
    assert {(a.documento, a.version) for a in aceptaciones.aceptaciones} == {
        (DocumentoLegal.TERMINOS, VERSION_DE_TERMINOS),
        (DocumentoLegal.PRIVACIDAD, VERSION_DE_PRIVACIDAD),
    }
    acciones = {e.accion for e in publicador.eventos if isinstance(e, EventoAuditable)}
    assert {"aceptar_terminos", "aceptar_politica_de_privacidad"} <= acciones


async def test_google_con_una_version_vieja_es_409(
    empresas, usuarios, publicador, registrador, perfil_de_google
):
    with pytest.raises(VersionLegalDesactualizada):
        await _google(empresas, usuarios, publicador, registrador).ejecutar(
            empresa_id=EmpresaId(uuid4()),
            email=perfil_de_google.email,
            nombre=perfil_de_google.nombre,
            consentimiento=Consentimiento(version_terminos="1.0", version_privacidad="1.0"),
            ahora=INSTANTE_FIJO,
        )

    assert not empresas.empresas


# ------------------------------------------------------------------------------ case 17


async def test_aceptar_invitacion_sin_la_privacidad_se_rechaza_y_sigue_invitado(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador, registrador
):
    emitida = await _emitir_invitacion(usuarios, invitaciones, tokens_de_invitacion, publicador)
    caso = _aceptar(
        usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador, registrador
    )

    with pytest.raises(ConsentimientoRequerido, match="política de privacidad"):
        await caso.ejecutar(
            token=emitida.token_en_claro,
            nombre="Beto Gomez",
            contrasena=CONTRASENA,
            version_privacidad=None,
            ahora=INSTANTE_FIJO,
        )

    assert usuarios.usuarios[emitida.usuario.id].estado is EstadoUsuario.INVITADO


async def test_aceptar_invitacion_con_una_privacidad_vieja_es_409(
    usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador, registrador
):
    emitida = await _emitir_invitacion(usuarios, invitaciones, tokens_de_invitacion, publicador)
    caso = _aceptar(
        usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador, registrador
    )

    with pytest.raises(VersionLegalDesactualizada):
        await caso.ejecutar(
            token=emitida.token_en_claro,
            nombre="Beto Gomez",
            contrasena=CONTRASENA,
            version_privacidad="0.9",
            ahora=INSTANTE_FIJO,
        )

    assert usuarios.usuarios[emitida.usuario.id].estado is EstadoUsuario.INVITADO


async def test_aceptar_invitacion_registra_solo_la_privacidad(
    usuarios,
    invitaciones,
    tokens_de_invitacion,
    hasher,
    emisor,
    publicador,
    registrador,
    aceptaciones,
):
    """HU-E1-08 RN-04: the invitee accepts the policy; the terms are the company's."""
    emitida = await _emitir_invitacion(usuarios, invitaciones, tokens_de_invitacion, publicador)
    caso = _aceptar(
        usuarios, invitaciones, tokens_de_invitacion, hasher, emisor, publicador, registrador
    )

    await caso.ejecutar(
        token=emitida.token_en_claro,
        nombre="Beto Gomez",
        contrasena=CONTRASENA,
        version_privacidad=VERSION_DE_PRIVACIDAD,
        ahora=INSTANTE_FIJO,
        direccion_ip="190.0.0.2",
    )

    assert [(a.documento, a.version, a.usuario_id) for a in aceptaciones.aceptaciones] == [
        (DocumentoLegal.PRIVACIDAD, VERSION_DE_PRIVACIDAD, emitida.usuario.id)
    ]
    eventos = [e for e in publicador.eventos if isinstance(e, EventoAuditable)]
    privacidad = next(e for e in eventos if e.accion == "aceptar_politica_de_privacidad")
    assert privacidad.entidad_afectada == (
        f"Usuario:{emitida.usuario.id} privacidad {VERSION_DE_PRIVACIDAD}"
    )
    assert privacidad.usuario_id == emitida.usuario.id
    assert privacidad.direccion_ip == "190.0.0.2"
    assert not any(e.accion == "aceptar_terminos" for e in eventos)
