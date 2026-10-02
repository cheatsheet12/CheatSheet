"""`Reembolso` — una fila inmutable de plata devuelta (ADR-0010, punto 4).

Un cobro guarda solo el acumulado (`monto_reembolsado`); **cada** reembolso, y cada corrección
de uno, es una fila de esta forma. Nunca se edita ni se borra: un error se corrige agregando una
fila **negativa** que apunta a la que anula (HU-E6-05 RN-08), visible en el historial.

Las invariantes de la fila viven acá y se repiten como `CHECK` en la migración 0027. El dominio
es la primera línea; el esquema es lo que un bug futuro no puede saltear.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.payments.domain.dinero import redondear
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida

MENSAJE_REEMBOLSO_EN_CERO = "El monto del reembolso no puede ser cero."
MENSAJE_SIGNO_DE_CORRECCION = (
    "Solo una correccion lleva monto negativo y apunta al reembolso que corrige."
)
MENSAJE_REEMBOLSO_SIN_MOTIVO = "Debe ingresar el motivo del reembolso."

#: Los topes de las columnas (`varchar(120)` y `varchar(500)`): pasarse es un 422 con el motivo
#: y no un error de la base.
LARGO_MAXIMO_DE_REFERENCIA = 120
LARGO_MAXIMO_DE_MOTIVO = 500


#: Argentina no tiene horario de verano desde 2009: un desfase fijo de tres horas alcanza y no
#: depende de que el sistema tenga la base de zonas horarias instalada.
ARGENTINA = timezone(timedelta(hours=-3))
HORA_DEL_DIA_DE_DEVOLUCION = time(12, 0)


def dia_de_argentina(instante: datetime) -> date:
    """El día calendario de Argentina en el que cae un instante."""
    return instante.astimezone(ARGENTINA).date()


def mediodia_de_argentina(dia: date) -> datetime:
    """Las 12:00 de ese día en Argentina, en UTC (15:00).

    Un reembolso manual se carga como un **día**, no como un instante. El mediodía cae en el mismo
    día en Argentina y en UTC, así que la devolución no cambia de período según la grilla del
    filtro (hoy los límites del período se arman en UTC).
    """
    return datetime.combine(dia, HORA_DEL_DIA_DE_DEVOLUCION, tzinfo=ARGENTINA).astimezone(UTC)


class OrigenDeReembolso(StrEnum):
    """Por dónde salió la plata: la API de MercadoPago o una carga manual (transferencias)."""

    API_MERCADOPAGO = "API_MERCADOPAGO"
    MANUAL = "MANUAL"


@dataclass(frozen=True, slots=True, kw_only=True)
class Reembolso:
    """Una devolución, o la corrección de una. **Inmutable.**

    - `monto` es `Decimal` de dos decimales, distinto de cero; **negativo si y solo si** es una
      corrección (`corrige_a` apunta a la fila anulada).
    - `motivo` es obligatorio en las filas manuales, correcciones incluidas.
    - `registrado_por` es `None` cuando confirma el sistema.
    - `mp_refund_id` es la clave de idempotencia de la confirmación: una misma respuesta de
      MercadoPago, una sola fila. `referencia` es texto libre de una persona y no puede serlo.
    """

    id: UUID
    empresa_id: EmpresaId
    cobro_id: UUID
    monto: Decimal
    fecha_devolucion: datetime
    origen: OrigenDeReembolso
    created_at: datetime
    referencia: str | None = None
    motivo: str | None = None
    corrige_a: UUID | None = None
    mp_refund_id: str | None = None
    registrado_por: UsuarioId | None = None

    def __post_init__(self) -> None:
        monto = redondear(self.monto)
        if monto == 0:
            raise EntradaInvalida(MENSAJE_REEMBOLSO_EN_CERO)
        if (monto < 0) != (self.corrige_a is not None):
            raise EntradaInvalida(MENSAJE_SIGNO_DE_CORRECCION)
        motivo = _texto(self.motivo, LARGO_MAXIMO_DE_MOTIVO, "El motivo")
        if self.origen is OrigenDeReembolso.MANUAL and motivo is None:
            raise EntradaInvalida(MENSAJE_REEMBOLSO_SIN_MOTIVO)
        # Frozen: la normalización pasa por `object.__setattr__`, una sola vez, acá adentro.
        object.__setattr__(self, "monto", monto)
        object.__setattr__(self, "motivo", motivo)
        object.__setattr__(
            self,
            "referencia",
            _texto(self.referencia, LARGO_MAXIMO_DE_REFERENCIA, "La referencia"),
        )

    @property
    def es_correccion(self) -> bool:
        return self.corrige_a is not None

    @property
    def es_manual(self) -> bool:
        return self.origen is OrigenDeReembolso.MANUAL


def _texto(valor: str | None, largo: int, nombre: str) -> str | None:
    """El texto sin espacios de más; vacío es ausente; más largo que la columna se rechaza."""
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio:
        return None
    if len(limpio) > largo:
        raise EntradaInvalida(f"{nombre} no puede superar los {largo} caracteres.")
    return limpio


__all__ = [
    "ARGENTINA",
    "LARGO_MAXIMO_DE_MOTIVO",
    "LARGO_MAXIMO_DE_REFERENCIA",
    "MENSAJE_REEMBOLSO_EN_CERO",
    "MENSAJE_REEMBOLSO_SIN_MOTIVO",
    "MENSAJE_SIGNO_DE_CORRECCION",
    "OrigenDeReembolso",
    "Reembolso",
    "dia_de_argentina",
    "mediodia_de_argentina",
]
