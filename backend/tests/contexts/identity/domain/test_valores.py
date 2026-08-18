"""The value objects of identity — above all, the CUIT.

The check-digit test is the one that earns its place: `cliente.cuit` and
`comprobante.receptor_cuit` will reuse this class, so a wrong digit accepted here ends
up on a document ARCA rejects, in epic 5, with money already committed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.identity.domain.valores import (
    CUIT,
    Email,
    HashDeContrasena,
    TerminosAceptados,
    validar_contrasena_en_claro,
)
from cheatsheet.shared.errors import EntradaInvalida

from tests.contexts.identity.conftest import CUIT_INVALIDO, CUIT_VALIDO


def test_un_cuit_con_digito_verificador_correcto_es_valido():
    assert CUIT(CUIT_VALIDO).valor == CUIT_VALIDO


def test_un_cuit_con_digito_verificador_incorrecto_es_rechazado():
    with pytest.raises(EntradaInvalida, match="digito verificador"):
        CUIT(CUIT_INVALIDO)


@pytest.mark.parametrize(
    "escrito", ["30-71234567-1", "30 71234567 1", "30.71234567.1", CUIT_VALIDO]
)
def test_un_cuit_se_normaliza_sin_separadores(escrito: str):
    """The user types it the way their accountant writes it. All of them are the same id."""
    assert CUIT(escrito).valor == CUIT_VALIDO


@pytest.mark.parametrize("escrito", ["3071234567", "307123456712", "", "abcdefghijk"])
def test_un_cuit_que_no_tiene_once_digitos_es_rechazado(escrito: str):
    with pytest.raises(EntradaInvalida):
        CUIT(escrito)


def test_el_cuit_se_muestra_formateado():
    assert CUIT(CUIT_VALIDO).formateado == "30-71234567-1"
    assert str(CUIT(CUIT_VALIDO)) == CUIT_VALIDO


def test_dos_emails_que_solo_difieren_en_mayusculas_son_el_mismo():
    """HU-E1-01 RN-03 would be trivially bypassable otherwise."""
    assert Email("Ana@Empresa.COM") == Email("ana@empresa.com")


@pytest.mark.parametrize("escrito", ["sin-arroba", "@sindominio.com", "ana@", "ana@sin punto", ""])
def test_un_email_mal_formado_es_rechazado(escrito: str):
    with pytest.raises(EntradaInvalida):
        Email(escrito)


def test_el_email_se_normaliza_sin_espacios():
    assert str(Email("  ana@empresa.com  ")) == "ana@empresa.com"


def test_una_contrasena_de_menos_de_ocho_caracteres_es_rechazada():
    """HU-E1-01 RN-01."""
    with pytest.raises(EntradaInvalida, match="8 caracteres"):
        validar_contrasena_en_claro("corta12")


def test_una_contrasena_de_ocho_caracteres_alcanza():
    """RN-01 says eight and nothing else. Adding rules nobody asked for is hostile."""
    assert validar_contrasena_en_claro("12345678") == "12345678"


def test_el_hash_nunca_se_muestra():
    """An Argon2 digest in a log line is material for an offline attack."""
    hash_real = "$argon2id$v=19$m=19456,t=2,p=1$c2FsdA$aG91c2U"
    envuelto = HashDeContrasena(hash_real)

    assert str(envuelto) == "***"
    assert repr(envuelto) == "HashDeContrasena(***)"
    assert hash_real not in f"{envuelto!r} {envuelto}"
    # The real value is still reachable for whoever legitimately needs it.
    assert envuelto.valor == hash_real


def test_un_hash_vacio_es_rechazado():
    with pytest.raises(EntradaInvalida):
        HashDeContrasena("   ")


def test_los_terminos_exigen_version_y_fecha_con_zona():
    """HU-E1-03 RN-01: a date without a version proves nothing."""
    with pytest.raises(EntradaInvalida, match="version"):
        TerminosAceptados(version="  ", fecha=datetime.now(UTC))
    with pytest.raises(EntradaInvalida, match="zona horaria"):
        TerminosAceptados(version="1.0", fecha=datetime(2026, 8, 14))  # noqa: DTZ001
