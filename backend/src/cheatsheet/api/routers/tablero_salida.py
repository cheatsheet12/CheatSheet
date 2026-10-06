"""La forma HTTP del tablero (HU-E10-01), compartida por el panel y la ruta del contador.

Salió de `reporteria.py` porque ese archivo ya pasaba de las 500 líneas, y vive aparte —y no
dentro de `contador.py`— porque las dos rutas devuelven **exactamente** esta forma: dos
conversiones paralelas del mismo objeto son dos lugares donde un campo se agrega en uno solo.

Los importes viajan como **texto**, nunca como número JSON: un `float` en JSON redondea en el
cuarto decimal, que es donde vive un centavo.
"""

from __future__ import annotations

from datetime import date

from cheatsheet.contexts.reporting.application.ports import CobrosPorEstado
from cheatsheet.contexts.reporting.application.tablero import Metrica, Tablero
from pydantic import BaseModel


class MetricaSalida(BaseModel):
    """Un número del encabezado. Los importes viajan como **texto**, nunca como número JSON.

    Es la misma regla del épico 5 y del 6: un `float` en JSON redondea en el cuarto decimal,
    que es donde vive un centavo, y el frontend formatea a partir de la cadena exacta.
    """

    valor: str
    anterior: str
    #: `None` cuando el período anterior fue cero: «creció 0%» y «no hay con qué comparar» son
    #: cosas distintas, y la pantalla dibuja un guion.
    variacion: str | None


class CobrosDeUnEstadoSalida(BaseModel):
    cantidad: int
    monto: str


class TableroSalida(BaseModel):
    desde: date
    hasta: date
    facturado: MetricaSalida
    cobrado: MetricaSalida
    turnos: MetricaSalida
    operaciones: MetricaSalida
    por_tipo: dict[str, str]
    por_semana: dict[str, str]
    pendiente: str
    en_mora: str
    #: Porcentaje con dos decimales, tal como lo calcula `payments` (RN-08).
    tasa_de_cobro: str
    #: El cobrado neto por semana ISO (`2026-W09`), por fecha de pago menos lo devuelto.
    cobrado_por_semana: dict[str, str]
    #: Lo creado en el período por su estado actual. Las claves son los nombres del enum de
    #: `payments` y la etiqueta de pantalla la pone el frontend.
    cobros_por_estado: dict[str, CobrosDeUnEstadoSalida]
    sin_actividad: bool


def _a_metrica(metrica: Metrica) -> MetricaSalida:
    return MetricaSalida(
        valor=str(metrica.valor),
        anterior=str(metrica.anterior),
        variacion=str(metrica.variacion) if metrica.variacion is not None else None,
    )


def _a_cobros_de_un_estado(cobros: CobrosPorEstado) -> CobrosDeUnEstadoSalida:
    return CobrosDeUnEstadoSalida(cantidad=cobros.cantidad, monto=str(cobros.monto))


def tablero_salida(tablero: Tablero) -> TableroSalida:
    return TableroSalida(
        desde=tablero.periodo.desde,
        hasta=tablero.periodo.hasta,
        facturado=_a_metrica(tablero.facturado),
        cobrado=_a_metrica(tablero.cobrado),
        turnos=_a_metrica(tablero.turnos),
        operaciones=_a_metrica(tablero.operaciones),
        por_tipo={clave: str(valor) for clave, valor in tablero.por_tipo.items()},
        por_semana={clave: str(valor) for clave, valor in tablero.por_semana.items()},
        pendiente=str(tablero.pendiente),
        en_mora=str(tablero.en_mora),
        tasa_de_cobro=str(tablero.tasa_de_cobro),
        cobrado_por_semana={
            clave: str(valor) for clave, valor in tablero.cobrado_por_semana.items()
        },
        cobros_por_estado={
            estado: _a_cobros_de_un_estado(cobros)
            for estado, cobros in tablero.cobros_por_estado.items()
        },
        sin_actividad=tablero.sin_actividad,
    )


__all__ = [
    "CobrosDeUnEstadoSalida",
    "MetricaSalida",
    "TableroSalida",
    "tablero_salida",
]
