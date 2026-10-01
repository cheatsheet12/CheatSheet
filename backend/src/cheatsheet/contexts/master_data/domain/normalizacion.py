"""Name normalization for the master-data catalogue (HU-E4-05 RN-01 to RN-04, RN-07).

Pure functions over `str`: no clock, no I/O, no framework. They are called from the
aggregates (`Cliente`, `Servicio`, `CategoriaEmpresa`), which is the common entry point of
the panel, the spreadsheet ingestion and the WhatsApp agent, so a name is normalized once
and in one place (RN-07). Every function is **idempotent**: `f(f(x)) == f(x)`.

What is deliberately *not* done:

- Accents are never added or removed (RN-01): «Maria» does not become «María».
- A word with mixed case («McDonald», «De») is preserved: only a word that arrives all
  upper-case or all lower-case is capitalized (RN-02).
- Email, WhatsApp and CUIT are not touched here; their value objects already normalize
  them (RN-05).

Heuristics the story accepts, with their known false positives: an upper-case word of up
to four letters in a company name is kept as an acronym (IBM, YPF, and also «SUR»).

The list of company-type acronyms is closed and is meant to be validated by the team
against the primary sources (Ley General de Sociedades 19.550, Ley 27.349).
"""

from __future__ import annotations

import unicodedata

from cheatsheet.shared.fiscal import CUIT

#: RN-02: lower-case unless they open the name.
PARTICULAS = frozenset({"de", "del", "la", "las", "los", "y", "e"})

#: RN-03, compared without dots and without case. `SE` and `SC` are Spanish words, so
#: they only count as company types when they are written with dots (see below).
SIGLAS_SOCIETARIAS = frozenset(
    {
        "SA",
        "SRL",
        "SAS",
        "SAU",
        "SCA",
        "SCS",
        "SH",
        "SGR",
        "SAIC",
        "SACI",
        "SACIF",
        "SAICF",
        "SAICA",
        "SRLU",
    }
)
SIGLAS_SOLO_CON_PUNTOS = frozenset({"SE", "SC"})

#: RN-03: a CUIT starting with one of these belongs to a legal entity.
PREFIJOS_DE_RAZON_SOCIAL = frozenset({"30", "33", "34"})

#: RN-03: up to this many letters, an upper-case word is kept as an acronym.
LARGO_MAXIMO_SIGLA = 4

_PUNTUACION_ENVOLVENTE = ",;:()[]"


def limpiar_texto(texto: str) -> str:
    """RN-01: NFC, any Unicode space is a space, control and format characters are dropped.

    Then runs of spaces collapse into one and the ends are trimmed. NFC only unifies how
    the same «á» is encoded; it neither adds nor removes accents.
    """
    caracteres: list[str] = []
    for caracter in texto:
        if caracter.isspace() or unicodedata.category(caracter) in {"Zs", "Zl", "Zp"}:
            caracteres.append(" ")
        elif unicodedata.category(caracter) not in {"Cc", "Cf"}:
            caracteres.append(caracter)
    compuesto = unicodedata.normalize("NFC", "".join(caracteres))
    return " ".join(parte for parte in compuesto.split(" ") if parte)


def normalizar_nombre_de_persona(texto: str) -> str:
    """RN-01 + RN-02."""
    palabras = limpiar_texto(texto).split(" ")
    if not palabras[0]:
        return ""
    return " ".join(_palabra_de_persona(p, i) for i, p in enumerate(palabras))


def normalizar_razon_social(texto: str) -> str:
    """RN-01 + RN-03: company-type acronyms and short upper-case words are kept."""
    palabras = limpiar_texto(texto).split(" ")
    if not palabras[0]:
        return ""
    return " ".join(_palabra_de_razon_social(p, i) for i, p in enumerate(palabras))


def normalizar_nombre_de_cliente(texto: str, cuit: CUIT | None) -> str:
    """RN-03: a client is a company when its CUIT starts with 30, 33 or 34; else a person."""
    if cuit is not None and str(cuit)[:2] in PREFIJOS_DE_RAZON_SOCIAL:
        return normalizar_razon_social(texto)
    return normalizar_nombre_de_persona(texto)


def normalizar_nombre_de_catalogo(texto: str) -> str:
    """RN-01 + RN-04: only an all-upper or all-lower name gets «First letter, rest lower»."""
    limpio = limpiar_texto(texto)
    if _clase(limpio) not in {"mayusculas", "minusculas"}:
        return limpio
    resultado: list[str] = []
    primera = True
    for caracter in limpio:
        if primera and _tiene_caja(caracter):
            resultado.append(_mayuscula(caracter))
            primera = False
        else:
            resultado.append(caracter.lower())
    return "".join(resultado)


def _tiene_caja(caracter: str) -> bool:
    return caracter.isupper() or caracter.islower()


def _clase(palabra: str) -> str:
    """Measured over the letters that have case; a word without any never changes."""
    con_caja = [c for c in palabra if _tiene_caja(c)]
    if not con_caja:
        return "sin_caja"
    if all(c.isupper() for c in con_caja):
        return "mayusculas"
    if all(c.islower() for c in con_caja):
        return "minusculas"
    return "mixta"


def _mayuscula(caracter: str) -> str:
    """The title-case form of one letter, unless it expands (`"ß".title()` is `"Ss"`)."""
    titulo = caracter.title()
    return titulo if len(titulo) == 1 else caracter


def _capitalizar(palabra: str) -> str:
    """Upper-case the first letter and the one after a hyphen or apostrophe (P4)."""
    resultado: list[str] = []
    anterior_es_de_palabra = False
    for caracter in palabra:
        resultado.append(caracter.lower() if anterior_es_de_palabra else _mayuscula(caracter))
        anterior_es_de_palabra = unicodedata.category(caracter)[0] in {"L", "N", "M"}
    return "".join(resultado)


def _palabra_de_persona(palabra: str, indice: int) -> str:
    if _clase(palabra) not in {"mayusculas", "minusculas"}:
        return palabra
    if indice > 0 and palabra.lower() in PARTICULAS:
        return palabra.lower()
    return _capitalizar(palabra)


def _palabra_de_razon_social(palabra: str, indice: int) -> str:
    sigla = _como_sigla(palabra)
    if sigla is not None:
        return sigla
    letras = sum(1 for c in palabra if c.isalpha())
    es_sigla_propia = (
        _clase(palabra) == "mayusculas"
        and letras <= LARGO_MAXIMO_SIGLA
        and palabra.lower() not in PARTICULAS
    )
    return palabra if es_sigla_propia else _palabra_de_persona(palabra, indice)


def _como_sigla(palabra: str) -> str | None:
    """The word in upper-case when it is a company type, keeping its dots; else `None`."""
    nucleo = palabra.strip(_PUNTUACION_ENVOLVENTE)
    if not nucleo:
        return None
    sin_puntos = nucleo.replace(".", "").upper()
    con_puntos = "." in nucleo
    valida = sin_puntos in SIGLAS_SOCIETARIAS or (
        con_puntos and sin_puntos in SIGLAS_SOLO_CON_PUNTOS
    )
    return palabra.replace(nucleo, nucleo.upper(), 1) if valida else None
