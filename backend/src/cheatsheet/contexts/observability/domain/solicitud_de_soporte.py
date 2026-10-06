"""`SolicitudDeSoporte` — un pedido de ayuda al equipo de CheatSheet (HU-E9-03).

**Vive en `observability` y no en un contexto propio**, que es donde el DER la pone. La razón
es buena: el ticket que alguien abre casi siempre cita una operación que salió mal, y este es
el contexto que sabe qué pasó. Un contexto nuevo para cuatro columnas sería una carpeta más y
la misma información del otro lado de una frontera.

**El estado lo mueve el equipo de CheatSheet, no la empresa** (RN-03). Desde el panel se abre
y se consulta; `ABIERTA → EN_REVISION → RESUELTA → CERRADA` es la vida del ticket del lado de
soporte, y por eso el agregado tiene la máquina de estados pero la API de este épico sólo
expone el alta y la consulta. La alternativa —dejar que el administrador cierre su propio
ticket— convierte «resuelta» en una opinión.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: HU-E9-03, palabra por palabra.
MENSAJE_CAMPOS_OBLIGATORIOS = "El asunto y la descripción son obligatorios."

LARGO_MAXIMO_DEL_ASUNTO = 200


class PrioridadDeSoporte(StrEnum):
    """Qué tan urgente lo considera quien lo abre.

    El DER declara `prioridad varchar` sin enumerarla. Tres valores, los mismos que
    `Severidad`, y a propósito: son la misma escala vista desde los dos lados —lo que el
    sistema considera urgente y lo que la empresa considera urgente— y dos vocabularios para una
    escala son dos tablas de equivalencia esperando a desincronizarse.
    """

    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"


class EstadoDeSolicitud(StrEnum):
    """El enum `estado_solicitud_soporte` del DER."""

    ABIERTA = "ABIERTA"
    EN_REVISION = "EN_REVISION"
    RESUELTA = "RESUELTA"
    CERRADA = "CERRADA"


#: Qué transiciones existen, como tabla y no como cuatro `if`.
#:
#: **`CERRADA` no vuelve.** Un ticket cerrado que se reabre pierde la fecha en que se resolvió,
#: que es lo único que dice cuánto tardó soporte en contestar. Si el problema sigue, se abre
#: otro y se cita el anterior — que además deja ver que pasó dos veces.
TRANSICIONES_LEGALES: dict[EstadoDeSolicitud, frozenset[EstadoDeSolicitud]] = {
    EstadoDeSolicitud.ABIERTA: frozenset(
        {EstadoDeSolicitud.EN_REVISION, EstadoDeSolicitud.RESUELTA, EstadoDeSolicitud.CERRADA}
    ),
    EstadoDeSolicitud.EN_REVISION: frozenset(
        {EstadoDeSolicitud.RESUELTA, EstadoDeSolicitud.CERRADA}
    ),
    EstadoDeSolicitud.RESUELTA: frozenset({EstadoDeSolicitud.CERRADA}),
    EstadoDeSolicitud.CERRADA: frozenset(),
}


@dataclass(slots=True)
class SolicitudDeSoporte:
    """Un pedido de ayuda, con quién lo abrió y en qué estado está."""

    id: UUID
    empresa_id: EmpresaId
    usuario_id: UsuarioId
    asunto: str
    descripcion: str
    prioridad: PrioridadDeSoporte = PrioridadDeSoporte.MEDIA
    estado: EstadoDeSolicitud = EstadoDeSolicitud.ABIERTA
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        asunto = self.asunto.strip()
        descripcion = self.descripcion.strip()
        if not asunto or not descripcion:
            # RN-02, con el texto del criterio de aceptación. Los dos campos en un solo
            # mensaje porque el criterio los nombra juntos: decir «falta el asunto» y después
            # «falta la descripción» son dos viajes para lo que la historia pide en uno.
            raise EntradaInvalida(MENSAJE_CAMPOS_OBLIGATORIOS)
        if len(asunto) > LARGO_MAXIMO_DEL_ASUNTO:
            raise EntradaInvalida(f"El asunto excede {LARGO_MAXIMO_DEL_ASUNTO} caracteres")
        self.asunto = asunto
        self.descripcion = descripcion

    @property
    def esta_abierta(self) -> bool:
        """Lo que RN-04 deja consultar: «sus solicitudes abiertas»."""
        return self.estado in (EstadoDeSolicitud.ABIERTA, EstadoDeSolicitud.EN_REVISION)

    def cambiar_estado(self, destino: EstadoDeSolicitud, momento: datetime) -> None:
        if destino not in TRANSICIONES_LEGALES[self.estado]:
            raise InvarianteViolada(
                f"Una solicitud {self.estado.value.lower()} no puede pasar a "
                f"{destino.value.lower()}"
            )
        self.estado = destino
        self.updated_at = momento


__all__ = [
    "LARGO_MAXIMO_DEL_ASUNTO",
    "MENSAJE_CAMPOS_OBLIGATORIOS",
    "TRANSICIONES_LEGALES",
    "EstadoDeSolicitud",
    "PrioridadDeSoporte",
    "SolicitudDeSoporte",
]
