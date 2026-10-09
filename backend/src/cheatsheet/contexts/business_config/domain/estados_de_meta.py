"""Los estados de una plantilla en Meta, traducidos a los nuestros (U6, D-U6-2).

Dos vocabularios de Meta: el **estado del nodo** (`status`, lo que devuelve el `GET`) y el
**evento del webhook** (`event`, lo que llega en `message_template_status_update`). Un valor que
Meta agregue sin avisar se traduce a `None`: quien lo recibe no cambia nada y deja un log, en vez
de inventar un estado.
"""

from __future__ import annotations

from cheatsheet.contexts.business_config.domain.plantilla import EstadoDeAprobacion

_A = EstadoDeAprobacion

#: `APPROVED, IN_APPEAL, PENDING, REJECTED, PENDING_DELETION, DELETED, DISABLED, PAUSED,
#: LIMIT_EXCEEDED` [T-NODE].
ESTADOS_DEL_NODO: dict[str, EstadoDeAprobacion] = {
    "APPROVED": _A.APROBADA,
    "IN_APPEAL": _A.PENDIENTE,
    "PENDING": _A.PENDIENTE,
    "REJECTED": _A.RECHAZADA,
    "LIMIT_EXCEEDED": _A.RECHAZADA,
    "PAUSED": _A.PAUSADA,
    "DISABLED": _A.DESHABILITADA,
    "DELETED": _A.SIN_ENVIAR,
    "PENDING_DELETION": _A.SIN_ENVIAR,
}

#: Los eventos de [WH-TPL] que deciden un estado. `FLAGGED` y `LOCKED` siguen siendo aprobadas:
#: la plantilla se puede usar, y el detalle de Meta queda a la vista.
EVENTOS_DEL_WEBHOOK: dict[str, EstadoDeAprobacion] = {
    "APPROVED": _A.APROBADA,
    "REINSTATED": _A.APROBADA,
    "FLAGGED": _A.APROBADA,
    "LOCKED": _A.APROBADA,
    "PENDING": _A.PENDIENTE,
    "IN_APPEAL": _A.PENDIENTE,
    "REJECTED": _A.RECHAZADA,
    "LIMIT_EXCEEDED": _A.RECHAZADA,
    "PAUSED": _A.PAUSADA,
    "DISABLED": _A.DESHABILITADA,
    "DELETED": _A.SIN_ENVIAR,
    "PENDING_DELETION": _A.SIN_ENVIAR,
    "ARCHIVED": _A.SIN_ENVIAR,
}

#: `UNARCHIVED` dice que la plantilla volvió, no en qué estado: no decide nada y la conciliación
#: la vuelve a leer.
EVENTOS_QUE_SE_RELEEN = frozenset({"UNARCHIVED"})


def estado_desde_nodo(estado: str) -> EstadoDeAprobacion | None:
    return ESTADOS_DEL_NODO.get(estado)


def estado_desde_evento(evento: str) -> EstadoDeAprobacion | None:
    return EVENTOS_DEL_WEBHOOK.get(evento)


__all__ = [
    "ESTADOS_DEL_NODO",
    "EVENTOS_DEL_WEBHOOK",
    "EVENTOS_QUE_SE_RELEEN",
    "estado_desde_evento",
    "estado_desde_nodo",
]
