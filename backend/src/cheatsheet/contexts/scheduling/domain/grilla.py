"""La grilla de inicios que se ofrece, con los ocupados marcados (decisión D96).

Es **una sola implementación** para el panel y para el agente de WhatsApp: antes cada uno
cruzaba los horarios del recurso contra los turnos con su propia copia de la lógica, y las dos
decían «ocupado» sólo cuando el inicio coincidía exactamente con el de un turno.

Pura y sin reloj propio: `ahora` llega de afuera, como en el resto del dominio.

**`ocupado` es una ayuda, no una garantía.** Quien decide si dos turnos conviven es la base
(`excl_turno_recurso_franja` y `excl_turno_recurso_intervalo`, decisión D28); `Turno.bloquea`
aplica el mismo criterio para que la pantalla no ofrezca lo que el motor va a rechazar.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from cheatsheet.contexts.scheduling.domain.recurso import RecursoReservable
from cheatsheet.contexts.scheduling.domain.turno import Turno


@dataclass(frozen=True, slots=True)
class HorarioOfrecido:
    """Un inicio posible y si ya está tomado por un turno o por su margen."""

    inicio: datetime
    ocupado: bool


def horarios_ofrecidos(
    recurso: RecursoReservable,
    fecha: date,
    duracion_min: int,
    ocupados: Iterable[Turno],
    ahora: datetime,
) -> tuple[HorarioOfrecido, ...]:
    """Los inicios de `fecha` para un turno de `duracion_min`, con la ocupación marcada.

    Los inicios salen de `RecursoReservable.horarios_del_dia` (paso del slot, el turno entra en
    la franja). Se descartan los anteriores a `ahora` (D95; uno igual a `ahora` se ofrece) y se
    marca ocupado el que algún turno `bloquea` con el intervalo **actual** del recurso.
    """
    tomados = tuple(ocupados)
    intervalo = recurso.intervalo_entre_turnos_min
    return tuple(
        HorarioOfrecido(
            inicio=momento,
            ocupado=any(uno.bloquea(momento, duracion_min, intervalo) for uno in tomados),
        )
        for momento in recurso.horarios_del_dia(fecha, duracion_min)
        if momento >= ahora
    )
