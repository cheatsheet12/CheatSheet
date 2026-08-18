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
from datetime import datetime
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
    parametros: dict[str, Any] = field(default_factory=dict)

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
        """Create the configuration of a system that has just validated successfully.

        The caller validates against the provider **before** calling this — HU-E2-01
        RN-02 and HU-E2-02 RN-02 both say invalid credentials leave the integration not
        connected, so a state of `CONECTADO` is a claim this aggregate is not in a
        position to check.
        """
        return cls(
            id=id,
            empresa_id=empresa_id,
            sistema=sistema,
            credencial=credencial,
            ambiente=ambiente,
            estado=EstadoDeConexion.CONECTADO,
            detalle_estado=None,
            verificado_en=ahora,
            parametros=dict(parametros or {}),
        )

    def reconectar(
        self,
        *,
        credencial: CredencialCifrada,
        ambiente: Ambiente,
        ahora: datetime,
        parametros: dict[str, Any] | None = None,
    ) -> CambioDeEstado | None:
        """Replace the credential of an integration that already has a row.

        Idempotency of `ConectarIntegracion` lives here: reconnecting overwrites, it does
        not accumulate rows. The unique index on `(empresa_id, sistema)` is the same rule
        stated in the database.
        """
        if ambiente is not self.ambiente:
            raise InvarianteViolada(
                f"La integracion {self.sistema.value} esta registrada en "
                f"{self.ambiente.value} y no puede reconectarse en {ambiente.value}"
            )
        self.credencial = credencial
        self.parametros = dict(parametros or {})
        return self.registrar_verificacion(EstadoDeConexion.CONECTADO, None, ahora)

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
        if anterior is estado:
            return None
        return CambioDeEstado(
            sistema=self.sistema,
            anterior=anterior,
            nuevo=estado,
            detalle=self.detalle_estado,
        )

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
