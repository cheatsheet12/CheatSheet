"""Los casos de uso del horario de atención (HS-T2 RN-04, HU-E11-01).

**Sólo el Administrador escribe**, con el guarda en el caso de uso (PRU-09). **`ConsultarAtencion`
es el Open Host Service**: `conversational` pregunta «¿está abierto?» y recibe un
`EstadoDeAtencion`, nunca una fila ni el JSONB. Sin comprobar rol, por la misma razón que
`ConsultarReglasVigentes`: quien llama es otro contexto actuando por una empresa.

Viven acá y no en `reglas.py`, que otras unidades también agrandan.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from cheatsheet.contexts.business_config.application.ports import PortRepositorioReglas
from cheatsheet.contexts.business_config.application.reglas import _exigir_administrador
from cheatsheet.contexts.business_config.domain.apertura import (
    HORIZONTE_DIAS,
    SIEMPRE_ABIERTO,
    EstadoDeAtencion,
    estado_de_atencion,
)
from cheatsheet.contexts.business_config.domain.horario_de_atencion import (
    ConfiguracionDeAtencion,
)
from cheatsheet.contexts.business_config.domain.horario_de_atencion_json import (
    VERSION,
    como_json,
    desde_json,
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
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA


class ConfigurarHorarioDeAtencion:
    """Define o reemplaza el horario de atención de una empresa.

    **Reemplaza en vez de acumular**, como `ConfigurarEscalamiento`: una empresa tiene un
    horario, no un catálogo. Guardar reactiva una regla apagada. Al guardar **descarta las
    fechas sin atención anteriores a `hoy - 366 días`**: ningún cálculo puede alcanzarlas, y así
    la lista no crece sin fin (las pasadas más recientes se conservan: una fecha de ayer sí
    importa para «desde cuándo está cerrado»).
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
        configuracion: ConfiguracionDeAtencion,
        ahora: datetime,
        prioridad: int = 0,
    ) -> ReglaDeNegocio:
        _exigir_administrador(rol)

        podada = _sin_fechas_vencidas(configuracion, ahora)
        existentes = await self._reglas.listar(TipoRegla.HORARIO_DE_ATENCION)
        regla = existentes[0] if existentes else None

        if regla is None:
            regla = ReglaDeNegocio(
                id=uuid4(),
                empresa_id=empresa_id,
                tipo=TipoRegla.HORARIO_DE_ATENCION,
                configuracion=como_json(podada),
                created_at=ahora,
                prioridad=prioridad,
            )
            await self._reglas.agregar(regla)
            accion = "alta_regla_de_horario_de_atencion"
        else:
            regla.reconfigurar(como_json(podada), ahora)
            regla.prioridad = prioridad
            regla.activar(ahora)
            await self._reglas.guardar(regla)
            accion = "editar_regla_de_horario_de_atencion"

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


def _sin_fechas_vencidas(
    configuracion: ConfiguracionDeAtencion, ahora: datetime
) -> ConfiguracionDeAtencion:
    hoy = ahora.astimezone(ZONA_ARGENTINA).date()
    limite = hoy - timedelta(days=HORIZONTE_DIAS)
    vigentes = frozenset(fecha for fecha in configuracion.fechas_cerradas if fecha >= limite)
    return replace(configuracion, fechas_cerradas=vigentes)


class ConsultarAtencion:
    """El Open Host Service: el estado de atención de la empresa para `ahora`.

    Sin regla configurada, o con la regla desactivada, la empresa está «siempre abierta»
    (`SIEMPRE_ABIERTO`): es lo que pasa hoy, y que una regla desactivada «deja de aplicarse de
    inmediato» (HU-E11-01 RN-04) no necesita un caso especial. **No hay horario por defecto**:
    inventarle uno a una empresa cambiaría el comportamiento de su agente sin que nadie lo
    haya pedido.
    """

    def __init__(self, reglas: PortRepositorioReglas) -> None:
        self._reglas = reglas

    async def ejecutar(self, *, empresa_id: EmpresaId, ahora: datetime) -> EstadoDeAtencion:
        del empresa_id  # RLS ya acotó el repositorio a la empresa.
        candidatas = await self._reglas.listar(TipoRegla.HORARIO_DE_ATENCION)
        elegida = resolver(candidatas, TipoRegla.HORARIO_DE_ATENCION)
        if elegida is None:
            return SIEMPRE_ABIERTO
        return estado_de_atencion(elegida.interpretada_como_atencion(), ahora)


def configuracion_de_atencion_desde(crudo: dict[str, Any]) -> ConfiguracionDeAtencion:
    """Traduce lo que llega del formulario. La validación es del dominio."""
    return desde_json({"version": VERSION, **crudo})


__all__ = [
    "ConfigurarHorarioDeAtencion",
    "ConsultarAtencion",
    "configuracion_de_atencion_desde",
]
