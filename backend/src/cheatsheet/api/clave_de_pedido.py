"""La clave de idempotencia del pedido: el encabezado `X-Idempotency-Key` (ADR-0013).

Es la forma del pedido HTTP, no una regla del caso de uso: por eso se valida acá, en el borde, y
no en `application/`. Los endpoints con efecto externo irreversible la comparten (`POST /cobros`
hoy; la emisión y la nota de crédito de `billing` en #97) para contestar los mismos casos con los
mismos códigos.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Header

from cheatsheet.shared.errors import EntradaInvalida

ENCABEZADO = "X-Idempotency-Key"
MENSAJE_FALTA = "Falta la clave de idempotencia del pedido (encabezado X-Idempotency-Key)."
MENSAJE_INVALIDA = "La clave de idempotencia del pedido no es valida."


class ClaveDeIdempotenciaFaltante(EntradaInvalida):
    """El pedido no trae `X-Idempotency-Key`. 422: es obligatoria."""


class ClaveDeIdempotenciaInvalida(EntradaInvalida):
    """El encabezado no es un UUID. 422."""


def exigir_clave_de_pedido(
    x_idempotency_key: Annotated[str | None, Header(alias=ENCABEZADO)] = None,
) -> UUID:
    """Dependencia de FastAPI: el UUID del encabezado, o 422 con el texto de la tabla del ADR."""
    if x_idempotency_key is None or not x_idempotency_key.strip():
        raise ClaveDeIdempotenciaFaltante(MENSAJE_FALTA)
    try:
        return UUID(x_idempotency_key.strip())
    except ValueError as exc:
        raise ClaveDeIdempotenciaInvalida(MENSAJE_INVALIDA) from exc


__all__ = [
    "ENCABEZADO",
    "MENSAJE_FALTA",
    "MENSAJE_INVALIDA",
    "ClaveDeIdempotenciaFaltante",
    "ClaveDeIdempotenciaInvalida",
    "exigir_clave_de_pedido",
]
