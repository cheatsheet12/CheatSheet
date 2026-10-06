"""`elegir_horarios` — qué se le ofrece al cliente de todo lo que hay libre (T6).

Antes el agente tomaba los tres primeros libres de la grilla, así que con un recurso que abre a las
9 ofrecía siempre 9:00, 9:30 y 10:00 de mañana: nunca la tarde, nunca otro día. Acá los libres del
día se **reparten**:

- sin franja ni hora → `HORARIOS_A_OFRECER` en índices equiespaciados, que cubren mañana y tarde;
- con franja → el mismo reparto dentro de la franja;
- con hora → esa hora si está libre y, si no, las más cercanas en orden cronológico;
- con varios días → el cupo se reparte entre ellos.

Función pura, sin I/O (R1). Lo que entra ya viene filtrado por `scheduling` (futuro, no ocupado);
acá sólo se elige.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID

from cheatsheet.contexts.conversational.domain.dialogo import OpcionDeHorario
from cheatsheet.contexts.conversational.domain.pedido_de_turno import MomentoDelDia
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

#: Cuántos horarios se ofrecen de una. El prototipo PAN-WA-02 muestra cuatro.
HORARIOS_A_OFRECER = 4

#: Cuántos días hacia adelante se busca cuando lo pedido no tiene nada («alternativas cercanas»).
DIAS_DE_BUSQUEDA = 7


@dataclass(frozen=True, slots=True)
class HorarioOfrecible:
    """Un horario que el agente puede ofrecer (HU-E8-01 RN-02).

    Sale de cruzar la disponibilidad del recurso con los turnos ya tomados, del lado de
    `scheduling`. Que llegue acá ya filtrado es lo que hace que el agente **no pueda** ofrecer un
    horario que no existe.
    """

    recurso_id: UUID
    servicio_id: UUID
    inicio: datetime


def elegir_horarios(
    por_dia: Sequence[Sequence[HorarioOfrecible]],
    *,
    momento: MomentoDelDia | None = None,
    hora: time | None = None,
    limite: int = HORARIOS_A_OFRECER,
) -> list[OpcionDeHorario]:
    """Hasta `limite` opciones, una por inicio, en orden cronológico."""
    dias = [_filtrar(_agrupar(libres), momento) for libres in por_dia]
    dias = [dia for dia in dias if dia]
    elegidas: list[OpcionDeHorario] = []
    for dia, cupo in zip(dias, _repartir(limite, len(dias)), strict=True):
        elegidas.extend(_del_dia(dia, hora, cupo))
    return sorted(elegidas, key=lambda uno: uno.inicio)


def _agrupar(libres: Sequence[HorarioOfrecible]) -> list[OpcionDeHorario]:
    """Una opción por inicio, con todos los recursos que lo tienen libre."""
    recursos: dict[datetime, list[UUID]] = {}
    servicios: dict[datetime, UUID] = {}
    for uno in sorted(libres, key=lambda libre: libre.inicio):
        recursos.setdefault(uno.inicio, []).append(uno.recurso_id)
        servicios.setdefault(uno.inicio, uno.servicio_id)
    return [
        OpcionDeHorario(inicio=inicio, servicio_id=servicios[inicio], recursos=tuple(ids))
        for inicio, ids in recursos.items()
    ]


def _filtrar(
    opciones: list[OpcionDeHorario], momento: MomentoDelDia | None
) -> list[OpcionDeHorario]:
    if momento is None:
        return opciones
    return [uno for uno in opciones if momento.contiene(_hora_local(uno))]


def _repartir(limite: int, dias: int) -> list[int]:
    """El cupo de cada día: parejo, y lo que sobra, a los primeros."""
    if dias == 0:
        return []
    base, resto = divmod(limite, dias)
    return [base + (1 if indice < resto else 0) for indice in range(dias)]


def _del_dia(dia: list[OpcionDeHorario], hora: time | None, cupo: int) -> list[OpcionDeHorario]:
    if cupo <= 0:
        return []
    if hora is not None:
        return _cerca_de(dia, hora, cupo)
    if len(dia) <= cupo:
        return dia
    return [dia[indice * len(dia) // cupo] for indice in range(cupo)]


def _cerca_de(dia: list[OpcionDeHorario], hora: time, cupo: int) -> list[OpcionDeHorario]:
    exacta = [uno for uno in dia if _hora_local(uno) == hora]
    if exacta:
        return exacta[:1]
    ordenadas = sorted(
        dia, key=lambda uno: (abs(_minutos(_hora_local(uno)) - _minutos(hora)), uno.inicio)
    )
    return sorted(ordenadas[:cupo], key=lambda uno: uno.inicio)


def _hora_local(opcion: OpcionDeHorario) -> time:
    return opcion.inicio.astimezone(ZONA_ARGENTINA).time()


def _minutos(hora: time) -> int:
    return hora.hour * 60 + hora.minute


__all__ = ["DIAS_DE_BUSQUEDA", "HORARIOS_A_OFRECER", "HorarioOfrecible", "elegir_horarios"]
