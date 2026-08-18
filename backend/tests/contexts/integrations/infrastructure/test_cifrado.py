"""AES-256-GCM at rest — cases 4 and 5 of the plan."""

from __future__ import annotations

import base64

import pytest
from cheatsheet.contexts.integrations.domain.valores import CredencialCifrada
from cheatsheet.contexts.integrations.infrastructure.cifrado import (
    ALGORITMO,
    CifradoAesGcm,
    ClaveDeCifradoInvalida,
    CredencialIlegible,
    generar_clave,
)

CERTIFICADO = b"-----BEGIN CERTIFICATE-----\nno es real\n-----END CERTIFICATE-----"


@pytest.fixture
def cifrador() -> CifradoAesGcm:
    return CifradoAesGcm(generar_clave())


def test_cifrar_y_descifrar_devuelve_el_original(cifrador: CifradoAesGcm) -> None:
    credencial = cifrador.cifrar(CERTIFICADO)

    assert cifrador.descifrar(credencial) == CERTIFICADO
    assert credencial.algoritmo == ALGORITMO


def test_el_ciphertext_no_contiene_el_plano(cifrador: CifradoAesGcm) -> None:
    """The one property the whole column exists for."""
    credencial = cifrador.cifrar(CERTIFICADO)

    assert CERTIFICADO not in credencial.contenido
    assert b"CERTIFICATE" not in credencial.contenido


def test_dos_cifrados_del_mismo_plano_difieren(cifrador: CifradoAesGcm) -> None:
    """The nonce is random per encryption, not derived from the row.

    A nonce derived from `(empresa_id, sistema)` would repeat on every reconnection, and
    a repeated nonce under one key breaks GCM outright.
    """
    primero = cifrador.cifrar(CERTIFICADO)
    segundo = cifrador.cifrar(CERTIFICADO)

    assert primero.contenido != segundo.contenido


def test_un_ciphertext_alterado_no_autentica(cifrador: CifradoAesGcm) -> None:
    """Why GCM and not a bare cipher: tampering raises instead of yielding garbage."""
    credencial = cifrador.cifrar(CERTIFICADO)
    alterado = bytearray(credencial.contenido)
    alterado[-1] ^= 0x01

    with pytest.raises(CredencialIlegible, match="no autentica"):
        cifrador.descifrar(
            CredencialCifrada(contenido=bytes(alterado), algoritmo=credencial.algoritmo)
        )


def test_otra_clave_no_puede_leer(cifrador: CifradoAesGcm) -> None:
    credencial = cifrador.cifrar(CERTIFICADO)
    otro = CifradoAesGcm(generar_clave())

    with pytest.raises(CredencialIlegible):
        otro.descifrar(credencial)


def test_un_algoritmo_desconocido_es_rechazado(cifrador: CifradoAesGcm) -> None:
    """What a future rotation to `/v2` relies on: unknown generations fail loudly."""
    credencial = cifrador.cifrar(CERTIFICADO)

    with pytest.raises(CredencialIlegible, match="Algoritmo desconocido"):
        cifrador.descifrar(
            CredencialCifrada(contenido=credencial.contenido, algoritmo="AES-256-GCM/v9")
        )


def test_una_credencial_mas_corta_que_el_nonce_es_rechazada(cifrador: CifradoAesGcm) -> None:
    with pytest.raises(CredencialIlegible, match="nonce"):
        cifrador.descifrar(CredencialCifrada(contenido=b"corto", algoritmo=ALGORITMO))


@pytest.mark.parametrize(
    "clave",
    [
        "no-es-base64!!",
        base64.b64encode(b"demasiado corta").decode(),
        base64.b64encode(b"x" * 64).decode(),
    ],
)
def test_una_clave_mal_formada_falla_al_construir(clave: str) -> None:
    """At construction, so a misconfigured deployment fails at boot and not at first use."""
    with pytest.raises(ClaveDeCifradoInvalida):
        CifradoAesGcm(clave)


def test_generar_clave_produce_una_clave_usable() -> None:
    cifrador = CifradoAesGcm(generar_clave())

    assert cifrador.descifrar(cifrador.cifrar(b"x")) == b"x"
