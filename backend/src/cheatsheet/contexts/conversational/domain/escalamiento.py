"""`Escalamiento` — el momento en que una máquina admite que no puede.

Es la entidad que HU-E9-01 RN-01 pide explícitamente que exista **como entidad y no como
estado de la conversación**: «la condición de escalada se deriva de la existencia de un
escalamiento abierto». Este archivo es esa frase hecha código.

Tres reglas viven acá:

1. **Un escalamiento cerrado no se reabre** (HU-E9-02 RN-04). Un pedido nuevo del cliente
   genera un escalamiento nuevo. Reabrir mezclaría dos casos que pueden no tener nada que ver
   y dejaría un `updated_at` que no explica qué pasó en el medio.

2. **Tomar el escalamiento es lo que calla al agente** (RN-02). No hay un flag «agente
   activo»: mientras haya un escalamiento sin resolver, el agente no contesta ese hilo. Un
   flag aparte sería el mismo hecho guardado dos veces.

3. **El motivo es obligatorio** (HU-E8-05 RN-02). Un escalamiento sin motivo le llega a un
   operador que tiene que leer el hilo entero para saber por qué está ahí.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: Los dos motivos que las historias nombran, más el que deja constancia de una transcripción
#: mala (HS-T7 RN-04). Constantes y no un enum porque el DER guarda `motivo` como `varchar`:
#: un enum acá obligaría a una migración el día que aparezca un motivo nuevo, y el valor no
#: gobierna ninguna decisión — se lee.
MOTIVO_BAJA_CONFIANZA = "El agente no interpretó la intención con confianza suficiente"
MOTIVO_PEDIDO_POR_EL_CLIENTE = "El cliente pidió hablar con una persona"
MOTIVO_TRANSCRIPCION_POBRE = "La transcripción de la nota de voz no alcanzó calidad suficiente"
MOTIVO_SIN_FAQ = "Ninguna respuesta frecuente cubre la consulta"
#: Cancelar un turno con seña depende de una política que el sistema no conoce (pendiente #6).
MOTIVO_CANCELACION_CON_SENA = "Cancelación de turno con seña"


class EstadoEscalamiento(StrEnum):
    """El enum `estado_escalamiento` del DER.

    `ABIERTO` es «esperando a alguien»; `ASIGNADO` es «alguien lo tomó»; `RESUELTO` es final.
    """

    ABIERTO = "ABIERTO"
    ASIGNADO = "ASIGNADO"
    RESUELTO = "RESUELTO"


#: Qué transiciones existen, como tabla y no como diez `if`.
#:
#: **`ABIERTO → RESUELTO` existe**, sin pasar por `ASIGNADO`: un operador puede leer el hilo,
#: ver que el cliente ya se resolvió solo y cerrarlo. Obligar a tomarlo primero sería un paso
#: que no protege nada.
#:
#: **`RESUELTO` no sale** (HU-E9-02 RN-04).
TRANSICIONES_LEGALES: dict[EstadoEscalamiento, frozenset[EstadoEscalamiento]] = {
    EstadoEscalamiento.ABIERTO: frozenset(
        {EstadoEscalamiento.ASIGNADO, EstadoEscalamiento.RESUELTO}
    ),
    EstadoEscalamiento.ASIGNADO: frozenset({EstadoEscalamiento.RESUELTO}),
    EstadoEscalamiento.RESUELTO: frozenset(),
}

#: Los estados en los que el agente **no** contesta ese hilo (RN-02).
ESTADOS_SIN_AGENTE = frozenset({EstadoEscalamiento.ABIERTO, EstadoEscalamiento.ASIGNADO})


@dataclass(slots=True)
class Escalamiento:
    """Una conversación esperando a una persona."""

    id: UUID
    conversacion_id: UUID
    empresa_id: EmpresaId
    motivo: str
    estado: EstadoEscalamiento = EstadoEscalamiento.ABIERTO
    usuario_asignado_id: UsuarioId | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.motivo.strip():
            raise EntradaInvalida("Un escalamiento necesita un motivo")

    @property
    def esta_abierto(self) -> bool:
        """Si esto es `True`, el agente no contesta ese hilo (RN-02)."""
        return self.estado in ESTADOS_SIN_AGENTE

    def tomar(self, usuario_id: UsuarioId, momento: datetime) -> None:
        """HU-E9-01 RN-02 y RN-06: el operador asume el control y queda registrado."""
        if self.estado is not EstadoEscalamiento.ABIERTO:
            raise InvarianteViolada(
                "El escalamiento ya fue tomado o resuelto"
                if self.estado is EstadoEscalamiento.ASIGNADO
                else "Un escalamiento resuelto no se reabre"
            )
        self.usuario_asignado_id = usuario_id
        self.updated_at = momento
        self._transicionar_a(EstadoEscalamiento.ASIGNADO)

    def resolver(self, momento: datetime) -> None:
        """HU-E9-02. Final: un escalamiento resuelto no vuelve.

        «Un nuevo pedido del cliente generará un escalamiento nuevo» — la regla lo dice, y esta
        transición ausente es la que lo hace cierto.
        """
        self.updated_at = momento
        self._transicionar_a(EstadoEscalamiento.RESUELTO)

    def _transicionar_a(self, destino: EstadoEscalamiento) -> None:
        if destino not in TRANSICIONES_LEGALES[self.estado]:
            raise InvarianteViolada(
                f"Un escalamiento {self.estado.value.lower()} no puede pasar a "
                f"{destino.value.lower()}"
            )
        self.estado = destino
