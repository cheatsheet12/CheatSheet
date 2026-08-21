"""HU-E2-02 RN-03: a token that is about to expire, renewed before it does.

MercadoPago's access token lasts about six months and comes with a refresh token. Storing
the second and never using it would mean the integration dies twice a year on a date
nobody has in a calendar — right when a company tries to charge.

So the daily sweep that already watches ARCA's certificates gets a sibling that asks a
different question. **They are two use cases and not one with a branch**, because what
they do differs where it matters: the ARCA one reads a date that is inside the certificate
we already hold and calls nobody; this one calls the provider and **rewrites the stored
credential**. Folding a credential write into a read-only sweep is how a task that used to
be safe to re-run stops being one.

**A provider that is down does not disconnect anybody.** Only an explicit rejection —
MercadoPago saying the refresh token is no longer valid — marks the integration inactive.
A timeout means we did not manage to ask, and the credential we hold still works.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.application.ports import (
    PortCifradoDeCredenciales,
    PortRegistroDeAdaptadores,
    PortRepositorioIntegraciones,
    ResultadoDeConexion,
)
from cheatsheet.contexts.integrations.application.sondeo import Desenlace
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_VENCIMIENTO,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)

#: Which systems hold a credential that can be traded for a fresh one. Only MercadoPago:
#: ARCA's certificate is renewed by the company at ARCA's own site, and Meta's token has
#: no refresh flow we participate in.
SISTEMAS_RENOVABLES: tuple[SistemaExterno, ...] = (SistemaExterno.MERCADOPAGO,)

#: What the audit row reads as. Not a `CambioDeEstado`: nothing changed state, and yet a
#: credential was replaced — which is exactly the kind of thing HS-T5 exists to record.
ACCION_RENOVADA = "credencial renovada"


class RenovarCredenciales:
    """Renew what is about to expire for one company. Reports only what changed state.

    Scoped to a company, like every other use case here: the sweep that decides *which*
    companies to visit lives in the task above, and is the only thing allowed to look
    across tenants.
    """

    def __init__(
        self,
        *,
        integraciones: PortRepositorioIntegraciones,
        cifrado: PortCifradoDeCredenciales,
        adaptadores: PortRegistroDeAdaptadores,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
        margen_dias: int,
    ) -> None:
        self._integraciones = integraciones
        self._cifrado = cifrado
        self._adaptadores = adaptadores
        self._publicador = publicador
        self._reloj = reloj
        self._margen = timedelta(days=margen_dias)

    async def ejecutar(self, *, empresa_id: EmpresaId) -> list[Desenlace]:
        ahora = self._reloj.ahora()
        desenlaces: list[Desenlace] = []

        for configuracion in await self._integraciones.listar(empresa_id):
            if not self._hay_que_renovar(configuracion, ahora):
                continue
            desenlace = await self._renovar(configuracion, empresa_id, ahora)
            if desenlace is not None:
                desenlaces.append(desenlace)
        return desenlaces

    def _hay_que_renovar(self, configuracion: ConfiguracionDeIntegracion, ahora: datetime) -> bool:
        if configuracion.sistema not in SISTEMAS_RENOVABLES:
            return False
        if self._adaptadores.renovador(configuracion.sistema) is None:
            return False
        if configuracion.estado is EstadoDeConexion.NO_CONECTADO:
            # Already inactive: the Administrator was told and has to reconnect. Retrying
            # a refresh token the provider rejected every day changes nothing.
            return False
        vence = vencimiento_de(configuracion)
        if vence is None:
            # No readable expiry: renew now rather than never. A missing date is how an
            # integration silently stops being watched, and one successful renewal writes
            # a proper one — so this self-heals instead of accumulating.
            return True
        return ahora >= vence - self._margen

    async def _renovar(
        self, configuracion: ConfiguracionDeIntegracion, empresa_id: EmpresaId, ahora: datetime
    ) -> Desenlace | None:
        renovador = self._adaptadores.renovador(configuracion.sistema)
        if renovador is None:  # pragma: no cover — `_hay_que_renovar` already checked
            return None
        # Point 3 of ADR-0003: the plaintext lives in this frame and is never stored back.
        plano = self._cifrado.descifrar(configuracion.credencial)

        try:
            respuesta = await renovador.renovar(plano)
        except ConexionRechazada as exc:
            return await self._desactivar(configuracion, empresa_id, str(exc), ahora)
        except ProveedorNoDisponible as exc:
            # We did not manage to ask. The credential we hold is still the one that
            # worked yesterday, so nothing about the integration changed.
            logger.warning(
                "renovacion_sin_respuesta",
                sistema=configuracion.sistema.value,
                motivo=str(exc),
            )
            return None

        await self._guardar_renovada(configuracion, empresa_id, respuesta, ahora)
        return None

    async def _guardar_renovada(
        self,
        configuracion: ConfiguracionDeIntegracion,
        empresa_id: EmpresaId,
        respuesta: ResultadoDeConexion,
        ahora: datetime,
    ) -> None:
        """Write the fresh credential and record that it happened. No email.

        A renewal that worked is not news for a person — a message every six months
        saying "nothing to do" is a message nobody reads. It is news for the audit log,
        because a stored credential was replaced.
        """
        configuracion.reconectar(
            credencial=self._cifrado.cifrar(respuesta.credencial),
            ambiente=configuracion.ambiente,
            ahora=ahora,
            estado=respuesta.estado,
            detalle=respuesta.detalle,
            # A merge and not a replacement: `reconectar` overwrites the bag, and the
            # refresh response carries fewer fields than the original connection did.
            parametros={**configuracion.parametros, **respuesta.parametros},
        )
        await self._integraciones.guardar(configuracion)
        await self._publicador.publicar(
            _evento(
                f"Integracion {configuracion.sistema.value}: {ACCION_RENOVADA}",
                configuracion.sistema,
                empresa_id,
                ahora,
            )
        )
        logger.info("credencial_renovada", sistema=configuracion.sistema.value)

    async def _desactivar(
        self,
        configuracion: ConfiguracionDeIntegracion,
        empresa_id: EmpresaId,
        motivo: str,
        ahora: datetime,
    ) -> Desenlace | None:
        """RN-03: the provider says the credential is gone. Inactive, and tell somebody."""
        cambio = configuracion.desactivar(motivo, ahora)
        await self._integraciones.guardar(configuracion)
        if cambio is None:
            return None
        await self._publicador.publicar(
            _evento(cambio.descripcion, configuracion.sistema, empresa_id, ahora)
        )
        return Desenlace(
            cambio=cambio, estado=configuracion.estado, detalle=configuracion.detalle_estado
        )


def vencimiento_de(configuracion: ConfiguracionDeIntegracion) -> datetime | None:
    """When the stored credential stops working, if the provider said so.

    `None` covers both "the parameter is not there" and "it is there and unreadable",
    because the caller does the same thing with either: it cannot schedule around a date
    it does not have.
    """
    crudo = configuracion.parametros.get(CLAVE_VENCIMIENTO)
    if not isinstance(crudo, str) or not crudo:
        return None
    try:
        return datetime.fromisoformat(crudo)
    except ValueError:
        logger.warning("vencimiento_ilegible", sistema=configuracion.sistema.value)
        return None


def _evento(
    accion: str, sistema: SistemaExterno, empresa_id: EmpresaId, ahora: datetime
) -> EventoAuditable:
    """`usuario_id=None`: the scheduler did this, not a person."""
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
