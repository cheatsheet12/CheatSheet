"""Los casos de uso de la agenda de notificación (HU-E11-01, HU-E8-04 RN-02).

**Sólo el Administrador escribe**, con el guarda en el caso de uso (PRU-09).
**`ConsultarAgendaDeNotificacion` es el Open Host Service**: `scheduling` pregunta «¿con qué
anticipación se recuerda?» y recibe una `AgendaVigente`, nunca una fila ni el JSONB. Sin comprobar
rol: quien llama es otro contexto actuando por una empresa. Tiene consulta propia y no engorda
`ReglasVigentes`.

Viven acá y no en `reglas.py`, que otras unidades también agrandan (el criterio de `atencion.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from cheatsheet.contexts.business_config.application.ports import PortRepositorioReglas
from cheatsheet.contexts.business_config.application.reglas import _exigir_administrador
from cheatsheet.contexts.business_config.domain.agenda_de_notificacion import (
    AGENDA_POR_DEFECTO,
    ConfiguracionDeAgenda,
)
from cheatsheet.contexts.business_config.domain.regla import (
    ReglaDeNegocio,
    TipoRegla,
    resolver,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario


class ConfigurarAgendaDeNotificacion:
    """Define o reemplaza la agenda de notificación de una empresa.

    **Reemplaza en vez de acumular**, como `ConfigurarHorarioDeAtencion`: una empresa tiene una
    agenda, no un catálogo. Guardar reactiva una regla apagada.
    """

    def __init__(self, *, reglas: PortRepositorioReglas, publicador: PublicadorDeEventos) -> None:
        self._reglas = reglas
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        configuracion: ConfiguracionDeAgenda,
        ahora: datetime,
        prioridad: int = 0,
    ) -> ReglaDeNegocio:
        _exigir_administrador(rol)

        existentes = await self._reglas.listar(TipoRegla.AGENDA_DE_NOTIFICACION)
        regla = existentes[0] if existentes else None

        if regla is None:
            regla = ReglaDeNegocio(
                id=uuid4(),
                empresa_id=empresa_id,
                tipo=TipoRegla.AGENDA_DE_NOTIFICACION,
                configuracion=configuracion.como_json(),
                created_at=ahora,
                prioridad=prioridad,
            )
            await self._reglas.agregar(regla)
            accion = "alta_regla_de_agenda"
        else:
            regla.cambiar_prioridad(prioridad)  # valida antes de tocar nada
            regla.reconfigurar(configuracion.como_json(), ahora)
            regla.activar(ahora)
            await self._reglas.guardar(regla)
            accion = "editar_regla_de_agenda"

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=regla.empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.BUSINESS_CONFIG,
                accion=accion,
                entidad_afectada=f"ReglaDeNegocio:{regla.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return regla


@dataclass(frozen=True, slots=True)
class AgendaVigente:
    """Lo que un consumidor de otro contexto recibe: la respuesta, no las filas.

    `anticipaciones_min` va de mayor a menor y está **vacía cuando los recordatorios están
    apagados**. `configurada` es `False` sólo cuando rige el default porque nunca se configuró.
    """

    anticipaciones_min: tuple[int, ...]
    configurada: bool


class ConsultarAgendaDeNotificacion:
    """El Open Host Service: con qué anticipaciones se recuerda un turno a esta empresa.

    - **Sin ninguna regla** de agenda: `AGENDA_POR_DEFECTO` (24 h) y `configurada=False`.
    - **Con reglas activas**: gana la de mayor prioridad (RN-05).
    - **Con reglas, todas desactivadas**: agenda vacía, los recordatorios están apagados. Es una
      decisión explícita del negocio de no avisar y no vuelve en silencio al default (Gate 1 del
      08/10): cada mensaje de plantilla de Meta tiene costo.
    """

    def __init__(self, reglas: PortRepositorioReglas) -> None:
        self._reglas = reglas

    async def ejecutar(self, *, empresa_id: EmpresaId) -> AgendaVigente:
        del empresa_id  # RLS ya acotó el repositorio a la empresa.
        candidatas = await self._reglas.listar(TipoRegla.AGENDA_DE_NOTIFICACION)
        if not candidatas:
            return AgendaVigente(AGENDA_POR_DEFECTO.anticipaciones_min, configurada=False)
        elegida = resolver(candidatas, TipoRegla.AGENDA_DE_NOTIFICACION)
        if elegida is None:
            return AgendaVigente((), configurada=True)
        return AgendaVigente(elegida.interpretada_como_agenda().anticipaciones_min, True)


def configuracion_de_agenda_desde(crudo: dict[str, Any]) -> ConfiguracionDeAgenda:
    """Traduce lo que llega del formulario. La validación es del dominio."""
    return ConfiguracionDeAgenda.desde_json(crudo)


__all__ = [
    "AgendaVigente",
    "ConfigurarAgendaDeNotificacion",
    "ConsultarAgendaDeNotificacion",
    "configuracion_de_agenda_desde",
]
