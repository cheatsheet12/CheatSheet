"""Ports of the integrations context.

This module and `integraciones.py` are the **published contract** of
[ADR-0003](../../../../../docs/adr/0003-integrations-open-host-service.md): any context
may call what lives in `application/`, and `domain/` and `infrastructure/` stay private.
Nothing here imports from another context — an Open Host Service that depended on its
clients would not be one.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    """What a live check found. `detalle` is what the Atención badge shows next to it."""

    estado: EstadoDeConexion
    detalle: str | None = None


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


class PortConectorDeIntegracion(Protocol):
    """Validates connection material against the provider before anything is stored.

    HU-E2-01 RN-02 and HU-E2-02 RN-02 both require validation *before* the integration is
    marked active, so this returns the credential to persist and raises when the provider
    says no.
    """

    async def conectar(self, material: MaterialDeConexion) -> bytes: ...


class PortRegistroDeAdaptadores(Protocol):
    """Resolves the connector and verifier of one system.

    The single seam each of the following units touches: `conexion-arca` registers the
    real ARCA pair, and nothing else in this context changes.
    """

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None: ...
    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None: ...
