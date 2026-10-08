"""Cómo se lee una respuesta de MercadoPago, ya en nuestro vocabulario.

Funciones puras sobre el JSON de la respuesta: ninguna hace red ni levanta ante un campo ilegible
(un formato que no entendemos no puede tumbar el webhook). Viven aparte de `pasarela.py` para que
el cliente HTTP y su parser no compartan archivo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from cheatsheet.contexts.payments.application.ports import EstadoDeReembolso, RespuestaDeReembolso


def preferencia_de(datos: dict[str, Any]) -> str | None:
    """El `preference_id` del cuerpo, si lo trae. **No** cae a `order.id`: ése es el id de la
    merchant order, no el de la preferencia, y tomarlo por tal ataba el pago a nada."""
    valor = datos.get("preference_id")
    return str(valor) if valor else None


def referencia_de(datos: dict[str, Any]) -> str | None:
    """El `external_reference` del pago, o `None` si falta o está vacío."""
    valor = datos.get("external_reference")
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def monto_de(datos: dict[str, Any]) -> Decimal | None:
    """El monto, **desde el texto** de la respuesta.

    `Decimal(str(...))` y no `Decimal(float)`: construir un `Decimal` desde un float arrastra
    el error binario del float adentro, que es exactamente lo que `CLAUDE.md` §3.5 prohíbe.
    """
    valor = datos.get("transaction_amount")
    return Decimal(str(valor)) if valor is not None else None


def fecha_de_aprobacion(datos: dict[str, Any]) -> datetime | None:
    """`date_approved` en UTC, o `None` si falta, no se entiende o no trae zona horaria.

    Es ISO 8601 y puede ser `null` (referencia oficial de MercadoPago, ADR-0010). **Nunca
    levanta**: un formato que no entendemos no puede tumbar el webhook, y el dominio ya sabe qué
    hacer con `None` (usa el momento de la confirmación y marca la fecha como aproximada). Sin
    zona horaria tampoco se adivina: una hora local tomada por UTC corre tres horas un pago.
    """
    return fecha_iso(datos.get("date_approved"))


def fecha_iso(valor: object) -> datetime | None:
    """Una fecha ISO 8601 con zona horaria, en UTC; `None` en cualquier otro caso."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        fecha = datetime.fromisoformat(valor.strip())
        if fecha.utcoffset() is None:
            return None
        return fecha.astimezone(UTC)
    except (ValueError, OverflowError):
        # `OverflowError`: a valid ISO date at the edge of `datetime`'s range that leaves it
        # once shifted to UTC (e.g. year 9999 at -03:00).
        return None


def _estado_de_reembolso(status: object) -> EstadoDeReembolso:
    """`approved` acepta; `rejected` y `cancelled` rechazan; **cualquier otra cosa es «en
    proceso»**. Nunca se acepta por defecto: la referencia solo muestra `approved` y no enumera
    el resto, y dar por devuelta una plata que no lo está es el error caro."""
    if not isinstance(status, str):
        return EstadoDeReembolso.EN_PROCESO
    normal = status.strip().lower()
    if normal == "approved":
        return EstadoDeReembolso.ACEPTADO
    if normal in ("rejected", "cancelled"):
        return EstadoDeReembolso.RECHAZADO
    return EstadoDeReembolso.EN_PROCESO


def respuesta_de_reembolso(
    datos: dict[str, Any], *, id_conocido: str | None = None
) -> RespuestaDeReembolso:
    identificador = datos.get("id")
    monto = datos.get("amount")
    return RespuestaDeReembolso(
        estado=_estado_de_reembolso(datos.get("status")),
        mp_refund_id=str(identificador) if identificador is not None else id_conocido,
        monto=Decimal(str(monto)) if isinstance(monto, int | Decimal | float) else None,
        fecha=fecha_iso(datos.get("date_created")),
        motivo=str(datos["message"]) if datos.get("message") else None,
    )
