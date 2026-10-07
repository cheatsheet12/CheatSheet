"""El uso de una FAQ: cada respuesta enviada con ella, y lo que se mide con eso (ADR-0012).

Un `UsoDeFAQ` es un hecho inmutable: el agente contestó con esa FAQ y el mensaje salió. Lo que
la pantalla muestra —«Este mes», «Mes anterior», «Total» y la participación antes y después de
la última edición— se **calcula** sobre esos hechos; nada se incrementa.

Todo lo de este módulo es puro: sin I/O ni framework (R1). Los límites de los meses vienen de
`shared.zona_horaria.MesCalendario`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId

#: Hasta cuántos días mira la participación antes y después de la edición (ADR-0012, punto 6).
VENTANA_MAXIMA_DE_COMPARACION = timedelta(days=30)

_UN_DIA = timedelta(days=1)
_UN_DECIMAL = Decimal("0.1")
_CIEN = Decimal(100)


@dataclass(frozen=True, slots=True)
class UsoDeFAQ:
    """Una respuesta con FAQ que salió por WhatsApp."""

    id: UUID
    empresa_id: EmpresaId
    faq_id: UUID
    #: El saliente que llevó la respuesta. Es único: un mensaje es a lo sumo un uso.
    mensaje_id: UUID
    usado_en: datetime


@dataclass(frozen=True, slots=True)
class ConteoDeUsos:
    """Los usos de una FAQ por período."""

    este_mes: int
    mes_anterior: int
    #: Todos los usos registrados como eventos. No incluye la línea de base (`usos_anteriores`).
    desde_el_seguimiento: int

    def total(self, usos_anteriores: int) -> int:
        """El total desde la creación: la línea de base sin fecha más los eventos."""
        return usos_anteriores + self.desde_el_seguimiento


SIN_USOS = ConteoDeUsos(este_mes=0, mes_anterior=0, desde_el_seguimiento=0)


class MotivoSinComparacion(StrEnum):
    """Por qué no se puede comparar antes y después de la edición (HU-E9-04 RN-07)."""

    SIN_EDICIONES = "SIN_EDICIONES"
    EDICION_RECIENTE = "EDICION_RECIENTE"
    SIN_HISTORIA_PREVIA = "SIN_HISTORIA_PREVIA"


@dataclass(frozen=True, slots=True)
class Lapso:
    """Un intervalo semiabierto `[desde, hasta)`."""

    desde: datetime
    hasta: datetime


@dataclass(frozen=True, slots=True)
class VentanaDeComparacion:
    """Dos lapsos de la misma cantidad de días a cada lado de la edición."""

    dias: int
    antes: Lapso
    despues: Lapso


def ventana_de_comparacion(
    *, editada_en: datetime | None, seguimiento_desde: datetime, ahora: datetime
) -> VentanaDeComparacion | MotivoSinComparacion:
    """`L` = el menor entre 30 días, los días enteros desde la edición y los previos a ella.

    Los «días previos» se cuentan desde que se empezó a registrar usos de esa FAQ: antes de eso
    no hay eventos, y comparar contra un lapso vacío sería inventar un cero.
    """
    if editada_en is None:
        return MotivoSinComparacion.SIN_EDICIONES
    desde_la_edicion = (ahora - editada_en) // _UN_DIA
    if desde_la_edicion < 1:
        return MotivoSinComparacion.EDICION_RECIENTE
    previos = (editada_en - seguimiento_desde) // _UN_DIA
    if previos < 1:
        return MotivoSinComparacion.SIN_HISTORIA_PREVIA
    dias = min(VENTANA_MAXIMA_DE_COMPARACION // _UN_DIA, desde_la_edicion, previos)
    largo = timedelta(days=dias)
    return VentanaDeComparacion(
        dias=dias,
        antes=Lapso(editada_en - largo, editada_en),
        despues=Lapso(editada_en, editada_en + largo),
    )


@dataclass(frozen=True, slots=True)
class Participacion:
    """Los usos de una FAQ sobre todas las respuestas con FAQ de la empresa en un lapso."""

    usos: int
    total: int

    @property
    def porcentaje(self) -> Decimal | None:
        """Con un decimal, `ROUND_HALF_UP`. `None` si la empresa no respondió con ninguna FAQ.

        No es dinero, pero un porcentaje que se redondea distinto en dos lugares es el mismo
        problema: se usa la regla del resto del sistema.
        """
        if self.total == 0:
            return None
        return (Decimal(self.usos) * _CIEN / Decimal(self.total)).quantize(
            _UN_DECIMAL, rounding=ROUND_HALF_UP
        )


__all__ = [
    "SIN_USOS",
    "VENTANA_MAXIMA_DE_COMPARACION",
    "ConteoDeUsos",
    "Lapso",
    "MotivoSinComparacion",
    "Participacion",
    "UsoDeFAQ",
    "VentanaDeComparacion",
    "ventana_de_comparacion",
]
