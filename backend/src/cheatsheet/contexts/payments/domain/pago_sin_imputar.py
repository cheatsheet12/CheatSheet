"""`PagoSinImputar` — plata que entró y no se pudo imputar a ninguna deuda.

Un pago aprobado de MercadoPago que no se puede atar a un cobro abierto **no se pierde en
silencio**: queda como una fila de esta forma y dispara una alerta de severidad alta. Es un
**hecho registrado**, no un proceso: sin estados ni transiciones, como el pago sobre un cobro
cancelado (`Cobro.registrar_pago_huerfano`). Resolverlo (devolver la plata, imputarla a mano) es
una operación sobre dinero que todavía no tiene historia de usuario detrás.

Las invariantes viven acá y se repiten como `CHECK` en la migración: el dominio es la primera
línea; el esquema es lo que un bug futuro no puede saltear. **No guarda datos del pagador**
(nombre, correo, teléfono): solo ids de MercadoPago y nuestros.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.payments.domain.dinero import redondear
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

#: Los topes de las columnas (`varchar(120)` y `varchar(256)`).
LARGO_MAXIMO_DE_PAGO = 120
LARGO_MAXIMO_DE_REFERENCIA = 256

MENSAJE_PAGO_SIN_ID = "Un pago sin imputar necesita el id de pago de MercadoPago."
MENSAJE_COBRO_INCONSISTENTE = (
    "Un pago sin imputar lleva el cobro encontrado si y solo si su motivo no es SIN_COBRO."
)


class MotivoSinImputar(StrEnum):
    """Por qué un pago aprobado no se imputó. Cerrado: agregar uno es una migración."""

    #: No hay un cobro con esa referencia ni con esa preferencia (o es de otra empresa).
    SIN_COBRO = "SIN_COBRO"
    #: El cobro existe y ya estaba pagado (o reembolsado): entró plata de más.
    COBRO_YA_PAGADO = "COBRO_YA_PAGADO"
    #: El cobro está abierto pero el monto pagado difiere del suyo: no se aprueba solo.
    MONTO_DISTINTO = "MONTO_DISTINTO"


@dataclass(frozen=True, slots=True, kw_only=True)
class PagoSinImputar:
    """Un pago aprobado que no se imputó. **Inmutable.**

    - `mp_payment_id` es la clave de idempotencia: un pago, una fila (por empresa).
    - `cobro_id` es el cobro encontrado cuando lo hay (`COBRO_YA_PAGADO`, `MONTO_DISTINTO`) y
      `None` solo en `SIN_COBRO`.
    - `monto` es lo que MercadoPago informó, redondeado `ROUND_HALF_UP`; `None` si no lo informó.
    - `referencia_externa` es lo que MercadoPago devolvió, sin interpretar y acotado a la columna.
    """

    id: UUID
    empresa_id: EmpresaId
    mp_payment_id: str
    motivo: MotivoSinImputar
    recibido_en: datetime
    referencia_externa: str | None = None
    cobro_id: UUID | None = None
    monto: Decimal | None = None
    fecha_aprobacion: datetime | None = None

    def __post_init__(self) -> None:
        pago = self.mp_payment_id.strip()
        if not pago or len(pago) > LARGO_MAXIMO_DE_PAGO:
            raise EntradaInvalida(MENSAJE_PAGO_SIN_ID)
        if (self.motivo is MotivoSinImputar.SIN_COBRO) != (self.cobro_id is None):
            raise EntradaInvalida(MENSAJE_COBRO_INCONSISTENTE)
        # Frozen: la normalización pasa por `object.__setattr__`, una sola vez, acá adentro.
        object.__setattr__(self, "mp_payment_id", pago)
        object.__setattr__(self, "referencia_externa", _referencia(self.referencia_externa))
        if self.monto is not None:
            object.__setattr__(self, "monto", redondear(self.monto))


def _referencia(valor: str | None) -> str | None:
    """Sin espacios de más; vacío es ausente. Se acota a la columna en vez de rechazar: es un
    dato de un tercero y un `external_reference` largo no puede tumbar el registro del pago."""
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio[:LARGO_MAXIMO_DE_REFERENCIA] if limpio else None


__all__ = [
    "LARGO_MAXIMO_DE_PAGO",
    "LARGO_MAXIMO_DE_REFERENCIA",
    "MENSAJE_COBRO_INCONSISTENTE",
    "MENSAJE_PAGO_SIN_ID",
    "MotivoSinImputar",
    "PagoSinImputar",
]
