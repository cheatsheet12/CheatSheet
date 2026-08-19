"""Stand-ins for the four external services, for environments with no real credentials.

Same reasoning as `identity`'s `ProveedorOAuthSimulado`, and the same guard rails:

- **Why they exist.** Until `conexion-arca`, `conexion-whatsapp` and `conexion-mercadopago`
  land, no provider adapter exists. Without these, PAN-CFG-INT could only ever show four
  cards that do nothing, `VerificarConexiones` would have nothing to verify, and the
  encryption path would never run outside a unit test — which is how a path ships broken.
- **What they are not.** They validate nothing. Any connection material is accepted, and
  the verifier reports whatever the parameters ask it to report.
- **Selecting one in `production` raises.** Not a warning: a `RuntimeError` at
  construction, before the process can serve a request.

Each of the following units deletes its pair from `registro.py` and registers the real
one. Nothing else in the context changes — `conexion-whatsapp` was the first to do it, and
it did exactly that: `WHATSAPP` no longer resolves here.
"""

from __future__ import annotations

import asyncio
from typing import Any

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    ResultadoDeConexion,
    ResultadoDeVerificacion,
)
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion, SistemaExterno
from cheatsheet.platform.settings import Entorno

#: Parameters a caller can set to drive the simulation, so the three states of
#: HU-E2-05 RN-02 and the timeout path are all reachable from the running app and not
#: only from a test double.
PARAMETRO_ESTADO = "simulado_estado"
PARAMETRO_DETALLE = "simulado_detalle"
PARAMETRO_DEMORA = "simulado_demora_segundos"
PARAMETRO_FALLA = "simulado_falla"


def _rechazar_en_produccion(sistema: SistemaExterno, entorno: Entorno) -> None:
    if entorno is Entorno.PRODUCTION:
        raise RuntimeError(
            f"El adaptador simulado de {sistema.value} no puede usarse en produccion. "
            f"Configura las credenciales reales del proveedor."
        )


class ConectorSimulado:
    """Implements `PortConectorDeIntegracion`. Accepts whatever it is given."""

    def __init__(self, *, sistema: SistemaExterno, entorno: Entorno) -> None:
        _rechazar_en_produccion(sistema, entorno)
        self._sistema = sistema

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        if material.parametros.get(PARAMETRO_FALLA):
            raise ProveedorNoDisponible(
                f"El adaptador simulado de {self._sistema.value} fue configurado para fallar"
            )
        if not material.contenido:
            raise ProveedorNoDisponible(f"{self._sistema.value} rechazo una credencial vacia")
        # `CONECTADO` by default: the two providers still answered by this stand-in — ARCA
        # and MercadoPago — validate synchronously. WhatsApp has its own stand-in now,
        # because "pending for 24 to 72 hours" is not a state this one can fake usefully.
        return ResultadoDeConexion(credencial=material.contenido)


class VerificadorSimulado:
    """Implements `PortVerificadorDeConexion`. Reports what the parameters ask for."""

    def __init__(self, *, sistema: SistemaExterno, entorno: Entorno) -> None:
        _rechazar_en_produccion(sistema, entorno)
        self._sistema = sistema

    async def verificar(
        self,
        credencial: bytes,  # noqa: ARG002 — a stand-in has nothing to check it against
        parametros: dict[str, Any],
    ) -> ResultadoDeVerificacion:
        demora = parametros.get(PARAMETRO_DEMORA)
        if isinstance(demora, (int, float)) and demora > 0:
            # Exercises the per-provider timeout of VerificarConexiones without needing a
            # real slow service.
            await asyncio.sleep(float(demora))
        if parametros.get(PARAMETRO_FALLA):
            raise ProveedorNoDisponible(
                f"El adaptador simulado de {self._sistema.value} fue configurado para fallar"
            )
        crudo = parametros.get(PARAMETRO_ESTADO)
        estado = EstadoDeConexion(crudo) if isinstance(crudo, str) else EstadoDeConexion.CONECTADO
        detalle = parametros.get(PARAMETRO_DETALLE)
        return ResultadoDeVerificacion(
            estado=estado, detalle=detalle if isinstance(detalle, str) else None
        )
