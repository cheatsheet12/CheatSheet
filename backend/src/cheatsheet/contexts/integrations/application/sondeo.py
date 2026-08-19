"""HU-E2-03: what happens while nobody is looking.

Meta takes 24 to 72 hours to verify a phone number (RN-02). Nothing on the screen can
resolve that — the Administrator connected the number and left. So a scheduled task asks
periodically, and this is the use case behind it.

**Why polling and not Meta's webhook — decision D-d.** Meta publishes a webhook for this
exact transition and it would be more immediate. It is not used here for three reasons,
in order of weight: receiving it needs a public endpoint, signature validation with
`WHATSAPP_APP_SECRET` and an approved Meta app, none of which exist yet; the webhook is a
*platform* concern, so its endpoint belongs to the conversational epic and building it
here would be constructing another epic's infrastructure; and against a 24-to-72-hour wait
instant notification buys nothing measurable. When that endpoint does exist, this becomes
the safety net for a webhook that never arrived — which is where a poll belongs anyway.

**This use case does not notify anybody.** It returns the transitions it produced and the
caller decides. Who the administrators of a company are is `identity` data, and ADR-0003
lists `identity` among this context's consumers: reaching into it would make an Open Host
Service depend on one of its own clients. See decision D-c.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.integrations.application.integraciones import (
    aplicar_resultado,
    verificar_con_timeout,
)
from cheatsheet.contexts.integrations.application.ports import (
    PortCifradoDeCredenciales,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
)
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.eventos import CambioDeEstado
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

#: Shown to the Administrator when the provider simply never answered (decision D-e).
MOTIVO_VENCIDO = "El proveedor no respondio la verificacion en el plazo maximo"


@dataclass(frozen=True, slots=True)
class Desenlace:
    """One integration that stopped being pending, and what it became.

    Carries the state change **and** the recipient-facing detail so the caller can send a
    notice without re-reading the aggregate — and, more to the point, without needing to
    know what an aggregate is.
    """

    cambio: CambioDeEstado
    estado: EstadoDeConexion
    detalle: str | None


class SondearIntegracionesPendientes:
    """Ask about every pending integration of one company, once.

    Scoped to a company on purpose: every session in this system carries an `empresa_id`
    and Row-Level Security is enforced against it. The sweep that finds *which* companies
    have something pending happens above this, in the task, and is the only place allowed
    to look across tenants — through a `SECURITY DEFINER` function that returns nothing
    but company ids.
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
        maximo_dias: int,
    ) -> None:
        self._integraciones = integraciones
        self._cifrado = cifrado
        self._adaptadores = adaptadores
        self._publicador = publicador
        self._reloj = reloj
        self._timeout = timeout_segundos
        self._maximo_dias = maximo_dias

    async def ejecutar(self, *, empresa_id: EmpresaId) -> list[Desenlace]:
        """Returns only the integrations that actually resolved.

        A poll that finds the answer is still not ready writes no audit row and produces
        no notice. Otherwise a 24-hour wait at one poll every 30 minutes would leave 48
        identical entries in the Log de Operaciones, and HU-E12-01 — which filters that
        log by module — would have to learn to ignore its own most frequent entry.
        """
        ahora = self._reloj.ahora()
        desenlaces: list[Desenlace] = []

        for configuracion in await self._integraciones.listar_pendientes(empresa_id):
            cambio = await self._resolver(configuracion, ahora)
            await self._integraciones.guardar(configuracion)
            if cambio is None:
                continue
            await self._publicador.publicar(
                _evento_del_sistema(cambio, empresa_id=empresa_id, ahora=ahora)
            )
            desenlaces.append(
                Desenlace(
                    cambio=cambio,
                    estado=configuracion.estado,
                    detalle=configuracion.detalle_estado,
                )
            )
        return desenlaces

    async def _resolver(
        self, configuracion: ConfiguracionDeIntegracion, ahora: datetime
    ) -> CambioDeEstado | None:
        """Give up, or ask again."""
        if configuracion.espera_vencida(ahora, self._maximo_dias):
            # Deliberately not a call to the provider: we have decided to stop waiting,
            # and asking one more time would make the timeout depend on it answering.
            return configuracion.registrar_verificacion(
                EstadoDeConexion.NO_CONECTADO, MOTIVO_VENCIDO, ahora
            )
        resultado = await verificar_con_timeout(
            configuracion=configuracion,
            adaptadores=self._adaptadores,
            cifrado=self._cifrado,
            timeout_segundos=self._timeout,
        )
        return aplicar_resultado(configuracion, resultado, ahora)


def _evento_del_sistema(
    cambio: CambioDeEstado, *, empresa_id: EmpresaId, ahora: datetime
) -> EventoAuditable:
    """The audit row for a change nobody asked for.

    `usuario_id` is `None` and that is the honest value: the scheduler acted, not a
    person. HS-T5 stores it either way, and the Log de Operaciones showing "el sistema"
    is exactly what happened.
    """
    return EventoAuditable(
        evento_id=uuid4(),
        empresa_id=empresa_id,
        ocurrido_en=ahora,
        modulo=Modulo.INTEGRATIONS,
        accion=cambio.descripcion,
        entidad_afectada=f"ConfiguracionDeIntegracion:{cambio.sistema.value}",
        resultado=Resultado.COMPLETADO,
        usuario_id=None,
        direccion_ip=None,
    )
