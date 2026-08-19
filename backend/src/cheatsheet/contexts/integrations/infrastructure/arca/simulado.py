"""A stand-in for ARCA, for every environment without a real fiscal certificate.

Same guard rails as every other stand-in in this context: it validates nothing against a
real service, and **constructing it in `production` raises** — a `RuntimeError` at build
time, before the process serves a request. Here that matters more than anywhere else: a
company believing it is connected to ARCA when nothing ever reached ARCA is a company that
believes it can invoice.

**It reuses the real credential parsing and the real expiry mapping.** Only the network
call is replaced. So a certificate that is malformed, whose key does not match, or that has
already expired is rejected on a laptop exactly as it would be in production — and the
three states of the card come out of the same function either way.

The ticket it mints is fake and says so. Nothing downstream can mistake it for one that
ARCA would accept.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    ResultadoDeConexion,
    ResultadoDeVerificacion,
    TicketEmitido,
)
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion, SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.arca import firma
from cheatsheet.contexts.integrations.infrastructure.arca.adaptadores import (
    SERVICIO_DE_VALIDACION,
    parametros_de_la_credencial,
)
from cheatsheet.contexts.integrations.infrastructure.arca.mapeo import estado_por_vencimiento
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.clock import Reloj

#: WSAA tickets last twelve hours. The stand-in copies that so the renewal margin, and the
#: code that decides when to renew, are exercised with realistic numbers.
DURACION_DEL_TICKET = timedelta(hours=12)

#: Marks the payload as fabricated. If one of these ever reached ARCA it would be rejected,
#: which is the correct outcome and better than a blob that looks plausible.
PREFIJO_SIMULADO = "TICKET-SIMULADO"


def _rechazar_en_produccion(entorno: Entorno) -> None:
    if entorno is Entorno.PRODUCTION:
        raise RuntimeError(
            f"El adaptador simulado de {SistemaExterno.ARCA.value} no puede usarse en "
            f"produccion. Configura las credenciales reales de ARCA."
        )


class ArcaSimulado:
    """Implements the three ARCA ports at once, without a socket."""

    def __init__(self, *, entorno: Entorno, reloj: Reloj, aviso: timedelta) -> None:
        _rechazar_en_produccion(entorno)
        self._reloj = reloj
        self._aviso = aviso

    async def emitir(self, credencial: bytes, servicio: ServicioDeArca) -> TicketEmitido:
        fiscal = firma.leer_credencial(credencial)
        ahora = self._reloj.ahora()
        firma.exigir_vigente(fiscal, ahora)
        return TicketEmitido(
            servicio=servicio,
            contenido=f"{PREFIJO_SIMULADO}-{secrets.token_hex(8)}".encode(),
            expira_en=ahora + DURACION_DEL_TICKET,
        )

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        fiscal = firma.leer_credencial(material.contenido)
        firma.exigir_vigente(fiscal, self._reloj.ahora())
        if not material.contenido.strip():
            raise ConexionRechazada("Falta la credencial fiscal")
        ticket = await self.emitir(material.contenido, SERVICIO_DE_VALIDACION)
        return ResultadoDeConexion(
            credencial=material.contenido,
            parametros=parametros_de_la_credencial(fiscal),
            tickets=(ticket,),
        )

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion:
        del parametros
        try:
            fiscal = firma.leer_credencial(credencial)
        except ConexionRechazada as exc:
            # Same answer the real adapter gives, for the same reason: a stored credential
            # that no longer parses is a data problem, and it belongs on the card.
            return ResultadoDeVerificacion(
                EstadoDeConexion.ATENCION, f"No se pudo leer la credencial guardada: {exc}"
            )
        estado, detalle = estado_por_vencimiento(fiscal.vence_en, self._reloj.ahora(), self._aviso)
        return ResultadoDeVerificacion(estado, detalle, parametros_de_la_credencial(fiscal))
