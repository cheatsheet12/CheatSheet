"""La grilla de horarios de un recurso para un servicio (HU-E7-06 y HU-E8-01).

**Una sola implementación para el panel y para el agente.** Antes cada uno cruzaba los horarios
del recurso contra los turnos con su propia copia de la lógica, y las dos marcaban «ocupado»
sólo cuando el inicio coincidía exactamente con el de un turno. Ahora la duración es la del
servicio y la ocupación es por solapamiento más intervalo (decisión D96).

Como siempre, lo que sale es una ayuda de interfaz y no una garantía: reservar puede fallar
con `FranjaOcupada` aunque acá figurara libre (decisión D28).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from cheatsheet.contexts.scheduling.application.errors import ServicioNoAdmitido
from cheatsheet.contexts.scheduling.application.ports import (
    PortCatalogoDeServicios,
    PortRepositorioRecurso,
    PortRepositorioTurno,
)
from cheatsheet.contexts.scheduling.application.recursos import VerRecurso
from cheatsheet.contexts.scheduling.application.turnos import MENSAJE_SERVICIO_NO_ADMITIDO
from cheatsheet.contexts.scheduling.domain.grilla import HorarioOfrecido, horarios_ofrecidos


class VerHorariosDisponibles:
    """Los inicios que el recurso ofrece ese día para ese servicio, con los ocupados marcados.

    Todos los roles leen. Un servicio que no es agendable o que no se presta en el recurso se
    rechaza con `ServicioNoAdmitido`, como en `ReservarTurno`: sin servicio no hay duración, y
    sin duración no hay grilla.
    """

    def __init__(
        self,
        *,
        turnos: PortRepositorioTurno,
        recursos: PortRepositorioRecurso,
        servicios: PortCatalogoDeServicios,
    ) -> None:
        self._turnos = turnos
        self._recursos = recursos
        self._servicios = servicios

    async def ejecutar(
        self, *, recurso_id: UUID, servicio_id: UUID, fecha: date, ahora: datetime
    ) -> tuple[HorarioOfrecido, ...]:
        recurso = await VerRecurso(self._recursos).ejecutar(recurso_id)
        servicio = await self._servicios.buscar_agendable(servicio_id)
        if servicio is None or not recurso.admite_servicio(servicio_id):
            raise ServicioNoAdmitido(MENSAJE_SERVICIO_NO_ADMITIDO)
        tomados = await self._turnos.ocupados_en(recurso_id, fecha)
        return horarios_ofrecidos(recurso, fecha, servicio.duracion_estandar_min, tomados, ahora)


__all__ = ["VerHorariosDisponibles"]
