"""Uniform translation of exceptions into HTTP responses.

Two things this must never do:

- **Leak internals.** A stack trace, a SQL statement or a driver message in a
  response body is reconnaissance handed to whoever asked. Unexpected failures answer
  with an opaque 500 and an identifier; the detail goes to the log, where it belongs.
- **Catch `Exception` in business code.** The blanket handler exists here, at the
  edge, and nowhere else. CLAUDE.md §5 requires module-specific exceptions and ruff
  (BLE) enforces it inside the contexts.

The domain hierarchy is reachable from here because it lives in the Shared Kernel
(`shared/errors.py`); rule R3 forbids importing any context's `domain/`.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.errors import (
    EntradaInvalida,
    ErrorDeDominio,
    InvarianteViolada,
    OperacionNoPermitida,
)

logger = obtener_logger(__name__)

# A broken business rule is a 409, not a 500: the request was understood and the
# system is healthy — the operation is simply not allowed to happen.
CODIGOS: dict[type[ErrorDeDominio], int] = {
    EntradaInvalida: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvarianteViolada: status.HTTP_409_CONFLICT,
    OperacionNoPermitida: status.HTTP_403_FORBIDDEN,
}


def _codigo_para(error: ErrorDeDominio) -> int:
    for tipo, codigo in CODIGOS.items():
        if isinstance(error, tipo):
            return codigo
    return status.HTTP_409_CONFLICT


def registrar_manejadores(app: FastAPI) -> None:
    """Attach the handlers to the application. Called once, from `create_app`."""

    @app.exception_handler(ErrorDeDominio)
    async def _dominio(_: Request, exc: Exception) -> JSONResponse:
        error = exc if isinstance(exc, ErrorDeDominio) else ErrorDeDominio(str(exc))
        codigo = _codigo_para(error)
        logger.info("error_de_dominio", tipo=type(error).__name__, detalle=str(error))
        return JSONResponse(
            status_code=codigo,
            content={"error": type(error).__name__, "detalle": str(error)},
        )

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
        incidente = uuid4()
        logger.error(
            "error_inesperado",
            incidente=str(incidente),
            tipo=type(exc).__name__,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "ErrorInterno",
                "detalle": "La operacion no pudo completarse.",
                "incidente": str(incidente),
            },
        )
