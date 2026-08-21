"""The `ConfiguracionDeIntegracion` aggregate (DER, BC4).

One per `(empresa_id, sistema)`. It holds an external service's credential, the
environment it talks to, and what the last live check found.

**A row exists only once something was connected.** The DER declares
`credencial_contenido_cifrado` NOT NULL, and that is respected rather than worked around:
PAN-CFG-INT shows four cards because `SISTEMAS_EN_PANTALLA` has four entries, not because
four empty rows were created per company. `ListarIntegraciones` joins the catalogue
against whatever rows exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from cheatsheet.contexts.integrations.domain.eventos import CambioDeEstado
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
    validar_detalle,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import InvarianteViolada


@dataclass(eq=False)
class ConfiguracionDeIntegracion:
    """What one company has configured for one external system."""

    id: UUID
    empresa_id: EmpresaId
    sistema: SistemaExterno
    credencial: CredencialCifrada
    ambiente: Ambiente
    estado: EstadoDeConexion
    detalle_estado: str | None
    verificado_en: datetime | None
    #: When the wait for an asynchronous provider started. **Gap H10** — the DER models
    #: the status as a boolean, so it has no notion of a verification in flight and no
    #: column for when one began. `verificado_en` cannot serve: it is re-stamped by every
    #: poll, so it measures the last question, not the wait. `None` whenever the
    #: integration is not `PENDIENTE`.
    pendiente_desde: datetime | None = None
    parametros: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def registrar(
        cls,
        *,
        id: UUID,
        empresa_id: EmpresaId,
        sistema: SistemaExterno,
        credencial: CredencialCifrada,
        ambiente: Ambiente,
        ahora: datetime,
        estado: EstadoDeConexion,
        detalle: str | None = None,
        parametros: dict[str, Any] | None = None,
    ) -> ConfiguracionDeIntegracion:
        """Create the configuration of a system the provider has just answered about.

        **The state comes from the provider, not from this method.** ARCA and MercadoPago
        validate synchronously and land on `CONECTADO`; WhatsApp lands on `PENDIENTE`,
        because Meta accepted the credential and has not yet finished reviewing the number
        (HU-E2-03 RN-01). This aggregate is in no position to decide which of those it is.

        What is invariant either way: the caller validated against the provider **before**
        calling this. HU-E2-01 RN-02 and HU-E2-02 RN-02 both say invalid credentials leave
        the integration not connected, so nothing is created for a credential that was
        refused.
        """
        return cls(
            id=id,
            empresa_id=empresa_id,
            sistema=sistema,
            credencial=credencial,
            ambiente=ambiente,
            estado=estado,
            detalle_estado=validar_detalle(detalle),
            verificado_en=ahora,
            pendiente_desde=ahora if estado is EstadoDeConexion.PENDIENTE else None,
            parametros=dict(parametros or {}),
        )

    @classmethod
    def conectar(
        cls,
        *,
        id: UUID,
        empresa_id: EmpresaId,
        sistema: SistemaExterno,
        credencial: CredencialCifrada,
        ambiente: Ambiente,
        ahora: datetime,
        parametros: dict[str, Any] | None = None,
    ) -> ConfiguracionDeIntegracion:
        """`registrar` for a provider that validated synchronously. Kept for the readers.

        A named constructor that says `conectar` where the outcome really is "connected"
        is worth more than one call site saving a keyword argument.
        """
        return cls.registrar(
            id=id,
            empresa_id=empresa_id,
            sistema=sistema,
            credencial=credencial,
            ambiente=ambiente,
            ahora=ahora,
            estado=EstadoDeConexion.CONECTADO,
            parametros=parametros,
        )

    def reconectar(
        self,
        *,
        credencial: CredencialCifrada,
        ambiente: Ambiente,
        ahora: datetime,
        estado: EstadoDeConexion = EstadoDeConexion.CONECTADO,
        detalle: str | None = None,
        parametros: dict[str, Any] | None = None,
    ) -> CambioDeEstado | None:
        """Replace the credential of an integration that already has a row.

        Idempotency of `ConectarIntegracion` lives here: reconnecting overwrites, it does
        not accumulate rows. The unique index on `(empresa_id, sistema)` is the same rule
        stated in the database.

        `estado` defaults to `CONECTADO` for the same reason `conectar` exists, and
        WhatsApp passes `PENDIENTE`: reconnecting a number sends it back to Meta for
        review, so claiming it is connected would be a lie for the next 24 to 72 hours.
        """
        if ambiente is not self.ambiente:
            raise InvarianteViolada(
                f"La integracion {self.sistema.value} esta registrada en "
                f"{self.ambiente.value} y no puede reconectarse en {ambiente.value}"
            )
        self.credencial = credencial
        self.parametros = dict(parametros or {})
        return self.registrar_verificacion(estado, detalle, ahora)

    def registrar_verificacion(
        self,
        estado: EstadoDeConexion,
        detalle: str | None,
        ahora: datetime,
    ) -> CambioDeEstado | None:
        """Record what a live check found (HU-E2-05 RN-01, RN-03).

        **Returns an event only when the state actually changed.** `verificado_en` is
        stamped either way, because RN-03 shows the time of the last check and a check
        that confirmed the status is still a check. But writing an audit row every time
        would turn the Log de Operaciones into a heartbeat, and HU-E12-01 — which filters
        that log by module — would have to learn to ignore its own most frequent entry.
        """
        anterior = self.estado
        self.estado = estado
        self.detalle_estado = validar_detalle(detalle)
        self.verificado_en = ahora
        # The clock on an asynchronous wait starts when the wait does and is cleared the
        # moment it ends, so a later pending period is never measured from an earlier one.
        if estado is not EstadoDeConexion.PENDIENTE:
            self.pendiente_desde = None
        elif anterior is not EstadoDeConexion.PENDIENTE:
            self.pendiente_desde = ahora
        if anterior is estado:
            return None
        return CambioDeEstado(
            sistema=self.sistema,
            anterior=anterior,
            nuevo=estado,
            detalle=self.detalle_estado,
        )

    def registrar_intento_fallido(self, detalle: str, ahora: datetime) -> CambioDeEstado | None:
        """Record a check that produced **no verdict** — a timeout, a host that is down.

        The distinction this method exists for: an integration that is `PENDIENTE` has a
        valid credential and an answer that has not arrived yet. If the network fails
        while we ask, nothing was learned about the integration — Meta did not reject
        anything, we simply could not reach it. Dropping it to `NO_CONECTADO` there would
        invent a rejection, show the Administrator a failure for something still in
        progress, and offer "Reconectar" for a request already in flight at Meta.

        So a pending integration **stays pending**: only `verificado_en` and the detail
        move, and no event is emitted because no state changed. For every other state the
        old behaviour is unchanged — a connected integration we cannot reach is, as far as
        anyone can tell, not connected.
        """
        if self.estado is EstadoDeConexion.PENDIENTE:
            self.detalle_estado = validar_detalle(detalle)
            self.verificado_en = ahora
            return None
        return self.registrar_verificacion(EstadoDeConexion.NO_CONECTADO, detalle, ahora)

    def espera_vencida(self, ahora: datetime, maximo_dias: int) -> bool:
        """Whether an asynchronous provider has taken longer than we are willing to wait.

        Decision D-e. HU-E2-03 RN-02 puts Meta's ceiling at 72 hours; the default here is
        seven days, more than double it. Without a ceiling a row Meta never answers about
        is polled forever: the company keeps a scheduled task alive indefinitely and the
        Administrator keeps a screen that never changes.
        """
        if not self.esta_pendiente or self.pendiente_desde is None:
            return False
        return ahora - self.pendiente_desde >= timedelta(days=maximo_dias)

    def actualizar_parametros(self, nuevos: dict[str, Any]) -> None:
        """Merge what the provider reported (HU-E2-03 RN-03: display name and quality).

        A merge and not a replacement: the parameters the Administrator supplied at
        connection time — which number, which account — are still what identifies the
        integration, and a verification that only returns the display name must not erase
        them.
        """
        if nuevos:
            self.parametros = {**self.parametros, **nuevos}

    def desactivar(self, motivo: str, ahora: datetime) -> CambioDeEstado | None:
        """Expired or revoked credentials leave the integration inactive.

        HU-E2-01 RN-04 and HU-E2-02 RN-03. **Nothing triggers this yet**: with every
        provider simulated there is nothing that can expire. It is written and tested
        here because it is the transition all three connection units share, so the first
        one to bring a real provider only has to schedule the check that calls it.
        """
        return self.registrar_verificacion(EstadoDeConexion.NO_CONECTADO, motivo, ahora)

    @property
    def esta_conectada(self) -> bool:
        return self.estado is EstadoDeConexion.CONECTADO

    @property
    def esta_pendiente(self) -> bool:
        """Waiting on a provider that answers asynchronously. Today, only Meta."""
        return self.estado is EstadoDeConexion.PENDIENTE
