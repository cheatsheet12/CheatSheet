"""The use cases: sign-up, sign-in, the refresh chain and step 2 of the onboarding."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.application.errors import (
    CredencialesInvalidas,
    CuitYaRegistrado,
    EmailYaRegistrado,
    ReusoDeRefreshDetectado,
    SesionInvalida,
)
from cheatsheet.contexts.identity.application.onboarding import (
    AceptarTerminos,
    CompletarDatosDeEmpresa,
)
from cheatsheet.contexts.identity.application.registro import (
    RegistrarConGoogle,
    RegistrarEmpresa,
)
from cheatsheet.contexts.identity.application.sesiones import (
    CerrarSesion,
    IniciarSesion,
    RefrescarSesion,
    Sesion,
)
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import CUIT, CondicionIVA, Email, RolUsuario
from cheatsheet.shared.auditoria import EventoAuditable, Modulo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

from tests.conftest import INSTANTE_FIJO
from tests.contexts.identity.conftest import CONTRASENA, CUIT_VALIDO, usuario_de_prueba

pytestmark = pytest.mark.asyncio


def _registrar(empresas, usuarios, hasher, publicador) -> RegistrarEmpresa:
    return RegistrarEmpresa(
        empresas=empresas, usuarios=usuarios, hasher=hasher, publicador=publicador
    )


async def test_registrarse_crea_empresa_y_administrador(empresas, usuarios, hasher, publicador):
    empresa_id = EmpresaId(uuid4())

    resultado = await _registrar(empresas, usuarios, hasher, publicador).ejecutar(
        empresa_id=empresa_id,
        email=Email("ana@empresa.com"),
        contrasena=CONTRASENA,
        nombre="Ana Perez",
        version_terminos="1.0",
        ahora=INSTANTE_FIJO,
    )

    assert resultado.usuario.rol is RolUsuario.ADMINISTRADOR
    assert resultado.usuario.empresa_id == empresa_id
    assert empresas.empresas[empresa_id] is resultado.empresa
    assert usuarios.usuarios[resultado.usuario.id] is resultado.usuario


async def test_registrarse_acepta_los_terminos_en_el_mismo_acto(
    empresas, usuarios, hasher, publicador
):
    """HU-E1-03 RN-02: acceptance completes the registration, it is not a later step."""
    resultado = await _registrar(empresas, usuarios, hasher, publicador).ejecutar(
        empresa_id=EmpresaId(uuid4()),
        email=Email("ana@empresa.com"),
        contrasena=CONTRASENA,
        nombre="Ana",
        version_terminos="3.2",
        ahora=INSTANTE_FIJO,
    )

    assert resultado.empresa.terminos is not None
    assert resultado.empresa.terminos.version == "3.2"


async def test_el_registro_queda_en_la_bitacora(empresas, usuarios, hasher, publicador):
    """The first real use of the HS-T5 mechanism the previous unit built."""
    await _registrar(empresas, usuarios, hasher, publicador).ejecutar(
        empresa_id=EmpresaId(uuid4()),
        email=Email("ana@empresa.com"),
        contrasena=CONTRASENA,
        nombre="Ana",
        version_terminos="1.0",
        ahora=INSTANTE_FIJO,
        direccion_ip="190.0.0.1",
    )

    evento = publicador.eventos[0]
    assert isinstance(evento, EventoAuditable)
    assert evento.modulo is Modulo.IDENTITY
    assert evento.accion == "registrar_empresa"
    assert evento.direccion_ip == "190.0.0.1"
    assert evento.usuario_id is not None


async def test_un_email_ya_registrado_es_rechazado(empresas, usuarios, hasher, publicador):
    """HU-E1-01 RN-03."""
    caso = _registrar(empresas, usuarios, hasher, publicador)

    async def registrar(email: str) -> None:
        await caso.ejecutar(
            empresa_id=EmpresaId(uuid4()),
            email=Email(email),
            contrasena=CONTRASENA,
            nombre="Ana",
            version_terminos="1.0",
            ahora=INSTANTE_FIJO,
        )

    await registrar("ana@empresa.com")

    with pytest.raises(EmailYaRegistrado):
        await registrar("ana@empresa.com")


async def test_el_mismo_email_en_otra_capitalizacion_tambien(
    empresas, usuarios, hasher, publicador
):
    caso = _registrar(empresas, usuarios, hasher, publicador)
    await caso.ejecutar(
        empresa_id=EmpresaId(uuid4()),
        email=Email("ana@empresa.com"),
        contrasena=CONTRASENA,
        nombre="Ana",
        version_terminos="1.0",
        ahora=INSTANTE_FIJO,
    )

    with pytest.raises(EmailYaRegistrado):
        await caso.ejecutar(
            empresa_id=EmpresaId(uuid4()),
            email=Email("ANA@EMPRESA.COM"),
            contrasena=CONTRASENA,
            nombre="Ana",
            version_terminos="1.0",
            ahora=INSTANTE_FIJO,
        )


async def test_una_contrasena_corta_no_llega_a_crear_nada(empresas, usuarios, hasher, publicador):
    """Validation happens before any write, so a rejected form leaves no orphan."""
    with pytest.raises(EntradaInvalida):
        await _registrar(empresas, usuarios, hasher, publicador).ejecutar(
            empresa_id=EmpresaId(uuid4()),
            email=Email("ana@empresa.com"),
            contrasena="corta",
            nombre="Ana",
            version_terminos="1.0",
            ahora=INSTANTE_FIJO,
        )

    assert empresas.empresas == {}
    assert usuarios.usuarios == {}


async def test_la_contrasena_se_guarda_hasheada(empresas, usuarios, hasher, publicador):
    resultado = await _registrar(empresas, usuarios, hasher, publicador).ejecutar(
        empresa_id=EmpresaId(uuid4()),
        email=Email("ana@empresa.com"),
        contrasena=CONTRASENA,
        nombre="Ana",
        version_terminos="1.0",
        ahora=INSTANTE_FIJO,
    )

    guardado = resultado.usuario.hash_de_contrasena
    assert guardado is not None
    assert guardado.valor != CONTRASENA


async def test_registrarse_con_google_no_deja_contrasena(
    empresas, usuarios, publicador, perfil_de_google
):
    """HU-E1-01 RN-02: that person never chose a password here."""
    resultado = await RegistrarConGoogle(
        empresas=empresas, usuarios=usuarios, publicador=publicador
    ).ejecutar(
        empresa_id=EmpresaId(uuid4()),
        email=perfil_de_google.email,
        nombre=perfil_de_google.nombre,
        version_terminos="1.0",
        ahora=INSTANTE_FIJO,
    )

    assert resultado.usuario.hash_de_contrasena is None
    assert resultado.usuario.puede_autenticarse_con_contrasena is False


async def test_google_tambien_rechaza_un_email_ya_registrado(
    empresas, usuarios, publicador, perfil_de_google
):
    caso = RegistrarConGoogle(empresas=empresas, usuarios=usuarios, publicador=publicador)

    async def registrar() -> None:
        await caso.ejecutar(
            empresa_id=EmpresaId(uuid4()),
            email=perfil_de_google.email,
            nombre=perfil_de_google.nombre,
            version_terminos="1.0",
            ahora=INSTANTE_FIJO,
        )

    await registrar()

    with pytest.raises(EmailYaRegistrado):
        await registrar()


async def test_iniciar_sesion_devuelve_los_dos_tokens(usuarios, hasher, emisor, refrescos):
    usuario = usuario_de_prueba(EmpresaId(uuid4()))
    await usuarios.agregar(usuario)

    sesion = await IniciarSesion(usuarios=usuarios, hasher=hasher, emisor=emisor).ejecutar(
        email=usuario.email, contrasena=CONTRASENA, ahora=INSTANTE_FIJO
    )

    assert sesion.access_token.startswith("acceso::")
    assert sesion.refresh_token.startswith("refresh::")
    # The refresh link is persisted hashed, never in the clear.
    guardado = next(iter(refrescos.tokens.values()))
    assert guardado.hash_del_token == f"h::{sesion.refresh_token}"


@pytest.mark.parametrize(
    ("contrasena", "activo", "con_contrasena"),
    [
        ("otra-contrasena", True, True),
        (CONTRASENA, False, True),
        (CONTRASENA, True, False),
    ],
    ids=["contrasena-incorrecta", "usuario-desactivado", "cuenta-de-google"],
)
async def test_todo_fallo_de_login_devuelve_el_mismo_error(
    usuarios, hasher, emisor, contrasena: str, activo: bool, con_contrasena: bool
):
    """Distinguishing them would turn the login form into an account enumerator."""
    usuario = usuario_de_prueba(EmpresaId(uuid4()), activo=activo, con_contrasena=con_contrasena)
    await usuarios.agregar(usuario)

    with pytest.raises(CredencialesInvalidas):
        await IniciarSesion(usuarios=usuarios, hasher=hasher, emisor=emisor).ejecutar(
            email=usuario.email, contrasena=contrasena, ahora=INSTANTE_FIJO
        )


async def test_un_email_inexistente_devuelve_el_mismo_error(usuarios, hasher, emisor):
    with pytest.raises(CredencialesInvalidas):
        await IniciarSesion(usuarios=usuarios, hasher=hasher, emisor=emisor).ejecutar(
            email=Email("nadie@empresa.com"), contrasena=CONTRASENA, ahora=INSTANTE_FIJO
        )


async def _sesion_inicial(usuarios, hasher, emisor) -> tuple[Usuario, Sesion]:
    usuario = usuario_de_prueba(EmpresaId(uuid4()))
    await usuarios.agregar(usuario)
    sesion = await IniciarSesion(usuarios=usuarios, hasher=hasher, emisor=emisor).ejecutar(
        email=usuario.email, contrasena=CONTRASENA, ahora=INSTANTE_FIJO
    )
    return usuario, sesion


async def test_refrescar_rota_el_token(usuarios, hasher, emisor, refrescos, tokens):
    _, sesion = await _sesion_inicial(usuarios, hasher, emisor)

    nueva = await RefrescarSesion(
        usuarios=usuarios, refrescos=refrescos, tokens=tokens, emisor=emisor
    ).ejecutar(refresh_token=sesion.refresh_token, ahora=INSTANTE_FIJO)

    assert nueva.refresh_token != sesion.refresh_token
    anterior = await refrescos.buscar_por_hash(f"h::{sesion.refresh_token}")
    assert anterior is not None
    assert anterior.fue_usado is True


async def test_el_refresh_conserva_la_familia(usuarios, hasher, emisor, refrescos, tokens):
    """Rotation is a chain, and revocation works on the chain."""
    _, sesion = await _sesion_inicial(usuarios, hasher, emisor)
    original = await refrescos.buscar_por_hash(f"h::{sesion.refresh_token}")

    nueva = await RefrescarSesion(
        usuarios=usuarios, refrescos=refrescos, tokens=tokens, emisor=emisor
    ).ejecutar(refresh_token=sesion.refresh_token, ahora=INSTANTE_FIJO)

    assert original is not None
    nuevo_guardado = await refrescos.buscar_por_hash(f"h::{nueva.refresh_token}")
    assert nuevo_guardado is not None
    assert nuevo_guardado.familia_id == original.familia_id


async def test_reusar_un_refresh_revoca_toda_la_familia(
    usuarios, hasher, emisor, refrescos, tokens
):
    """The alarm: otherwise the thief and the victim just take turns rotating."""
    _, sesion = await _sesion_inicial(usuarios, hasher, emisor)
    caso = RefrescarSesion(usuarios=usuarios, refrescos=refrescos, tokens=tokens, emisor=emisor)
    await caso.ejecutar(refresh_token=sesion.refresh_token, ahora=INSTANTE_FIJO)

    with pytest.raises(ReusoDeRefreshDetectado):
        await caso.ejecutar(refresh_token=sesion.refresh_token, ahora=INSTANTE_FIJO)

    assert all(token.revocado for token in refrescos.tokens.values())


async def test_un_refresh_desconocido_es_rechazado(usuarios, refrescos, tokens, emisor):
    with pytest.raises(SesionInvalida):
        await RefrescarSesion(
            usuarios=usuarios, refrescos=refrescos, tokens=tokens, emisor=emisor
        ).ejecutar(refresh_token="inventado", ahora=INSTANTE_FIJO)


async def test_un_refresh_vencido_es_rechazado(usuarios, hasher, emisor, refrescos, tokens):
    _, sesion = await _sesion_inicial(usuarios, hasher, emisor)

    with pytest.raises(SesionInvalida):
        await RefrescarSesion(
            usuarios=usuarios, refrescos=refrescos, tokens=tokens, emisor=emisor
        ).ejecutar(refresh_token=sesion.refresh_token, ahora=INSTANTE_FIJO + timedelta(days=31))


async def test_un_usuario_desactivado_no_puede_refrescar(
    usuarios, hasher, emisor, refrescos, tokens
):
    usuario, sesion = await _sesion_inicial(usuarios, hasher, emisor)
    usuario.activo = False
    await usuarios.guardar(usuario)

    with pytest.raises(SesionInvalida):
        await RefrescarSesion(
            usuarios=usuarios, refrescos=refrescos, tokens=tokens, emisor=emisor
        ).ejecutar(refresh_token=sesion.refresh_token, ahora=INSTANTE_FIJO)


async def test_cerrar_sesion_revoca_la_familia(usuarios, hasher, emisor, refrescos, tokens):
    _, sesion = await _sesion_inicial(usuarios, hasher, emisor)

    await CerrarSesion(refrescos=refrescos, tokens=tokens).ejecutar(
        refresh_token=sesion.refresh_token
    )

    assert all(token.revocado for token in refrescos.tokens.values())


async def test_cerrar_sesion_con_un_token_desconocido_no_falla(refrescos, tokens):
    """Signing out is never an error the user should see."""
    await CerrarSesion(refrescos=refrescos, tokens=tokens).ejecutar(refresh_token="inventado")


async def test_completar_datos_de_empresa_cierra_el_onboarding(empresas, publicador):
    empresa_id = EmpresaId(uuid4())
    empresa = Empresa(id=empresa_id)
    empresa.aceptar_terminos("1.0", INSTANTE_FIJO)
    await empresas.agregar(empresa)

    resultado = await CompletarDatosDeEmpresa(empresas=empresas, publicador=publicador).ejecutar(
        empresa_id=empresa_id,
        usuario_id=UsuarioId(uuid4()),
        razon_social="Panaderia Dona Rosa SRL",
        cuit=CUIT(CUIT_VALIDO),
        condicion_iva=CondicionIVA.MONOTRIBUTO,
        nombre_responsable="Rosa Gimenez",
        email_contacto=Email("rosa@panaderia.com"),
        ahora=INSTANTE_FIJO,
    )

    assert resultado.onboarding_completo is True
    assert publicador.eventos[-1].accion == "completar_datos_de_empresa"


async def test_un_cuit_ya_registrado_por_otra_empresa_es_rechazado(empresas, publicador):
    """`empresa.cuit` is unique in the DER: one company, one tax id."""
    otra = Empresa(id=EmpresaId(uuid4()))
    otra.completar_datos_fiscales(
        razon_social="Otra SRL",
        cuit=CUIT(CUIT_VALIDO),
        condicion_iva=CondicionIVA.EXENTO,
        nombre_responsable="Otro",
        email_contacto=Email("otro@x.com"),
    )
    await empresas.agregar(otra)

    empresa_id = EmpresaId(uuid4())
    await empresas.agregar(Empresa(id=empresa_id))

    with pytest.raises(CuitYaRegistrado):
        await CompletarDatosDeEmpresa(empresas=empresas, publicador=publicador).ejecutar(
            empresa_id=empresa_id,
            usuario_id=UsuarioId(uuid4()),
            razon_social="Panaderia",
            cuit=CUIT(CUIT_VALIDO),
            condicion_iva=CondicionIVA.MONOTRIBUTO,
            nombre_responsable="Rosa",
            email_contacto=Email("rosa@panaderia.com"),
            ahora=INSTANTE_FIJO,
        )


async def test_completar_una_empresa_inexistente_falla(empresas, publicador):
    with pytest.raises(InvarianteViolada):
        await CompletarDatosDeEmpresa(empresas=empresas, publicador=publicador).ejecutar(
            empresa_id=EmpresaId(uuid4()),
            usuario_id=UsuarioId(uuid4()),
            razon_social="Panaderia",
            cuit=CUIT(CUIT_VALIDO),
            condicion_iva=CondicionIVA.MONOTRIBUTO,
            nombre_responsable="Rosa",
            email_contacto=Email("rosa@panaderia.com"),
            ahora=INSTANTE_FIJO,
        )


async def test_reaceptar_terminos_actualiza_la_version(empresas, publicador):
    """HU-E1-03 RN-03."""
    empresa_id = EmpresaId(uuid4())
    empresa = Empresa(id=empresa_id)
    empresa.aceptar_terminos("1.0", INSTANTE_FIJO)
    await empresas.agregar(empresa)

    resultado = await AceptarTerminos(empresas=empresas, publicador=publicador).ejecutar(
        empresa_id=empresa_id,
        usuario_id=UsuarioId(uuid4()),
        version="2.0",
        ahora=INSTANTE_FIJO,
    )

    assert resultado.terminos is not None
    assert resultado.terminos.version == "2.0"
    assert resultado.debe_reaceptar_terminos("2.0") is False


async def test_aceptar_terminos_de_una_empresa_inexistente_falla(empresas, publicador):
    with pytest.raises(InvarianteViolada):
        await AceptarTerminos(empresas=empresas, publicador=publicador).ejecutar(
            empresa_id=EmpresaId(uuid4()),
            usuario_id=UsuarioId(uuid4()),
            version="2.0",
            ahora=INSTANTE_FIJO,
        )
