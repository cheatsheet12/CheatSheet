"""Application-level conditions of the observability context."""

from __future__ import annotations

from uuid import UUID

from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida


class RegistroDuplicado(Exception):
    """The occurrence already has an audit record.

    Not a domain error: nothing about the business was violated. It is the expected
    outcome of an at-least-once delivery, and the caller's correct reaction is to do
    nothing and carry on.
    """

    def __init__(self, evento_id: UUID) -> None:
        super().__init__(f"El evento {evento_id} ya fue registrado")
        self.evento_id = evento_id


class OperacionInexistente(EntradaInvalida):
    """No está en la bitácora de esta empresa, o no está en ninguna.

    Bajo RLS son la misma respuesta, como en el resto del sistema: distinguirlas le diría a una
    empresa que el id de una operación ajena es real.
    """


class NotificacionInexistente(EntradaInvalida):
    """No existe, o es de la bandeja de otra persona. Misma respuesta, por lo mismo."""


class SolicitudInexistente(EntradaInvalida):
    """La solicitud de soporte no existe para esta empresa."""


class AccesoALaBitacoraDenegado(OperacionNoPermitida):
    """HU-E12-01 RN-05 y HU-E12-02 RN-04, textual: Solo Lectura no accede a la bitácora.

    El motivo está escrito en el encabezado de la épica 12: ese rol puede corresponder a un
    actor externo, y la bitácora expone el registro crudo de toda la operación —incluidos datos
    de clientes y mensajes de terceros—. Lo fiscal que un contador necesite sale por los
    reportes y el paquete contable del épico 9, no por acá.
    """


__all__ = [
    "AccesoALaBitacoraDenegado",
    "NotificacionInexistente",
    "OperacionInexistente",
    "RegistroDuplicado",
    "SolicitudInexistente",
]
