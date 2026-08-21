"""HU-E2-05 for MercadoPago: is the stored token still good?

One `GET /users/me`. It is the same call `conectar` uses to validate, which is deliberate:
whatever proves a token works at connection time is what proves it still works later.

**A 401 here is RN-03 happening.** MercadoPago answered, and what it said is that the
token was revoked from the seller's own panel or expired. That is not a failure to reach
the provider — it is the provider saying the integration is over — so it comes back as
`NO_CONECTADO` and the card offers Reconectar.
"""

from __future__ import annotations

from typing import Any

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import ResultadoDeVerificacion
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.mercadopago.cliente import ClienteMercadoPago
from cheatsheet.contexts.integrations.infrastructure.mercadopago.mapeo import (
    CLAVE_CUENTA_REAL,
    desempaquetar,
    estado_por_ambiente,
    parametros_de_cuenta,
)


class VerificadorMercadoPago:
    """Implements `PortVerificadorDeConexion`."""

    def __init__(self, cliente: ClienteMercadoPago, *, es_produccion: bool) -> None:
        self._cliente = cliente
        self._es_produccion = es_produccion

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion:
        acceso, _ = desempaquetar(credencial)
        try:
            cuenta = await self._cliente.cuenta(acceso=acceso)
        except ConexionRechazada as exc:
            # Answered, and said no. Never raised upward: one dead integration must not
            # take the screen's other three cards with it.
            return ResultadoDeVerificacion(EstadoDeConexion.NO_CONECTADO, str(exc))

        # The account kind is what was recorded when it connected: `/users/me` does not
        # repeat it, and re-deriving it from anything else would be guessing.
        estado, detalle = estado_por_ambiente(
            bool(parametros.get(CLAVE_CUENTA_REAL)), self._es_produccion
        )
        if estado is EstadoDeConexion.NO_CONECTADO:
            # See `ConectorMercadoPago.renovar`: a mismatch found long after connecting is
            # something to flag, not a reason to drop a connection that works.
            estado = EstadoDeConexion.ATENCION
        return ResultadoDeVerificacion(estado, detalle, parametros_de_cuenta(cuenta))
