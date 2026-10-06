"""The real Argon2id and the real JWT — exercised once, here.

Everywhere else uses fakes: Argon2 is *designed* to cost 19 MiB and two passes, which is
right in production and absurd in a test that only wants to know whether a use case
compared the right two things.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cheatsheet.contexts.identity.domain.valores import HashDeContrasena
from cheatsheet.contexts.identity.infrastructure.oauth_google import (
    ConfiguracionOAuthGoogle,
    ProveedorOAuthGoogle,
)
from cheatsheet.contexts.identity.infrastructure.seguridad import (
    EmisorDeTokensJWT,
    HasherArgon2,
    decodificar_acceso,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

SECRETO = "fake-secret-for-tests"
#: Anchored to the real clock: a JWT carries `exp`, so a hard-coded instant makes the
#: test start failing on a date nobody chose.
AHORA = datetime.now(UTC)


@pytest.fixture(scope="module")
def hasher() -> HasherArgon2:
    """Module-scoped: building the parameter table twice buys nothing."""
    return HasherArgon2()


def test_el_hash_no_es_reversible(hasher: HasherArgon2):
    resultado = hasher.hashear("una-contrasena-larga")

    assert "una-contrasena-larga" not in resultado.valor
    assert resultado.valor.startswith("$argon2id$")


def test_la_contrasena_correcta_verifica(hasher: HasherArgon2):
    guardado = hasher.hashear("una-contrasena-larga")

    assert hasher.verificar("una-contrasena-larga", guardado) is True


def test_la_contrasena_incorrecta_no_verifica(hasher: HasherArgon2):
    guardado = hasher.hashear("una-contrasena-larga")

    assert hasher.verificar("otra-contrasena", guardado) is False


def test_dos_hashes_de_la_misma_contrasena_son_distintos(hasher: HasherArgon2):
    """The salt is per hash. Equal digests would make a rainbow table worth building."""
    primero = hasher.hashear("una-contrasena-larga")
    segundo = hasher.hashear("una-contrasena-larga")

    assert primero.valor != segundo.valor


def test_un_hash_corrupto_no_explota(hasher: HasherArgon2):
    """A malformed digest is "no", not an exception the sign-in flow has to know about."""
    assert hasher.verificar("cualquiera", HashDeContrasena("no-es-un-hash")) is False


def _emisor() -> EmisorDeTokensJWT:
    return EmisorDeTokensJWT(secreto=SECRETO, vida_acceso=timedelta(minutes=15))


def test_el_access_token_lleva_empresa_usuario_y_rol():
    usuario_id, empresa_id = UsuarioId(uuid4()), EmpresaId(uuid4())

    token = _emisor().emitir_acceso(
        usuario_id=usuario_id, empresa_id=empresa_id, rol="ADMINISTRADOR", ahora=AHORA
    )

    datos = decodificar_acceso(token.valor, SECRETO)
    assert datos["sub"] == str(usuario_id)
    assert datos["empresa_id"] == str(empresa_id)
    assert datos["rol"] == "ADMINISTRADOR"


def test_un_token_firmado_con_otro_secreto_es_rechazado():
    token = _emisor().emitir_acceso(
        usuario_id=UsuarioId(uuid4()), empresa_id=EmpresaId(uuid4()), rol="OPERADOR", ahora=AHORA
    )

    with pytest.raises(jwt.PyJWTError):
        decodificar_acceso(token.valor, "otro-secreto-falso")


def test_un_token_vencido_es_rechazado():
    emisor = EmisorDeTokensJWT(secreto=SECRETO, vida_acceso=timedelta(minutes=-1))
    token = emisor.emitir_acceso(
        usuario_id=UsuarioId(uuid4()), empresa_id=EmpresaId(uuid4()), rol="OPERADOR", ahora=AHORA
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decodificar_acceso(token.valor, SECRETO)


def test_un_secreto_vacio_no_arranca():
    """Failing at construction beats signing tokens the world can forge."""
    with pytest.raises(ValueError, match="JWT_SECRET"):
        EmisorDeTokensJWT(secreto="  ", vida_acceso=timedelta(minutes=15))


def test_cada_refresh_es_distinto_e_impredecible():
    emisor = _emisor()

    emitidos = {emisor.emitir_refresh(AHORA).valor for _ in range(50)}

    assert len(emitidos) == 50
    assert all(len(valor) >= 32 for valor in emitidos)


def test_el_hash_del_refresh_es_estable_y_no_contiene_el_token():
    emisor = _emisor()
    token = emisor.emitir_refresh(AHORA).valor

    huella = emisor.hashear_refresh(token)

    assert huella == emisor.hashear_refresh(token)
    assert token not in huella
    assert len(huella) == 64  # SHA-256 in hex


def test_la_url_de_google_pide_solo_email_y_perfil():
    """HU-E1-01 RN-02: CheatSheet does not reach any other part of the account."""
    proveedor = ProveedorOAuthGoogle(
        ConfiguracionOAuthGoogle(
            client_id="un-client-id",
            client_secret="fake-secret-for-tests",
            redirect_uri="https://app.cheatsheet.test/callback",
        )
    )

    url = proveedor.url_de_autorizacion("un-state-aleatorio")

    assert "scope=openid+email+profile" in url
    assert "state=un-state-aleatorio" in url
    assert "response_type=code" in url
