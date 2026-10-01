"""El normalizador de nombres de `master_data` — HU-E4-05 RN-01 a RN-04 y RN-07.

Son funciones puras, así que se prueban sin ningún doble. Lo que importa de verdad:

- **Nunca se agregan ni se quitan tildes** (RN-01): «Maria» no pasa a «María».
- **Se preserva lo que viene con mayúsculas mezcladas** («McDonald»): solo se capitaliza
  una palabra que llega toda en mayúsculas o toda en minúsculas (RN-02).
- **Es idempotente** (RN-07): normalizar dos veces da lo mismo que normalizar una.
"""

from __future__ import annotations

import unicodedata

import pytest
from cheatsheet.contexts.master_data.domain.normalizacion import (
    limpiar_texto,
    normalizar_nombre_de_catalogo,
    normalizar_nombre_de_cliente,
    normalizar_nombre_de_persona,
    normalizar_razon_social,
)
from cheatsheet.shared.fiscal import CUIT

CUIT_DE_EMPRESA = CUIT("30712345671")
CUIT_DE_PERSONA = CUIT("20123456786")

LIMPIEZA = [
    ("  Ana   Perez ", "Ana Perez"),
    ("Ana\tPerez", "Ana Perez"),
    ("Ana\nPerez", "Ana Perez"),
    ("Ana\xa0Perez", "Ana Perez"),
    ("Ana\u2003\u2003Perez", "Ana Perez"),
    ("An\u200ba Pe\ufeffrez", "Ana Perez"),
    ("Ana\xadPerez", "AnaPerez"),
    ("An\x00a\x07 Perez", "Ana Perez"),
    ("José", "José"),
    ("   ", ""),
    ("\u200b\u200b", ""),
]

PERSONAS = [
    ("JUAN CARLOS DE LA CRUZ", "Juan Carlos de la Cruz"),
    ("MARIA DE LOS ANGELES perez  ", "Maria de los Angeles Perez"),
    ("McDonald", "McDonald"),
    ("juan De la cruz", "Juan De la Cruz"),
    ("DE LA FUENTE ANA", "De la Fuente Ana"),
    ("JOSE y MARIA E HIJOS", "Jose y Maria e Hijos"),
    ("O'BRIEN", "O'Brien"),
    ("MARIA-JOSE", "Maria-Jose"),
    ("o'brien", "O'Brien"),
    ("WhatsApp 1234", "WhatsApp 1234"),
    ("1234 -", "1234 -"),
    ("josé", "José"),
]

RAZONES_SOCIALES = [
    ("ferreteria lopez s.r.l.", "Ferreteria Lopez S.R.L."),
    ("IBM ARGENTINA SA", "IBM Argentina SA"),
    ("YPF SOCIEDAD ANONIMA", "YPF Sociedad Anonima"),
    ("SUR", "SUR"),
    ("FERRETERIA DE LA COSTA SA", "Ferreteria de la Costa SA"),
    ("DE LA COSTA SA", "De la Costa SA"),
    ("ferreteria lopez srl", "Ferreteria Lopez SRL"),
    ("lopez s.a.s.", "Lopez S.A.S."),
    ("lopez sas", "Lopez SAS"),
    ("lopez s.a.u.", "Lopez S.A.U."),
    ("lopez s.c.a.", "Lopez S.C.A."),
    ("lopez, s.a.", "Lopez, S.A."),
    ("el señor se", "El Señor Se"),
    ("transportes s.e.", "Transportes S.E."),
    ("transportes se", "Transportes Se"),
    ("transportes sc", "Transportes Sc"),
    ("McDonald S.A.", "McDonald S.A."),
]

CATALOGO = [
    ("CORTE DE PELO", "Corte de pelo"),
    ("corte", "Corte"),
    ("Corte VIP", "Corte VIP"),
    ("VIP", "Vip"),
    ("  VIP   GOLD ", "Vip gold"),
    ("1234", "1234"),
    ("Corte de Pelo", "Corte de Pelo"),
]


@pytest.mark.parametrize(("entrada", "esperado"), LIMPIEZA)
def test_limpiar_texto_rn_01(entrada: str, esperado: str) -> None:
    assert limpiar_texto(entrada) == esperado


def test_limpiar_texto_unifica_la_representacion_unicode_sin_tocar_tildes() -> None:
    nfd = unicodedata.normalize("NFD", "José")
    nfc = unicodedata.normalize("NFC", "José")

    assert nfd != nfc
    assert limpiar_texto(nfd) == limpiar_texto(nfc) == nfc


@pytest.mark.parametrize(("entrada", "esperado"), PERSONAS)
def test_nombre_de_persona_rn_02(entrada: str, esperado: str) -> None:
    assert normalizar_nombre_de_persona(entrada) == esperado


@pytest.mark.parametrize(("entrada", "esperado"), RAZONES_SOCIALES)
def test_razon_social_rn_03(entrada: str, esperado: str) -> None:
    assert normalizar_razon_social(entrada) == esperado


@pytest.mark.parametrize(
    ("cuit", "es_razon_social"),
    [
        ("30712345671", True),
        ("33693450239", True),
        ("34999032089", True),
        ("20123456786", False),
        ("27123456780", False),
        (None, False),
    ],
)
def test_el_prefijo_del_cuit_decide_razon_social_o_persona(
    cuit: str | None, es_razon_social: bool
) -> None:
    valor = CUIT(cuit) if cuit else None

    resultado = normalizar_nombre_de_cliente("FERRETERIA LOPEZ SRL", valor)

    assert resultado == ("Ferreteria Lopez SRL" if es_razon_social else "Ferreteria Lopez Srl")


def test_cliente_sin_cuit_se_trata_como_persona() -> None:
    assert normalizar_nombre_de_cliente("JUAN PEREZ", None) == "Juan Perez"
    assert normalizar_nombre_de_cliente("ferreteria lopez s.r.l.", CUIT_DE_EMPRESA) == (
        "Ferreteria Lopez S.R.L."
    )


@pytest.mark.parametrize(("entrada", "esperado"), CATALOGO)
def test_nombre_de_catalogo_rn_04(entrada: str, esperado: str) -> None:
    assert normalizar_nombre_de_catalogo(entrada) == esperado


def test_idempotencia_sobre_todo_el_corpus_rn_07() -> None:
    funciones = [
        limpiar_texto,
        normalizar_nombre_de_persona,
        normalizar_razon_social,
        normalizar_nombre_de_catalogo,
        lambda t: normalizar_nombre_de_cliente(t, CUIT_DE_EMPRESA),
        lambda t: normalizar_nombre_de_cliente(t, CUIT_DE_PERSONA),
    ]
    corpus = [e for e, _ in LIMPIEZA + PERSONAS + RAZONES_SOCIALES + CATALOGO]
    corpus += [esperado for _, esperado in PERSONAS + RAZONES_SOCIALES + CATALOGO]

    for funcion in funciones:
        for texto in corpus:
            una_vez = funcion(texto)
            assert funcion(una_vez) == una_vez, (texto, una_vez)
