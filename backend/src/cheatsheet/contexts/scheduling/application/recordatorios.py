"""`EnviarRecordatoriosDeTurno` — el barrido que recuerda los turnos próximos (HU-E8-04, HU-E11-01).

El barrido corre por empresa, cada 15 minutos. **El `ahora` decide qué le toca a la corrida**; toda
fecha que se escribe sale del reloj real (`EnvioDeRecordatorios`). Dos pasadas:

1. **Pendientes vencidos.** Una fila **en curso** cuya ventana venció pasa a `FALLIDO` `INCIERTO`
   **sin reenviar** (pudo haber salido). Una fila **esperando reintento** se descarta si el turno ya
   no está abierto, cambió de franja o ya empezó; si no, se reintenta sobre **la misma fila**.
2. **Nuevos.** Turnos abiertos que empiezan dentro de la máxima anticipación, menos los que la
   pasada 1 ya tocó (un recordatorio por turno por barrido): `que_corresponde` dice qué mandar y qué
   omitir. Las anticipaciones superadas por una más cercana quedan como filas `OMITIDO`
   (`ANTICIPACION_SUPERADA`) y nunca se mandan; la elegida va por los tres tiempos.

**Agenda apagada (Gate 1, pregunta 1).** Una regla de agenda desactivada es la decisión explícita de
no avisar: no se manda nada nuevo, no se reintenta lo que esperaba (queda `DESCARTADO`
`AGENDA_APAGADA`) y lo que estaba en curso se resuelve `INCIERTO`, sin reenviar.

**Agenda malformada (D-U8-5).** Si la fila de la regla no se puede interpretar, se deja un log
(`recordatorios_de_turno_agenda_invalida`, solo con `empresa_id` y `regla_id`) y se saltea **esa
empresa**: una fila corrupta nunca aborta el resto ni se vuelve un 422 desde un worker.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from cheatsheet.contexts.scheduling.application.envio_de_recordatorios import (
    Desenlace,
    EnvioDeRecordatorios,
)
from cheatsheet.contexts.scheduling.application.errors import AgendaDeNotificacionInvalida
from cheatsheet.contexts.scheduling.application.ports_de_recordatorios import (
    PortAgendaDeNotificacion,
    PortRepositorioRecordatoriosDeTurno,
    PortTurnosPorRecordar,
)
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    RecordatorioDeTurno,
    que_corresponde,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResultadoDeBarrido:
    """Cuántas filas terminaron cada una de las maneras. Sin datos de nadie."""

    enviados: int = 0
    fallidos: int = 0
    en_reintento: int = 0
    omitidos: int = 0
    descartados: int = 0

    @property
    def hubo_actividad(self) -> bool:
        return any(
            (self.enviados, self.fallidos, self.en_reintento, self.omitidos, self.descartados)
        )


class _Contadores:
    def __init__(self) -> None:
        self.cuentas = {desenlace: 0 for desenlace in Desenlace}

    def sumar(self, desenlace: Desenlace) -> None:
        self.cuentas[desenlace] += 1

    def resultado(self) -> ResultadoDeBarrido:
        return ResultadoDeBarrido(
            enviados=self.cuentas[Desenlace.SALIO],
            fallidos=self.cuentas[Desenlace.FALLO],
            en_reintento=self.cuentas[Desenlace.EN_REINTENTO],
            omitidos=self.cuentas[Desenlace.OMITIDO],
            descartados=self.cuentas[Desenlace.DESCARTADO],
        )


class EnviarRecordatoriosDeTurno:
    """Recuerda a los clientes los turnos que se acercan, una vez por (turno, anticipación, franja)."""

    def __init__(
        self,
        *,
        turnos: PortTurnosPorRecordar,
        recordatorios: PortRepositorioRecordatoriosDeTurno,
        agenda: PortAgendaDeNotificacion,
        envio: EnvioDeRecordatorios,
    ) -> None:
        self._turnos = turnos
        self._recordatorios = recordatorios
        self._agenda = agenda
        self._envio = envio

    async def ejecutar(self, *, empresa_id: EmpresaId, ahora: datetime) -> ResultadoDeBarrido:
        try:
            anticipaciones = await self._agenda.anticipaciones()
        except AgendaDeNotificacionInvalida as invalida:
            # Solo ids: nunca el contenido de la fila. Se saltea esta empresa, no el barrido.
            logger.warning(
                "recordatorios_de_turno_agenda_invalida",
                empresa_id=str(empresa_id),
                regla_id=str(invalida.regla_id) if invalida.regla_id is not None else None,
            )
            return ResultadoDeBarrido()
        contadores = _Contadores()
        tocados = await self._pendientes(ahora, apagada=not anticipaciones, contadores=contadores)
        if anticipaciones:
            await self._nuevos(ahora, anticipaciones, tocados, contadores)
        return contadores.resultado()

    async def _pendientes(
        self, ahora: datetime, *, apagada: bool, contadores: _Contadores
    ) -> set[UUID]:
        """Pasada 1. Devuelve los turnos que tocó, para que la pasada 2 los deje."""
        tocados: set[UUID] = set()
        for pendiente in await self._recordatorios.pendientes(ahora):
            desenlace = await self._envio.retomar(
                recordatorio_id=pendiente.id, ahora=ahora, agenda_apagada=apagada
            )
            tocados.add(pendiente.turno_id)
            contadores.sumar(desenlace)
        return tocados

    async def _nuevos(
        self,
        ahora: datetime,
        anticipaciones: tuple[int, ...],
        tocados: set[UUID],
        contadores: _Contadores,
    ) -> None:
        """Pasada 2: turnos que empiezan en `(ahora, ahora + máxima anticipación]`."""
        hasta = ahora + timedelta(minutes=max(anticipaciones))
        turnos = [
            turno
            for turno in await self._turnos.abiertos_con_inicio_entre(ahora, hasta)
            if turno.id not in tocados
        ]
        existentes = await self._existentes([turno.id for turno in turnos])
        for turno in turnos:
            plan = que_corresponde(turno, anticipaciones, existentes[turno.id], ahora)
            for omitida in plan.omitir:
                contadores.sumar(
                    await self._envio.omitir_superada(turno=turno, anticipacion_min=omitida)
                )
            if plan.enviar is not None:
                contadores.sumar(
                    await self._envio.enviar_nuevo(turno=turno, anticipacion_min=plan.enviar)
                )

    async def _existentes(self, turno_ids: list[UUID]) -> dict[UUID, list[RecordatorioDeTurno]]:
        por_turno: dict[UUID, list[RecordatorioDeTurno]] = defaultdict(list)
        for fila in await self._recordatorios.de_turnos(turno_ids):
            por_turno[fila.turno_id].append(fila)
        return por_turno


__all__ = ["EnviarRecordatoriosDeTurno", "ResultadoDeBarrido"]
