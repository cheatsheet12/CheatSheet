"""Ports of the integrations context.

This module and `integraciones.py` are the **published contract** of
[ADR-0003](../../../../../docs/adr/0003-integrations-open-host-service.md): any context
may call what lives in `application/`, and `domain/` and `infrastructure/` stay private.
Nothing here imports from another context — an Open Host Service that depended on its
clients would not be one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.shared.empresa import EmpresaId


class PortRepositorioIntegraciones(Protocol):
    async def agregar(self, configuracion: ConfiguracionDeIntegracion) -> None: ...
    async def guardar(self, configuracion: ConfiguracionDeIntegracion) -> None: ...
    async def buscar(
        self, empresa_id: EmpresaId, sistema: SistemaExterno
    ) -> ConfiguracionDeIntegracion | None: ...
    async def listar(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]: ...
    async def listar_pendientes(
        self, empresa_id: EmpresaId
    ) -> list[ConfiguracionDeIntegracion]: ...


class PortCifradoDeCredenciales(Protocol):
    """Encrypts and decrypts a credential at rest.

    The adapter lives in `integrations/infrastructure/` and nowhere else. That placement
    is what makes ADR-0003's "decryption never leaves the context" a fact rather than a
    convention: a cipher in `platform/` would be importable by any module, and the claim
    would rest on nobody happening to do it.
    """

    def cifrar(self, plano: bytes) -> CredencialCifrada: ...
    def descifrar(self, credencial: CredencialCifrada) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ResultadoDeVerificacion:
    """What a live check found. `detalle` is what the Atención badge shows next to it.

    `parametros` carries whatever the provider reported about itself and is **merged**
    into the row, never substituted for it. Today that is HU-E2-03 RN-03 — the verified
    display name and the line quality Meta reports — and the field is generic rather than
    WhatsApp-shaped because a provider-specific DTO in the published contract is what
    point 5 of ADR-0003 forbids.
    """

    estado: EstadoDeConexion
    detalle: str | None = None
    parametros: dict[str, Any] = field(default_factory=dict)


class PortVerificadorDeConexion(Protocol):
    """Asks one external service whether the stored credential still works.

    Implementations own their timeout, their retries with backoff and their failure
    handling (CLAUDE.md §5). The use case owns only the guarantee that a slow one does
    not delay the others.
    """

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion: ...


@dataclass(frozen=True, slots=True)
class MaterialDeConexion:
    """What the connect endpoint received, on its way to the provider adapter.

    Opaque bytes plus free parameters, because the three providers disagree about what a
    credential even is: ARCA takes a certificate and a private key, MercadoPago an OAuth
    authorization code, Meta a phone number and a token. Giving each its own DTO here
    would put provider-specific shapes in the published contract, which point 5 of
    ADR-0003 forbids.
    """

    contenido: bytes
    parametros: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResultadoDeConexion:
    """What the provider answered: the credential to store, and where that leaves us.

    **The state is part of the answer, and that is the point** — decision D-a of
    `conexion-whatsapp`. ARCA and MercadoPago validate synchronously and come back
    `CONECTADO`. Meta accepts the credential and then reviews the number for 24 to 72
    hours (HU-E2-03 RN-01), so it comes back `PENDIENTE`. Without this, `ConectarIntegracion`
    would have to ask "is this WhatsApp?" — the per-provider conditional the adapter
    registry exists precisely to avoid.

    `credencial` is what gets encrypted and persisted; it is not necessarily what arrived.
    An OAuth exchange returns a different token from the code it was given.
    """

    credencial: bytes
    estado: EstadoDeConexion = EstadoDeConexion.CONECTADO
    detalle: str | None = None
    parametros: dict[str, Any] = field(default_factory=dict)


class PortConectorDeIntegracion(Protocol):
    """Validates connection material against the provider before anything is stored.

    HU-E2-01 RN-02 and HU-E2-02 RN-02 both require validation *before* the integration is
    marked active, so this returns the credential to persist and raises when the provider
    says no.
    """

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion: ...


@dataclass(frozen=True, slots=True)
class AvisoDeIntegracion:
    """One notice about an integration whose state changed on its own.

    **`destinatarios` arrives resolved, and that is deliberate — decision D-c.** Who the
    administrators of a company are is `identity` data, and ADR-0003 lists `identity`
    among this context's consumers: reaching back into it would make the Open Host Service
    depend on a client of its own. So the composition root — the Celery task — reads the
    recipients and passes them in. What stays here is *when* to notify; what stays outside
    is *whom*.
    """

    destinatarios: tuple[str, ...]
    sistema: SistemaExterno
    estado: EstadoDeConexion
    detalle: str | None


class PortAvisoDeIntegracion(Protocol):
    """Tells the Administrator that a provider answered while nobody was looking.

    Only the asynchronous outcomes go through here (HU-E2-03: the verification completed,
    or it failed). The synchronous ones need no push — whoever pressed the button is
    looking at the screen that already shows the answer.
    """

    async def avisar(self, aviso: AvisoDeIntegracion) -> None: ...


class PortRegistroDeAdaptadores(Protocol):
    """Resolves the connector and verifier of one system.

    The single seam each of the following units touches: `conexion-arca` registers the
    real ARCA pair, and nothing else in this context changes.
    """

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None: ...
    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None: ...
