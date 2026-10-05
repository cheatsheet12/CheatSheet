"""Cómo se lee lo que el cliente contesta a una oferta del agente (T3 del plan de la unidad).

**Un analizador determinista y no el modelo.** Con un diálogo vigente, «el primero», «a las 10:30»
o «sí» se resuelven acá, sin llamar al intérprete: cero tokens, ningún dato al proveedor, y ninguna
acción con efecto que dependa de una salida de modelo (D38, `CLAUDE.md` §5). Si el mensaje no se
resuelve sin ambigüedad, sigue el camino normal del intérprete: el cliente pudo cambiar de tema.

Como en `pedido_de_persona.py`, la lista es **cerrada y con límites de palabra**, y se diseña para
equivocarse hacia el lado seguro: un falso negativo termina en una repregunta o en el intérprete;
un falso positivo reserva o cancela algo que nadie pidió. Por eso una afirmación es un mensaje que
**es** un «sí» (más cortesías), no uno que lo contiene: «si hay más tarde» pregunta, no confirma.

Función pura, sin I/O ni framework (R1).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time

from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

#: «El último».
ULTIMO = -1

_ORDINALES_EN_PALABRAS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(?:primer[oa]?|1ro|1ra|1ero)\b"), 1),
    (re.compile(r"\b(?:segund[oa]|2do|2da)\b"), 2),
    (re.compile(r"\b(?:tercer[oa]?|3ro|3ra|3ero)\b"), 3),
    (re.compile(r"\b(?:cuart[oa]|4to|4ta)\b"), 4),
    (re.compile(r"\bultim[oa]\b"), ULTIMO),
)
#: Sólo el número, con la puntuación que lo acompaña: «2», «2.», «2)».
_SOLO_UN_NUMERO = re.compile(r"^\s*(\d{1,2})\s*[.)!]*\s*$")
#: «el 2», «la 3», «opción 3», «número 4». **No** si lo sigue algo que lo vuelve hora o fecha.
_NUMERO_ANUNCIADO = re.compile(
    r"\b(?:el|la|opcion|numero|nro|n°|#)\s*#?\s*(\d{1,2})\b(?![:./]\d)(?!\s*(?:hs|hrs|h\b|horas|y\s|de\s))"
)

_MERIDIANO = r"(?:\s+(?:de\s+la\s+)?(?P<meridiano>manana|tarde|noche)\b)?"
#: «10:30», «10.30», «10 y media», «17 hs», «5 de la tarde».
_HORA_MARCADA = re.compile(
    r"(?<![\d/:.])(?P<h>\d{1,2})"
    r"(?:[:.](?P<m>[0-5]\d)(?![\d:])"
    r"|\s+y\s+(?P<fraccion>media|cuarto)\b"
    r"|\s*(?:hs|hrs|h|horas)\b"
    r"|(?=\s+de\s+la\s+(?:manana|tarde|noche)\b))" + _MERIDIANO
)
#: «a las 5», «el de las 16», «las 5 de la tarde».
_A_LAS = re.compile(r"\blas\s+(?P<h>\d{1,2})\b(?![:.]\d)" + _MERIDIANO)

_DIAS_DE_LA_SEMANA: tuple[tuple[str, int], ...] = (
    ("lunes", 0),
    ("martes", 1),
    ("miercoles", 2),
    ("jueves", 3),
    ("viernes", 4),
    ("sabado", 5),
    ("domingo", 6),
)

#: Un mensaje es una afirmación si **todas** sus palabras son de esta lista y alguna es un «sí».
_SI = frozenset({"si", "sii", "sip", "dale", "ok", "okey", "okay", "confirmo", "confirmado"})
_SI |= frozenset({"confirmar", "listo", "perfecto", "claro", "bueno", "vale", "genial"})
_CORTESIAS = frozenset(
    {"gracias", "por", "favor", "porfa", "de", "acuerdo", "supuesto", "eso", "es", "mejor"}
)
_NO = frozenset({"no", "nop", "nope", "ninguno", "ninguna", "nada"})
_OTRO_MOMENTO = re.compile(r"\botr[oa]\s+(?:dia|fecha|horario|momento)\b")
_PALABRAS = re.compile(r"[a-z0-9]+")
#: Más largo que esto no es un «sí» suelto: es una frase.
_MAXIMO_DE_PALABRAS = 6


@dataclass(frozen=True, slots=True)
class RespuestaDelCliente:
    """Lo que el mensaje del cliente dice, sin interpretar a qué opción se refiere.

    `horas` trae las lecturas posibles de la hora, la más plausible primero: «a las 5» es 17:00 o
    05:00; una agenda de atención rara vez ofrece las 5 de la madrugada.
    """

    ordinal: int | None = None
    horas: tuple[time, ...] = ()
    dias_semana: tuple[int, ...] = ()
    afirma: bool = False
    niega: bool = False


@dataclass(frozen=True, slots=True)
class Unica:
    indice: int


@dataclass(frozen=True, slots=True)
class Ambigua:
    """Más de una opción coincide: hay que repreguntar."""


@dataclass(frozen=True, slots=True)
class FueraDeRango:
    """Un número que no corresponde a ninguna opción."""


@dataclass(frozen=True, slots=True)
class NoEsEleccion:
    """El mensaje no elige nada: sigue el camino normal del intérprete."""


@dataclass(frozen=True, slots=True)
class HoraNoOfrecida:
    """Pidió una hora que no estaba entre las opciones. `hora` es su lectura más plausible."""

    hora: time


Eleccion = Unica | Ambigua | FueraDeRango | NoEsEleccion | HoraNoOfrecida


def leer_respuesta(texto: str) -> RespuestaDelCliente:
    """Lee un mensaje corto contra la lista cerrada. Nunca levanta."""
    limpio = _sin_tildes(texto)
    palabras = _PALABRAS.findall(limpio)
    si, no = _afirma(palabras), _niega(palabras, limpio)
    return RespuestaDelCliente(
        ordinal=_ordinal(limpio),
        horas=_horas(limpio),
        dias_semana=_dias_de_la_semana(limpio),
        afirma=si and not no,
        niega=no and not si,
    )


def elegir(inicios: Sequence[datetime | None], respuesta: RespuestaDelCliente) -> Eleccion:
    """Cuál de las opciones eligió. `inicios` trae el inicio de cada una, o `None` si no tiene."""
    if respuesta.ordinal is not None:
        indice = len(inicios) - 1 if respuesta.ordinal == ULTIMO else respuesta.ordinal - 1
        return Unica(indice) if 0 <= indice < len(inicios) else FueraDeRango()
    if not any(inicio is not None for inicio in inicios):
        return NoEsEleccion()
    if respuesta.horas:
        coinciden = _coinciden(inicios, respuesta)
        if not coinciden:
            return HoraNoOfrecida(respuesta.horas[0])
        return Unica(coinciden[0]) if len(coinciden) == 1 else Ambigua()
    if respuesta.dias_semana:
        coinciden = _coinciden(inicios, respuesta)
        if not coinciden:
            # Otro día: es un pedido nuevo, lo lee el intérprete.
            return NoEsEleccion()
        return Unica(coinciden[0]) if len(coinciden) == 1 else Ambigua()
    return NoEsEleccion()


def _coinciden(inicios: Sequence[datetime | None], respuesta: RespuestaDelCliente) -> list[int]:
    indices: list[int] = []
    for indice, inicio in enumerate(inicios):
        if inicio is None:
            continue
        local = inicio.astimezone(ZONA_ARGENTINA)
        if respuesta.horas and local.time().replace(second=0, microsecond=0) not in respuesta.horas:
            continue
        if respuesta.dias_semana and local.weekday() not in respuesta.dias_semana:
            continue
        indices.append(indice)
    return indices


def _ordinal(texto: str) -> int | None:
    for patron, valor in _ORDINALES_EN_PALABRAS:
        if patron.search(texto):
            return valor
    for patron in (_SOLO_UN_NUMERO, _NUMERO_ANUNCIADO):
        encontrado = patron.search(texto)
        if encontrado is not None:
            return int(encontrado.group(1))
    return None


def _horas(texto: str) -> tuple[time, ...]:
    lecturas: list[time] = []
    for patron in (_HORA_MARCADA, _A_LAS):
        for encontrado in patron.finditer(texto):
            for hora in _lecturas(encontrado):
                if hora not in lecturas:
                    lecturas.append(hora)
    return tuple(lecturas)


def _lecturas(encontrado: re.Match[str]) -> list[time]:
    """Las horas que un mismo mención puede querer decir, la más plausible primero."""
    hora = int(encontrado.group("h"))
    if hora > 23:
        return []
    grupos = encontrado.groupdict()
    minuto = int(grupos.get("m") or 0)
    if grupos.get("fraccion"):
        minuto = 30 if grupos["fraccion"] == "media" else 15
    meridiano = grupos.get("meridiano")
    if meridiano in ("tarde", "noche"):
        return [time(hora + 12 if hora < 12 else hora, minuto)]
    if meridiano == "manana" or hora == 0 or hora >= 12:
        return [time(hora, minuto)]
    # Sin aclarar, de 1 a 11 puede ser de mañana o de tarde. Hasta las 7 se lee de tarde primero.
    de_tarde, de_manana = time(hora + 12, minuto), time(hora, minuto)
    return [de_tarde, de_manana] if hora <= 7 else [de_manana, de_tarde]


def _dias_de_la_semana(texto: str) -> tuple[int, ...]:
    encontrados = [
        (encontrado.start(), numero)
        for nombre, numero in _DIAS_DE_LA_SEMANA
        if (encontrado := re.search(rf"\b{nombre}\b", texto)) is not None
    ]
    return tuple(numero for _, numero in sorted(encontrados))


def _afirma(palabras: list[str]) -> bool:
    return (
        0 < len(palabras) <= _MAXIMO_DE_PALABRAS
        and any(palabra in _SI for palabra in palabras)
        and all(palabra in _SI or palabra in _CORTESIAS for palabra in palabras)
    )


def _niega(palabras: list[str], texto: str) -> bool:
    if _OTRO_MOMENTO.search(texto) is not None:
        return True
    return (
        0 < len(palabras) <= _MAXIMO_DE_PALABRAS
        and any(palabra in _NO for palabra in palabras)
        and all(palabra in _NO or palabra in _CORTESIAS for palabra in palabras)
    )


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(letra for letra in descompuesto if not unicodedata.combining(letra))


__all__ = [
    "ULTIMO",
    "Ambigua",
    "Eleccion",
    "FueraDeRango",
    "HoraNoOfrecida",
    "NoEsEleccion",
    "RespuestaDelCliente",
    "Unica",
    "elegir",
    "leer_respuesta",
]
