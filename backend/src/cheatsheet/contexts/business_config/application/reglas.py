"""Los casos de uso de HU-E11-01 — las reglas parametrizables de una empresa.

**Sólo el Administrador escribe.** Es el actor de la historia, y no es una restricción
decorativa: la regla de escalamiento decide cuántos mensajes recibe un cliente por una deuda,
y la política de turnos decide qué pasa con una seña. El guarda vive en el caso de uso y no
sólo en el router, por lo que enseñó PRU-09.

**`ConsultarReglasVigentes` es el Open Host Service de este contexto** (ADR-0003). `payments`
pregunta cuál es la cadena de recordatorios y recibe una configuración tipada, nunca una fila:
la prioridad, el estado activo y el JSONB son cosas de acá.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from cheatsheet.contexts.business_config.application.errors import ReglaInexistente
from cheatsheet.contexts.business_config.application.ports import PortRepositorioReglas
from cheatsheet.contexts.business_config.domain.regla import (
    ESCALAMIENTO_POR_DEFECTO,
    ConfiguracionDeEscalamiento,
    ReglaDeNegocio,
    ReglasVigentes,
    TipoRegla,
    resolver,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

MOTIVO_SOLO_ADMIN = "Solo un Administrador puede configurar las reglas de negocio"


def _exigir_administrador(rol: RolUsuario) -> None:
    if rol is not RolUsuario.ADMINISTRADOR:
        raise EntradaInvalida(MOTIVO_SOLO_ADMIN)


class ListarReglas:
    """PAN-CFG-RN. Todas las de la empresa, con su tipo, prioridad y estado (RN-01)."""

    def __init__(self, reglas: PortRepositorioReglas) -> None:
        self._reglas = reglas

    async def ejecutar(self, tipo: TipoRegla | None = None) -> list[ReglaDeNegocio]:
        return await self._reglas.listar(tipo)


class ConfigurarEscalamiento:
    """Define o reemplaza la cadena de recordatorios de una empresa (RN-02).

    **Reemplaza en vez de acumular.** Una empresa tiene una cadena de escalamiento, no un
    catálogo de cadenas: si cada guardado creara una fila nueva, la resolución por prioridad
    tendría que desempatar entre versiones de lo mismo y la pantalla mostraría cinco reglas
    donde hay una. Crear una segunda regla de este tipo es algo que la pantalla no ofrece y
    que este caso de uso no hace.
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
        configuracion: ConfiguracionDeEscalamiento,
        ahora: datetime,
        prioridad: int = 0,
    ) -> ReglaDeNegocio:
        _exigir_administrador(rol)

        existentes = await self._reglas.listar(TipoRegla.ESCALAMIENTO_DE_COBRO)
        regla = existentes[0] if existentes else None

        if regla is None:
            regla = ReglaDeNegocio(
                id=uuid4(),
                empresa_id=empresa_id,
                tipo=TipoRegla.ESCALAMIENTO_DE_COBRO,
                configuracion=configuracion.como_json(),
                created_at=ahora,
                prioridad=prioridad,
            )
            await self._reglas.agregar(regla)
            accion = "alta_regla_de_escalamiento"
        else:
            regla.reconfigurar(configuracion.como_json(), ahora)
            regla.prioridad = prioridad
            # Guardar reactiva: alguien que edita una regla apagada está queriendo usarla, y
            # dejarla apagada sería guardar algo que no tiene efecto sin decirlo.
            regla.activar(ahora)
            await self._reglas.guardar(regla)
            accion = "editar_regla_de_escalamiento"

        await self._publicar(regla, usuario_id=usuario_id, ahora=ahora, accion=accion)
        return regla

    async def _publicar(
        self, regla: ReglaDeNegocio, *, usuario_id: UsuarioId, ahora: datetime, accion: str
    ) -> None:
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


class CambiarEstadoDeRegla:
    """RN-04 — desactivar deja de aplicar de inmediato, sin tocar lo ya procesado."""

    def __init__(self, *, reglas: PortRepositorioReglas, publicador: PublicadorDeEventos) -> None:
        self._reglas = reglas
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        regla_id: UUID,
        activa: bool,
        ahora: datetime,
    ) -> ReglaDeNegocio:
        _exigir_administrador(rol)

        regla = await self._reglas.buscar_por_id(regla_id)
        if regla is None:
            raise ReglaInexistente("La regla de negocio no existe")

        if activa:
            regla.activar(ahora)
        else:
            regla.desactivar(ahora)
        await self._reglas.guardar(regla)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.BUSINESS_CONFIG,
                accion="activar_regla" if activa else "desactivar_regla",
                entidad_afectada=f"ReglaDeNegocio:{regla.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return regla


class ConsultarReglasVigentes:
    """El Open Host Service: qué reglas rigen ahora, resueltas por prioridad (RN-05).

    **No comprueba rol**, por la misma razón que `ObtenerTicketDeAcceso` no comprueba
    ninguno: el llamador es otro contexto actuando por una empresa, y quien le pidió *a él*
    es donde vive la autorización.

    Sin regla configurada devuelve el default, y lo dice (`configurada=False`). Devolver
    «nada» obligaría a cada consumidor a decidir qué hacer sin cadena, y HS-T3 tiene como
    precondición que exista una: una empresa que nunca entró a PAN-CFG-RN no puede quedarse
    sin recordatorios y sin enterarse.
    """

    def __init__(self, reglas: PortRepositorioReglas) -> None:
        self._reglas = reglas

    async def ejecutar(self, *, empresa_id: EmpresaId) -> ReglasVigentes:
        del empresa_id  # RLS ya acotó el repositorio a la empresa.
        candidatas = await self._reglas.listar(TipoRegla.ESCALAMIENTO_DE_COBRO)
        elegida = resolver(candidatas, TipoRegla.ESCALAMIENTO_DE_COBRO)
        if elegida is None:
            return ReglasVigentes(escalamiento=ESCALAMIENTO_POR_DEFECTO, configurada=False)
        return ReglasVigentes(
            escalamiento=elegida.interpretada_como_escalamiento(), configurada=True
        )


def configuracion_desde(crudo: dict[str, Any]) -> ConfiguracionDeEscalamiento:
    """Traduce lo que llega del formulario. La validación es del dominio.

    Está acá y no en el router porque el mensaje que produce —«Los días de escalamiento deben
    ser mayores a cero.»— es texto de la historia, y quien lo escribe es el value object.
    """
    return ConfiguracionDeEscalamiento.desde_json(crudo)


__all__ = [
    "MOTIVO_SOLO_ADMIN",
    "CambiarEstadoDeRegla",
    "ConfigurarEscalamiento",
    "ConsultarReglasVigentes",
    "ListarReglas",
    "configuracion_desde",
]
