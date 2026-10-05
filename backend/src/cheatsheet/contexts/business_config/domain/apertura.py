"""«¿Está abierto?», «¿cuándo abre?» y «¿desde cuándo está cerrado?» — funciones puras.

Todo se calcula sobre la **hora argentina** (`ZONA_ARGENTINA`), nunca sobre UTC: entre las 21:00
y las 24:00 locales UTC ya es el día siguiente —otro día de la semana y otra fecha—, y una fecha
sin atención se compara con la fecha local. El modelo de lenguaje no participa: que el negocio
esté abierto es un cálculo, no una interpretación.

Las búsquedas recorren fecha por fecha **hasta `HORIZONTE_DIAS` (366) días** en cada sentido:
con fechas sin atención, una semana ya no alcanza, y un año entero (bisiesto incluido) son a lo
sumo 367 fechas por unas pocas franjas.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from cheatsheet.contexts.business_config.domain.horario_de_atencion import (
    ConfiguracionDeAtencion,
    FranjaDeAtencion,
    PoliticaFueraDeHorario,
)
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

HORIZONTE_DIAS = 366


@dataclass(frozen=True, slots=True)
class EstadoDeAtencion:
    """La respuesta que `ConsultarAtencion` entrega a otros contextos.

    `proxima_apertura` es `None` cuando no hay ninguna en el horizonte («sin próxima
    apertura»); `cerrado_desde` es `None` mientras el negocio está abierto.
    """

    configurado: bool
    abierto: bool
    politica: PoliticaFueraDeHorario
    proxima_apertura: datetime | None
    cerrado_desde: datetime | None


#: Sin horario configurado el negocio está «siempre abierto»: es lo que pasa hoy, y una empresa
#: que nunca entró a la pantalla no puede quedar muda de golpe.
SIEMPRE_ABIERTO = EstadoDeAtencion(
    configurado=False,
    abierto=True,
    politica=PoliticaFueraDeHorario.AGENTE_RESPONDE,
    proxima_apertura=None,
    cerrado_desde=None,
)


def _instante(fecha: date, minutos: int) -> datetime:
    """El instante local `minutos` después de la medianoche de `fecha` (1440 = la siguiente)."""
    medianoche = datetime.combine(fecha, time(0, 0), tzinfo=ZONA_ARGENTINA)
    return medianoche + timedelta(minutes=minutos)


def _franjas_hacia_adelante(
    config: ConfiguracionDeAtencion, desde: date
) -> Iterator[tuple[date, FranjaDeAtencion]]:
    for desplazamiento in range(HORIZONTE_DIAS + 1):
        fecha = desde + timedelta(days=desplazamiento)
        for franja in config.franjas_de(fecha):
            yield fecha, franja


def _franjas_hacia_atras(
    config: ConfiguracionDeAtencion, desde: date
) -> Iterator[tuple[date, FranjaDeAtencion]]:
    for desplazamiento in range(HORIZONTE_DIAS + 1):
        fecha = desde - timedelta(days=desplazamiento)
        for franja in reversed(config.franjas_de(fecha)):
            yield fecha, franja


def esta_abierto(config: ConfiguracionDeAtencion, instante: datetime) -> bool:
    """`[desde, hasta)`: a las 19:00 en punto de 09:00-19:00 ya está cerrado.

    La contigüidad de medianoche no necesita un caso especial: `20:00-24:00` del lunes y
    `00:00-02:00` del martes cubren cada una su propio día local.
    """
    local = instante.astimezone(ZONA_ARGENTINA)
    minutos = local.hour * 60 + local.minute
    return any(franja.desde <= minutos < franja.hasta for franja in config.franjas_de(local.date()))


def proxima_apertura(config: ConfiguracionDeAtencion, instante: datetime) -> datetime | None:
    """Abierto: `instante`. Cerrado: el comienzo de la próxima franja, o `None` sin ninguna.

    Cerrado, la primera franja que empieza después de `instante` es una apertura real: una que
    fuera continuación de otra contigua dejaría a `instante` dentro del tramo, es decir abierto.
    """
    if esta_abierto(config, instante):
        return instante
    local = instante.astimezone(ZONA_ARGENTINA)
    for fecha, franja in _franjas_hacia_adelante(config, local.date()):
        apertura = _instante(fecha, franja.desde)
        if apertura > instante:
            return apertura
    return None


def cerrado_desde(config: ConfiguracionDeAtencion, instante: datetime) -> datetime:
    """El último cierre anterior a `instante` (sólo tiene sentido con el negocio cerrado).

    En el hueco de un horario cortado es el cierre de la mañana; en una fecha sin atención, el
    último cierre de una fecha con atención. Sin ninguno en el horizonte devuelve el borde de la
    ventana, `instante - 366 días` («cerrado al menos desde»): siempre es un instante.
    """
    limite = instante - timedelta(days=HORIZONTE_DIAS)
    local = instante.astimezone(ZONA_ARGENTINA)
    for fecha, franja in _franjas_hacia_atras(config, local.date()):
        cierre = _instante(fecha, franja.hasta)
        if cierre <= instante:
            return max(cierre, limite)
    return limite


def estado_de_atencion(config: ConfiguracionDeAtencion, ahora: datetime) -> EstadoDeAtencion:
    abierto = esta_abierto(config, ahora)
    return EstadoDeAtencion(
        configurado=True,
        abierto=abierto,
        politica=config.politica,
        proxima_apertura=proxima_apertura(config, ahora),
        cerrado_desde=None if abierto else cerrado_desde(config, ahora),
    )


__all__ = [
    "HORIZONTE_DIAS",
    "SIEMPRE_ABIERTO",
    "EstadoDeAtencion",
    "cerrado_desde",
    "esta_abierto",
    "estado_de_atencion",
    "proxima_apertura",
]
