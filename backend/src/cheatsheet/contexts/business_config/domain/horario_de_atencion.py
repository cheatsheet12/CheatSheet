"""El horario de atención de una empresa — cuándo una persona atiende el canal (HS-T2 RN-04).

**No es la disponibilidad de los recursos** (`PatronDeDisponibilidad`): aquella dice cuándo se
puede *reservar* un turno con un recurso; ésta, cuándo *atiende* el negocio. Pueden diferir en
los dos sentidos, y por eso se configuran aparte.

Cada día de la semana (lunes 0, como en `recurso.py`) tiene **una o más franjas** semiabiertas
`[desde, hasta)` —un horario cortado es un día con dos—, y la empresa puede cargar **fechas sin
atención** (feriados, vacaciones): ese día el negocio está cerrado las 24 horas. Todo en hora
argentina; el cálculo de «¿está abierto?» vive en `apertura.py`, y la forma JSON en
`horario_de_atencion_json.py`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from itertools import pairwise

from cheatsheet.shared.errors import EntradaInvalida

MINUTOS_POR_DIA = 24 * 60

#: Tope de cordura: un año de feriados nacionales son unos 19.
MAXIMO_DE_FECHAS_CERRADAS = 200

MENSAJE_CIERRE_ANTES_QUE_APERTURA = "La hora de cierre debe ser posterior a la de apertura."
MENSAJE_SIN_DIAS = "Indicá al menos un día con horario de atención."
MENSAJE_FORMATO_DE_HORA = "El horario debe tener el formato HH:MM."
MENSAJE_FRANJAS_SUPERPUESTAS = "Las franjas de un mismo día no pueden superponerse ni tocarse."
MENSAJE_FRANJAS_DESORDENADAS = "Las franjas de un día deben ir de la más temprana a la más tarde."
MENSAJE_DIA_INVALIDO = "El día de la semana debe estar entre 0 (lunes) y 6 (domingo)."
MENSAJE_DEMASIADAS_FECHAS = f"Podés cargar hasta {MAXIMO_DE_FECHAS_CERRADAS} fechas sin atención."

_HORA = re.compile(r"^(?:([01]\d|2[0-3]):([0-5]\d)|(24):(00))$")


class PoliticaFueraDeHorario(StrEnum):
    """Qué hace el agente cuando el negocio está cerrado (la opción (c) de I-09)."""

    #: (a), por defecto. El agente sigue atendiendo; sólo cambia el aviso de derivación.
    AGENTE_RESPONDE = "AGENTE_RESPONDE"
    #: (b). El agente no contesta y manda un mensaje fijo, una vez por período de cierre.
    MENSAJE_FIJO = "MENSAJE_FIJO"


def minutos_desde_texto(texto: str) -> int:
    """`"HH:MM"` → minutos desde la medianoche. Admite `24:00` (el fin del día)."""
    encontrado = _HORA.match(texto) if isinstance(texto, str) else None
    if encontrado is None:
        raise EntradaInvalida(MENSAJE_FORMATO_DE_HORA)
    horas, minutos, fin_horas, _ = encontrado.groups()
    if fin_horas is not None:
        return MINUTOS_POR_DIA
    return int(horas) * 60 + int(minutos)


def texto_desde_minutos(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


@dataclass(frozen=True, slots=True)
class FranjaDeAtencion:
    """Un tramo `[desde, hasta)` de un día, en minutos desde la medianoche.

    Semiabierta: a las 13:00 en punto de 09:00-13:00 el negocio ya está cerrado. No cruza la
    medianoche: un horario hasta las 2 se carga como dos días (`20:00-24:00` y `00:00-02:00`).
    """

    desde: int
    hasta: int

    def __post_init__(self) -> None:
        if not 0 <= self.desde < self.hasta <= MINUTOS_POR_DIA:
            raise EntradaInvalida(MENSAJE_CIERRE_ANTES_QUE_APERTURA)

    @classmethod
    def desde_textos(cls, desde: str, hasta: str) -> FranjaDeAtencion:
        return cls(desde=minutos_desde_texto(desde), hasta=minutos_desde_texto(hasta))

    def como_textos(self) -> tuple[str, str]:
        return (texto_desde_minutos(self.desde), texto_desde_minutos(self.hasta))


def _validar_franjas_del_dia(franjas: tuple[FranjaDeAtencion, ...]) -> None:
    for anterior, siguiente in pairwise(franjas):
        if siguiente.desde < anterior.desde:
            raise EntradaInvalida(MENSAJE_FRANJAS_DESORDENADAS)
        # `<=`: dos franjas que se tocan son una sola, y hay una única forma de escribirla.
        if siguiente.desde <= anterior.hasta:
            raise EntradaInvalida(MENSAJE_FRANJAS_SUPERPUESTAS)


@dataclass(frozen=True, slots=True)
class ConfiguracionDeAtencion:
    """El horario, las fechas sin atención y la política de una empresa.

    Valida al construirse (D24): una configuración mal formada falla acá y no a la mitad de
    un mensaje entrante. Los días sin franjas se descartan: «cerrado» es no estar en el mapa.
    """

    dias: Mapping[int, tuple[FranjaDeAtencion, ...]]
    fechas_cerradas: frozenset[date] = field(default_factory=frozenset)
    politica: PoliticaFueraDeHorario = PoliticaFueraDeHorario.AGENTE_RESPONDE

    def __post_init__(self) -> None:
        con_franjas: dict[int, tuple[FranjaDeAtencion, ...]] = {}
        for dia, franjas in self.dias.items():
            if not 0 <= dia <= 6:
                raise EntradaInvalida(MENSAJE_DIA_INVALIDO)
            _validar_franjas_del_dia(tuple(franjas))
            if franjas:
                con_franjas[dia] = tuple(franjas)
        if not con_franjas:
            raise EntradaInvalida(MENSAJE_SIN_DIAS)
        if len(self.fechas_cerradas) > MAXIMO_DE_FECHAS_CERRADAS:
            raise EntradaInvalida(MENSAJE_DEMASIADAS_FECHAS)
        object.__setattr__(self, "dias", con_franjas)

    def franjas_de(self, fecha: date) -> tuple[FranjaDeAtencion, ...]:
        """Las franjas de una fecha local: ninguna si es una fecha sin atención."""
        if fecha in self.fechas_cerradas:
            return ()
        return self.dias.get(fecha.weekday(), ())


__all__ = [
    "MAXIMO_DE_FECHAS_CERRADAS",
    "MENSAJE_CIERRE_ANTES_QUE_APERTURA",
    "MENSAJE_DEMASIADAS_FECHAS",
    "MENSAJE_DIA_INVALIDO",
    "MENSAJE_FORMATO_DE_HORA",
    "MENSAJE_FRANJAS_DESORDENADAS",
    "MENSAJE_FRANJAS_SUPERPUESTAS",
    "MENSAJE_SIN_DIAS",
    "MINUTOS_POR_DIA",
    "ConfiguracionDeAtencion",
    "FranjaDeAtencion",
    "PoliticaFueraDeHorario",
    "minutos_desde_texto",
    "texto_desde_minutos",
]
