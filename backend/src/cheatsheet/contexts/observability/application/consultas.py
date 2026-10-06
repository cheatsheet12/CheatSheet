"""Reading the audit log — the metric of epic 9 and the panel of HU-E12-01 / HU-E12-02.

The log is written by a subscriber that nobody calls directly; this is the other half — the
part that answers questions about it. Four of them, and no more:

- **how many operations happened in a period**, one of the four dashboard metrics of
  HU-E10-01 RN-02;
- **which ones**, filtered by date, module, outcome, initiator and free text (HU-E12-01 RN-03);
- **one of them in detail**, with what it recorded about itself (HU-E12-02 RN-01);
- **the timeline of the thing it happened to**, which is the part worth explaining:

  > **The timeline is the log itself, filtered by entity.** HU-E12-02 asks for «el timeline de
  > ejecución con sus pasos internos», and every step already wrote a row — `validar`,
  > `enviar_a_arca`, `autorizar` — all of them naming the same `entidad_afectada`. Building a
  > second table of steps would mean writing every step twice and having two versions of what
  > happened, which is the one thing an audit trail may not have. The duration is the distance
  > between the first row and the last (RN-03).

Everything here is a read. Nothing in this module can write, and the port it uses still has no
`actualizar` and no `eliminar`: HS-T5 RN-03 makes these records immutable, and reading them
does not change that.

No `empresa_id` filter appears anywhere: Row-Level Security already scopes the statement, and
a second copy of that rule in the application layer is a copy that can drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from cheatsheet.contexts.observability.application.errors import (
    AccesoALaBitacoraDenegado,
    OperacionInexistente,
)
from cheatsheet.contexts.observability.application.ports import (
    FiltrosDeBitacora,
    PortRegistroDeAuditoria,
)
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.shared.roles import RolUsuario

#: HU-E12-01, palabra por palabra, para el estado vacío de PAN-LOG-01.
MENSAJE_SIN_OPERACIONES = "No hay operaciones para los filtros seleccionados."

MOTIVO_SIN_ACCESO = "El rol Solo Lectura no accede a la bitácora de operaciones"


def _exigir_acceso(rol: RolUsuario) -> None:
    """HU-E12-01 RN-05 y HU-E12-02 RN-04. Ver `AccesoALaBitacoraDenegado`."""
    if rol not in (RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR):
        raise AccesoALaBitacoraDenegado(MOTIVO_SIN_ACCESO)


class ListarOperaciones:
    """PAN-LOG-01. Los registros del filtro, del más nuevo al más viejo."""

    def __init__(self, registros: PortRegistroDeAuditoria) -> None:
        self._registros = registros

    async def ejecutar(
        self, filtros: FiltrosDeBitacora | None = None, *, rol: RolUsuario | None = None
    ) -> list[RegistroDeAuditoria]:
        """El rol es opcional porque hay **un** llamador que no es una persona: el reporte de
        operaciones del épico 9, que ya comprobó el permiso de quien lo pidió. Un rol
        obligatorio ahí habría significado inventarle uno a un contexto."""
        if rol is not None:
            _exigir_acceso(rol)
        return await self._registros.listar(filtros or FiltrosDeBitacora())


class ContarOperaciones:
    """Cuántas, sin traerlas.

    Separado de `ListarOperaciones` porque el llamador es un número de encabezado sobre un mes
    entero: hidratar cada agregado para tomarle el largo sería trabajo hecho para tirar.
    """

    def __init__(self, registros: PortRegistroDeAuditoria) -> None:
        self._registros = registros

    async def ejecutar(self, filtros: FiltrosDeBitacora | None = None) -> int:
        return await self._registros.contar(filtros or FiltrosDeBitacora())


@dataclass(frozen=True, slots=True)
class DetalleDeOperacion:
    """Lo que PAN-LOG-02 muestra (HU-E12-02 RN-01 y RN-03).

    `duracion` es `None` cuando la operación dejó una sola fila: una operación instantánea no
    tiene duración medida, y mostrar «0 ms» sería afirmar algo que nadie midió.
    """

    registro: RegistroDeAuditoria
    #: Todas las filas de la misma entidad, de la más vieja a la más nueva. Incluye la propia.
    timeline: list[RegistroDeAuditoria]
    duracion: timedelta | None

    @property
    def tiene_detalle(self) -> bool:
        """Si la operación registró datos de entrada o la respuesta de un servicio externo."""
        return bool(self.registro.detalle)

    @property
    def paso_con_error(self) -> RegistroDeAuditoria | None:
        """El primer paso que falló, que es lo que el tercer criterio pide señalar."""
        return next((uno for uno in self.timeline if not uno.fue_exitosa), None)


class VerOperacion:
    """PAN-LOG-02. Un registro, su timeline y su duración.

    El timeline se arma con **una** consulta por entidad y no con una por paso: una operación
    fiscal deja media docena de filas, y una consulta por fila sería un N+1 en la pantalla que
    alguien abre justo cuando algo salió mal y quiere entenderlo rápido.
    """

    def __init__(self, registros: PortRegistroDeAuditoria) -> None:
        self._registros = registros

    async def ejecutar(self, registro_id: UUID, *, rol: RolUsuario) -> DetalleDeOperacion:
        _exigir_acceso(rol)

        registro = await self._registros.buscar_por_id(registro_id)
        if registro is None:
            raise OperacionInexistente("La operación no existe")

        timeline = await self._registros.listar_de_entidad(registro.entidad_afectada)
        if not timeline:  # pragma: no cover - siempre contiene al menos a sí mismo
            timeline = [registro]

        duracion = timeline[-1].timestamp - timeline[0].timestamp
        return DetalleDeOperacion(
            registro=registro,
            timeline=timeline,
            duracion=duracion if len(timeline) > 1 else None,
        )


__all__ = [
    "MENSAJE_SIN_OPERACIONES",
    "MOTIVO_SIN_ACCESO",
    "ContarOperaciones",
    "DetalleDeOperacion",
    "ListarOperaciones",
    "VerOperacion",
]
