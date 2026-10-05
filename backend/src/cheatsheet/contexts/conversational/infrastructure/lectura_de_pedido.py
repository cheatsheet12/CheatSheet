"""El `pedido_de_turno` que el intérprete devuelve: su validación y su doble.

Dos mitades, las dos del lado de la infraestructura:

- **`leer_pedido` es la tercera defensa** (ver `interprete.py`): revalida campo por campo lo que
  el esquema ya debería haber garantizado. Una salida de modelo es entrada no confiable como
  cualquier formulario (`CLAUDE.md` §5), y un pedido a medias es peor que ninguno: si algo no
  cumple, **se descarta el pedido entero** y la intención y la confianza se conservan. Sin
  pedido, el agente trata el mensaje como un pedido de reserva sin preferencias —que le ofrece
  horarios reales y nada más—, así que descartar nunca produce una acción.
- **`extraer_pedido` es el doble**: lee por palabras clave lo que haría falta para correr PRU-05
  contra el intérprete simulado de staging. Reusa el analizador determinista de
  `respuesta_del_cliente` para horas y días de la semana.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import time
from typing import Any

from cheatsheet.contexts.conversational.domain.pedido_de_turno import (
    AccionDeTurno,
    Cuando,
    MomentoDelDia,
    PedidoDeTurno,
    ReferenciaDeDia,
)
from cheatsheet.contexts.conversational.domain.respuesta_del_cliente import leer_respuesta
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.errors import EntradaInvalida

logger = obtener_logger(__name__)

_CLAVES_DEL_PEDIDO = frozenset({"accion", "cuandos", "momento", "hora", "servicio"})
_CLAVES_DEL_CUANDO = frozenset({"referencia", "dia_semana", "dia", "mes"})
_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def leer_pedido(crudo: Any) -> PedidoDeTurno | None:
    """El pedido validado, o `None` si no vino o no cumple. Nunca levanta."""
    if crudo is None:
        return None
    try:
        return _construir(crudo)
    except (KeyError, TypeError, ValueError, EntradaInvalida):
        logger.warning("interprete_devolvio_un_pedido_invalido")
        return None


def _construir(crudo: Any) -> PedidoDeTurno:
    if not isinstance(crudo, dict) or not set(crudo) <= _CLAVES_DEL_PEDIDO:
        raise ValueError("el pedido no tiene la forma del esquema")
    cuandos = crudo.get("cuandos", [])
    if not isinstance(cuandos, list):
        raise TypeError("`cuandos` tiene que ser una lista")
    momento = crudo.get("momento")
    servicio = crudo.get("servicio")
    if servicio is not None and not isinstance(servicio, str):
        raise TypeError("`servicio` tiene que ser texto")
    return PedidoDeTurno(
        accion=AccionDeTurno(crudo["accion"]),
        cuandos=tuple(_cuando(uno) for uno in cuandos),
        momento=None if momento is None else MomentoDelDia(momento),
        hora=_hora(crudo.get("hora")),
        servicio=servicio,
    )


def _cuando(crudo: Any) -> Cuando:
    if not isinstance(crudo, dict) or not set(crudo) <= _CLAVES_DEL_CUANDO:
        raise ValueError("el día no tiene la forma del esquema")
    return Cuando(
        referencia=ReferenciaDeDia(crudo["referencia"]),
        dia_semana=_entero(crudo.get("dia_semana")),
        dia=_entero(crudo.get("dia")),
        mes=_entero(crudo.get("mes")),
    )


def _entero(valor: Any) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError("se esperaba un entero")
    return int(valor)


def _hora(valor: Any) -> time | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise TypeError("la hora tiene que ser texto")
    encontrada = _HORA.fullmatch(valor)
    if encontrada is None:
        raise ValueError("la hora no es HH:MM")
    return time(int(encontrada.group(1)), int(encontrada.group(2)))


# -- el doble ---------------------------------------------------------------------------

_REPROGRAMAR = ("reprogram", "reagend", "cambiar mi turno", "cambiar el turno", "mover mi turno")
_CANCELAR = ("cancel", "no voy a poder", "no puedo ir", "no puedo asistir", "no llego")
_MES_POR_NOMBRE = {
    nombre: numero
    for numero, nombre in enumerate(
        (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ),
        1,
    )
}
_FECHA_CON_BARRA = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")
_FECHA_CON_NOMBRE = re.compile(rf"\b(\d{{1,2}}) de ({'|'.join(_MES_POR_NOMBRE)})\b")
_MANANA_DEL_DIA = re.compile(r"(?<!la )\bmanana\b")
_FRANJA_DE_LA_MANANA = re.compile(r"\b(?:a|de|por|en) la manana\b|\btemprano\b")


def extraer_pedido(texto: str) -> PedidoDeTurno:
    """Lo que el doble entiende de un pedido de turno. Conservador, por palabras clave."""
    limpio = _sin_tildes(texto)
    lectura = leer_respuesta(texto)
    cuandos = _referencias_relativas(limpio)
    cuandos += [Cuando(ReferenciaDeDia.DIA_DE_SEMANA, dia_semana=d) for d in lectura.dias_semana]
    cuandos += _fechas(limpio)
    return PedidoDeTurno(
        accion=_accion(limpio),
        cuandos=tuple(cuandos[:3]),
        momento=_momento(limpio),
        hora=lectura.horas[0] if lectura.horas else None,
    )


def _accion(texto: str) -> AccionDeTurno:
    if any(clave in texto for clave in _REPROGRAMAR):
        return AccionDeTurno.REPROGRAMAR
    if any(clave in texto for clave in _CANCELAR):
        return AccionDeTurno.CANCELAR
    return AccionDeTurno.RESERVAR


def _referencias_relativas(texto: str) -> list[Cuando]:
    encontradas: list[Cuando] = []
    if re.search(r"\bhoy\b", texto):
        encontradas.append(Cuando(ReferenciaDeDia.HOY))
    sin_pasado = texto.replace("pasado manana", " ")
    if sin_pasado != texto:
        encontradas.append(Cuando(ReferenciaDeDia.PASADO_MANANA))
    if _MANANA_DEL_DIA.search(sin_pasado):
        encontradas.append(Cuando(ReferenciaDeDia.MANANA))
    return sorted(encontradas, key=lambda uno: list(ReferenciaDeDia).index(uno.referencia))


def _fechas(texto: str) -> list[Cuando]:
    candidatas = [(int(dia), int(mes)) for dia, mes in _FECHA_CON_BARRA.findall(texto)] + [
        (int(dia), _MES_POR_NOMBRE[mes]) for dia, mes in _FECHA_CON_NOMBRE.findall(texto)
    ]
    return [
        Cuando(ReferenciaDeDia.FECHA, dia=dia, mes=mes)
        for dia, mes in candidatas
        if 1 <= dia <= 31 and 1 <= mes <= 12
    ]


def _momento(texto: str) -> MomentoDelDia | None:
    if re.search(r"\btarde\b", texto):
        return MomentoDelDia.TARDE
    if re.search(r"\bnoche\b", texto):
        return MomentoDelDia.NOCHE
    if _FRANJA_DE_LA_MANANA.search(texto):
        return MomentoDelDia.MANANA
    return None


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(letra for letra in descompuesto if not unicodedata.combining(letra))


__all__ = ["extraer_pedido", "leer_pedido"]
