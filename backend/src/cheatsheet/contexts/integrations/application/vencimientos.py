"""HU-E2-01 RN-04: an expiring fiscal credential, noticed before it expires.

**A certificate's expiry is silent.** Nobody presses "Verificar estado" on the day it
happens, and the first sign is a document that cannot be issued. RN-04 asks the system to
mark the integration inactive and notify — which means something has to look on its own.

**And it looks for free.** The `notAfter` date lives inside the certificate we already
store, so the daily sweep costs no call to ARCA and burns no access ticket. That is what
makes warning *ahead* of expiry affordable: renewing a certificate at ARCA takes days, so
finding out on the day it expired is finding out too late.

Deliberately close in shape to `sondeo.py`, and for the same reason: the two run the same
way — Beat fans out one message per company, the use case returns what changed, the task
notifies. What differs is the question each one asks.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.integrations.application.integraciones import (
    SinVeredicto,
    aplicar_resultado,
    verificar_con_timeout,
)
from cheatsheet.contexts.integrations.application.ports import (
    PortCifradoDeCredenciales,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
)
from cheatsheet.contexts.integrations.application.sondeo import Desenlace
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

#: Which systems carry a credential that expires on a date we can read. Only ARCA so far:
#: Meta's token has no `notAfter` we hold, and MercadoPago's refresh flow is its own unit.
SISTEMAS_CON_VENCIMIENTO: tuple[SistemaExterno, ...] = (SistemaExterno.ARCA,)


class RevisarVencimientos:
    """Check one company's dated credentials and report what changed.

    Returns only real transitions. A certificate that was fine yesterday and is fine today
    produces nothing — no audit row and no email — because a daily task that reports "still
    valid" for two years is a task everybody learns to ignore.
    """

    def __init__(
        self,
        *,
        integraciones: PortRepositorioIntegraciones,
        cifrado: PortCifradoDeCredenciales,
        adaptadores: PortRegistroDeAdaptadores,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
        timeout_segundos: int,
    ) -> None:
        self._integraciones = integraciones
        self._cifrado = cifrado
        self._adaptadores = adaptadores
        self._publicador = publicador
        self._reloj = reloj
        self._timeout = timeout_segundos

    async def ejecutar(self, *, empresa_id: EmpresaId) -> list[Desenlace]:
        ahora = self._reloj.ahora()
        desenlaces: list[Desenlace] = []

        for configuracion in await self._integraciones.listar(empresa_id):
            if configuracion.sistema not in SISTEMAS_CON_VENCIMIENTO:
                continue
            # The ARCA verifier reads the certificate and opens no socket, so this is a
            # local computation despite going through the same port as a live check.
            resultado = await verificar_con_timeout(
                configuracion=configuracion,
                adaptadores=self._adaptadores,
                cifrado=self._cifrado,
                timeout_segundos=self._timeout,
            )
            if isinstance(resultado, SinVeredicto):
                # Nothing was learned. Unlike a provider outage, this can only mean the
                # stored credential is unreadable, and the verifier already reports that
                # as a state — so there is nothing to record here.
                continue
            cambio = aplicar_resultado(configuracion, resultado, ahora)
            await self._integraciones.guardar(configuracion)
            if cambio is None:
                continue
            await self._publicador.publicar(
                _evento_del_sistema(cambio.descripcion, configuracion.sistema, empresa_id, ahora)
            )
            desenlaces.append(
                Desenlace(
                    cambio=cambio,
                    estado=configuracion.estado,
                    detalle=configuracion.detalle_estado,
                )
            )
        return desenlaces


def _evento_del_sistema(
    accion: str, sistema: SistemaExterno, empresa_id: EmpresaId, ahora: datetime
) -> EventoAuditable:
    """`usuario_id=None`: the scheduler noticed, not a person."""
    return EventoAuditable(
        evento_id=uuid4(),
        empresa_id=empresa_id,
        ocurrido_en=ahora,
        modulo=Modulo.INTEGRATIONS,
        accion=accion,
        entidad_afectada=f"ConfiguracionDeIntegracion:{sistema.value}",
        resultado=Resultado.COMPLETADO,
        usuario_id=None,
        direccion_ip=None,
    )
