"""`Dialogo` — lo que el sistema le ofreció al cliente y está esperando que conteste.

Es la pieza que faltaba para que «el primero» reserve algo (pendiente #5 del épico 8): el agente
ofrecía horarios y no recordaba cuáles. Un solo diálogo pendiente por conversación, con su
vencimiento adentro, guardado en `conversacion.dialogo` (T2).

**Lo arma el sistema, nunca el modelo ni el cliente.** Las opciones salen de `scheduling` (los
horarios libres, los turnos del cliente) y de ellas —y sólo de ellas— salen los ids que después se
reservan o se cancelan. El texto de un cliente elige *entre* las opciones; no puede agregar una.

Value object inmutable y sin I/O (R1). El JSON de la base existe sólo en el repositorio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.conversational.domain.pedido_de_turno import PedidoDeTurno
from cheatsheet.shared.errors import InvarianteViolada

#: Cuánto vale una oferta de horarios o una pregunta de confirmación (Pregunta 4 del Gate 1).
#:
#: WhatsApp es casi sincrónico: en media hora el cliente contestó o se fue. Más tiempo aumenta el
#: riesgo de que un «sí» suelto, horas después, confirme algo que el cliente ya no tenía en mente.
VIGENCIA_DEL_DIALOGO = timedelta(minutes=30)


class PasoDelDialogo(StrEnum):
    """Qué espera el agente que el cliente conteste."""

    ELEGIR_SERVICIO = "ELEGIR_SERVICIO"
    PEDIR_CUANDO = "PEDIR_CUANDO"
    ELEGIR_HORARIO = "ELEGIR_HORARIO"
    ELEGIR_TURNO_A_CANCELAR = "ELEGIR_TURNO_A_CANCELAR"
    CONFIRMAR_CANCELACION = "CONFIRMAR_CANCELACION"


@dataclass(frozen=True, slots=True)
class OpcionDeServicio:
    id: UUID
    nombre: str


@dataclass(frozen=True, slots=True)
class OpcionDeHorario:
    """Un inicio libre. `recursos` son todos los que lo tienen libre, en el orden de prueba.

    Si el primero da `FranjaOcupada` al reservar, se prueba el siguiente antes de decirle al
    cliente que se ocupó (T6).
    """

    inicio: datetime
    servicio_id: UUID
    recursos: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class OpcionDeTurno:
    turno_id: UUID
    servicio: str
    inicio: datetime
    tiene_sena: bool


Opcion = OpcionDeServicio | OpcionDeHorario | OpcionDeTurno

#: De qué tipo son las opciones de cada paso. `PEDIR_CUANDO` no lleva ninguna.
_TIPO_DE_OPCION: dict[PasoDelDialogo, type[Opcion] | None] = {
    PasoDelDialogo.ELEGIR_SERVICIO: OpcionDeServicio,
    PasoDelDialogo.PEDIR_CUANDO: None,
    PasoDelDialogo.ELEGIR_HORARIO: OpcionDeHorario,
    PasoDelDialogo.ELEGIR_TURNO_A_CANCELAR: OpcionDeTurno,
    PasoDelDialogo.CONFIRMAR_CANCELACION: OpcionDeTurno,
}


@dataclass(frozen=True, slots=True)
class Dialogo:
    """Un paso pendiente de la conversación, con lo que hace falta para continuarlo.

    `servicio_id` y `pedido` viajan para poder seguir una reserva (preguntar el día después de
    resolver el servicio) y para volver a ofrecer cuando la oferta venció (T14).
    """

    paso: PasoDelDialogo
    abierto_en: datetime
    vence_en: datetime
    opciones: tuple[Opcion, ...] = ()
    servicio_id: UUID | None = None
    pedido: PedidoDeTurno | None = None

    def __post_init__(self) -> None:
        if self.vence_en <= self.abierto_en:
            raise InvarianteViolada("Un diálogo tiene que vencer después de abrirse")
        tipo = _TIPO_DE_OPCION[self.paso]
        if tipo is None:
            if self.opciones:
                raise InvarianteViolada("Pedir el día no lleva opciones")
            return
        if not self.opciones:
            raise InvarianteViolada("Un diálogo para elegir necesita opciones")
        if not all(isinstance(uno, tipo) for uno in self.opciones):
            raise InvarianteViolada("Las opciones no son del tipo que pide el paso")
        if self.paso is PasoDelDialogo.CONFIRMAR_CANCELACION and len(self.opciones) != 1:
            raise InvarianteViolada("Confirmar una cancelación lleva exactamente un turno")

    @classmethod
    def nuevo(
        cls,
        paso: PasoDelDialogo,
        ahora: datetime,
        *,
        opciones: tuple[Opcion, ...] = (),
        servicio_id: UUID | None = None,
        pedido: PedidoDeTurno | None = None,
    ) -> Dialogo:
        """Abre un diálogo ahora, con la vigencia de siempre."""
        return cls(
            paso=paso,
            abierto_en=ahora,
            vence_en=ahora + VIGENCIA_DEL_DIALOGO,
            opciones=opciones,
            servicio_id=servicio_id,
            pedido=pedido,
        )

    def vigente(self, ahora: datetime) -> bool:
        return ahora < self.vence_en

    @property
    def inicios(self) -> list[datetime | None]:
        """El inicio de cada opción, o `None` si la opción no tiene (un servicio)."""
        return [None if isinstance(uno, OpcionDeServicio) else uno.inicio for uno in self.opciones]

    @property
    def servicios(self) -> tuple[OpcionDeServicio, ...]:
        return tuple(uno for uno in self.opciones if isinstance(uno, OpcionDeServicio))

    @property
    def horarios(self) -> tuple[OpcionDeHorario, ...]:
        return tuple(uno for uno in self.opciones if isinstance(uno, OpcionDeHorario))

    @property
    def turnos(self) -> tuple[OpcionDeTurno, ...]:
        return tuple(uno for uno in self.opciones if isinstance(uno, OpcionDeTurno))


__all__ = [
    "VIGENCIA_DEL_DIALOGO",
    "Dialogo",
    "Opcion",
    "OpcionDeHorario",
    "OpcionDeServicio",
    "OpcionDeTurno",
    "PasoDelDialogo",
]
