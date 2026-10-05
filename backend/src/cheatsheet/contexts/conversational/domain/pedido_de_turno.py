"""`PedidoDeTurno` — lo que el cliente pidió sobre un turno, y para cuándo.

El modelo **extrae** este pedido y nada más: no sabe qué día es hoy y no se le dice (T5 del plan
de la unidad). Devuelve referencias relativas —«jueves», «mañana», «el 14»— tal como las dijo el
cliente, y es `resolver_dias` la que las convierte en fechas, con el `hoy` en hora argentina que
le pasa quien llama. Calcular fechas en un modelo es el tipo de cosa que sale bien casi siempre y
mal justo cuando el cliente se va a quedar sin turno.

Todo acá es una lista cerrada o un rango, y se **revalida** apenas se construye: una salida del
modelo es entrada no confiable como cualquier formulario (`CLAUDE.md` §5).

Función pura, sin I/O ni framework (R1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import StrEnum

from cheatsheet.shared.errors import EntradaInvalida

#: «Jueves o viernes» son dos; más de tres es una lista que nadie quiere recorrer.
MAXIMO_DE_CUANDOS = 3

#: Largo máximo del nombre de servicio que se extrae. **Sólo se usa para comparar** con el
#: catálogo, nunca como dato de una acción.
LARGO_MAXIMO_DEL_SERVICIO = 60


class AccionDeTurno(StrEnum):
    """Qué quiere hacer el cliente con un turno. Sub-acción de la intención `TURNO` (T1)."""

    RESERVAR = "RESERVAR"
    CANCELAR = "CANCELAR"
    REPROGRAMAR = "REPROGRAMAR"


class ReferenciaDeDia(StrEnum):
    HOY = "HOY"
    MANANA = "MANANA"
    PASADO_MANANA = "PASADO_MANANA"
    DIA_DE_SEMANA = "DIA_DE_SEMANA"
    FECHA = "FECHA"


class MomentoDelDia(StrEnum):
    """La franja del día que el cliente prefiere. Los límites son horas locales."""

    MANANA = "MANANA"
    TARDE = "TARDE"
    NOCHE = "NOCHE"

    def contiene(self, hora: time) -> bool:
        desde, hasta = _RANGOS[self]
        return desde <= hora.hour < hasta


#: `[desde, hasta)` en horas locales: mañana hasta las 13, tarde hasta las 20, noche el resto.
_RANGOS: dict[MomentoDelDia, tuple[int, int]] = {
    MomentoDelDia.MANANA: (0, 13),
    MomentoDelDia.TARDE: (13, 20),
    MomentoDelDia.NOCHE: (20, 24),
}


@dataclass(frozen=True, slots=True)
class Cuando:
    """Un día pedido, como lo dijo el cliente.

    `dia_semana` va de 0 (lunes) a 6 (domingo), la misma numeración que `date.weekday()`.
    """

    referencia: ReferenciaDeDia
    dia_semana: int | None = None
    dia: int | None = None
    mes: int | None = None

    def __post_init__(self) -> None:
        if self.referencia is ReferenciaDeDia.DIA_DE_SEMANA and not _entre(self.dia_semana, 0, 6):
            raise EntradaInvalida("Un día de la semana va de 0 a 6")
        if self.referencia is ReferenciaDeDia.FECHA:
            if not _entre(self.dia, 1, 31):
                raise EntradaInvalida("El día de una fecha va de 1 a 31")
            if self.mes is not None and not _entre(self.mes, 1, 12):
                raise EntradaInvalida("El mes de una fecha va de 1 a 12")


@dataclass(frozen=True, slots=True)
class PedidoDeTurno:
    """Lo que el modelo entendió de un pedido de turno. **Sin efecto**: sólo orienta la búsqueda."""

    accion: AccionDeTurno
    cuandos: tuple[Cuando, ...] = ()
    momento: MomentoDelDia | None = None
    hora: time | None = None
    servicio: str | None = None

    def __post_init__(self) -> None:
        if len(self.cuandos) > MAXIMO_DE_CUANDOS:
            raise EntradaInvalida(f"Un pedido nombra a lo sumo {MAXIMO_DE_CUANDOS} días")
        if self.servicio is not None and len(self.servicio) > LARGO_MAXIMO_DEL_SERVICIO:
            raise EntradaInvalida("El nombre del servicio es demasiado largo")

    @property
    def sin_dia_ni_hora(self) -> bool:
        """`True` cuando el cliente no dijo ni un día ni una hora: hay que preguntarle el día."""
        return not self.cuandos and self.hora is None


@dataclass(frozen=True, slots=True)
class DiasPedidos:
    """Las fechas futuras que el pedido nombra, y si nombró alguna que ya pasó (CA6)."""

    fechas: tuple[date, ...]
    paso_alguna: bool


def resolver_dias(pedido: PedidoDeTurno, hoy: date, ahora_local: time | None = None) -> DiasPedidos:
    """Convierte las referencias del pedido en fechas, con `hoy` en hora argentina.

    - Un día de la semana es su **próxima ocurrencia**, y hoy cuenta.
    - Un día del mes sin mes es la próxima ocurrencia de ese número.
    - Un día **y** mes que ya pasaron son pasado (CA6): no se salta al año siguiente, porque
      quien escribe «el 2 de octubre» en octubre casi nunca habla del año que viene.
    - Una hora de hoy anterior a `ahora_local` también es pasado.
    - Una fecha imposible («31 de febrero») se ignora sin decir que pasó.
    """
    fechas: set[date] = set()
    paso = False
    for cuando in pedido.cuandos:
        fecha, ya_paso = _resolver(cuando, hoy)
        paso = paso or ya_paso
        if fecha is not None:
            fechas.add(fecha)
    hora_ya_paso = pedido.hora is not None and ahora_local is not None and pedido.hora < ahora_local
    if hora_ya_paso and hoy in fechas:
        fechas.discard(hoy)
        paso = True
    return DiasPedidos(fechas=tuple(sorted(fechas)), paso_alguna=paso)


def _resolver(cuando: Cuando, hoy: date) -> tuple[date | None, bool]:
    """`(fecha, paso)`: la fecha futura, o `None` y si fue porque ya pasó."""
    referencia = cuando.referencia
    if referencia is ReferenciaDeDia.HOY:
        return hoy, False
    if referencia is ReferenciaDeDia.MANANA:
        return hoy + timedelta(days=1), False
    if referencia is ReferenciaDeDia.PASADO_MANANA:
        return hoy + timedelta(days=2), False
    if referencia is ReferenciaDeDia.DIA_DE_SEMANA:
        faltan = ((cuando.dia_semana or 0) - hoy.weekday()) % 7
        return hoy + timedelta(days=faltan), False
    return _resolver_fecha(cuando, hoy)


def _resolver_fecha(cuando: Cuando, hoy: date) -> tuple[date | None, bool]:
    dia = cuando.dia or 1
    if cuando.mes is not None:
        try:
            fecha = date(hoy.year, cuando.mes, dia)
        except ValueError:
            return None, False
        return (fecha, False) if fecha >= hoy else (None, True)
    # Sin mes: la próxima ocurrencia de ese número. Un año alcanza para encontrarla (hay
    # meses de 31 días todos los trimestres).
    anio, mes = hoy.year, hoy.month
    for _ in range(12):
        try:
            candidata: date | None = date(anio, mes, dia)
        except ValueError:
            candidata = None
        if candidata is not None and candidata >= hoy:
            return candidata, False
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return None, False


def _entre(valor: int | None, minimo: int, maximo: int) -> bool:
    return valor is not None and minimo <= valor <= maximo


__all__ = [
    "LARGO_MAXIMO_DEL_SERVICIO",
    "MAXIMO_DE_CUANDOS",
    "AccionDeTurno",
    "Cuando",
    "DiasPedidos",
    "MomentoDelDia",
    "PedidoDeTurno",
    "ReferenciaDeDia",
    "resolver_dias",
]
