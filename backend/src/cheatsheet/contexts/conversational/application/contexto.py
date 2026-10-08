"""Lo que comparten los pasos de una conversación sobre turnos.

`ContextoDelMensaje` junta lo que cada paso necesita saber del mensaje que se está procesando
—la empresa, el hilo, el cliente, a quién contestarle y qué hora es— para que reservar, cancelar
y el agente no se pasen seis parámetros sueltos de mano en mano.

`Desenlace` es lo que un paso devuelve: qué texto le llegó al cliente y, si hay que escalar, por
qué. **Escalar no lo decide el paso**: lo hace el agente (`ProcesarMensajeEntrante._escalar`), que
es quien tiene los repositorios de escalamiento. El paso sólo dice «esto necesita una persona».
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.domain.conversacion import Conversacion
from cheatsheet.shared.auditoria import EventoAuditable, Iniciador, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA


@dataclass(frozen=True, slots=True)
class ContextoDelMensaje:
    """El mensaje que se está procesando, en el vocabulario de los pasos de turnos."""

    empresa_id: EmpresaId
    conversacion: Conversacion
    cliente_id: UUID
    telefono: str
    ahora: datetime

    @property
    def hoy(self) -> date:
        """El día **de Argentina**: entre las 21:00 y las 24:00 locales, UTC ya cambió de día."""
        return self.ahora.astimezone(ZONA_ARGENTINA).date()

    @property
    def hora_local(self) -> time:
        return self.ahora.astimezone(ZONA_ARGENTINA).time()


@dataclass(frozen=True, slots=True)
class Desenlace:
    """Cómo terminó un paso: lo que se le dijo al cliente y, si hace falta, por qué escalar."""

    texto: str | None
    escalar_por: str | None = None


def evento_del_agente(
    contexto: ContextoDelMensaje, *, accion: str, entidad: str, resultado: Resultado
) -> EventoAuditable:
    """HS-T2 RN-05 y T12: lo que el agente hace por su cuenta se marca con **iniciador IA**.

    Es la marca que hace contestable «qué hizo el agente solo» en el panel de auditoría.
    """
    return EventoAuditable(
        evento_id=uuid4(),
        empresa_id=contexto.empresa_id,
        ocurrido_en=contexto.ahora,
        modulo=Modulo.CONVERSATIONAL,
        accion=accion,
        entidad_afectada=entidad,
        resultado=resultado,
        iniciador=Iniciador.IA,
    )


__all__ = ["ContextoDelMensaje", "Desenlace", "evento_del_agente"]
