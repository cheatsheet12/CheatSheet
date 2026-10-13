"""Per-company OAuth material used by unattended integrations.

Only the refresh token is persisted. A consumer receives a short-lived access token for
one call; it never gets the encrypted row, the cipher, or the renewal credential.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from cheatsheet.contexts.integrations.application.ports import (
    PortCifradoDeCredenciales,
    PortRepositorioIntegraciones,
)
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.shared.empresa import EmpresaId


class CredencialOAuthRevocada(Exception):
    """The provider refused the renewal credential; a new consent is required."""


class PortRefrescarOAuth(Protocol):
    async def renovar(self, credencial: bytes) -> str: ...


class RegistrarCredencialOAuth:
    """Store a refresh credential only after the provider validated the consent."""

    def __init__(
        self, repositorio: PortRepositorioIntegraciones, cifrado: PortCifradoDeCredenciales
    ) -> None:
        self._repositorio = repositorio
        self._cifrado = cifrado

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        sistema: SistemaExterno,
        renovacion: str,
        ambiente: Ambiente,
        ahora: datetime,
    ) -> UUID:
        if not renovacion:
            raise ValueError("La credencial de renovacion esta vacia")
        cifrada = self._cifrado.cifrar(renovacion.encode("utf-8"))
        existente = await self._repositorio.buscar(empresa_id, sistema)
        if existente is None:
            configuracion = ConfiguracionDeIntegracion.conectar(
                id=uuid4(),
                empresa_id=empresa_id,
                sistema=sistema,
                credencial=cifrada,
                ambiente=ambiente,
                ahora=ahora,
            )
            await self._repositorio.agregar(configuracion)
            return configuracion.id
        # A company can link several files. Replacing a healthy token with one from a
        # different Google account would silently break every previously linked file.
        if existente.estado is EstadoDeConexion.CONECTADO:
            return existente.id
        existente.reconectar(credencial=cifrada, ambiente=ambiente, ahora=ahora)
        await self._repositorio.guardar(existente)
        return existente.id


class ObtenerAccesoOAuth:
    """Resolve and renew one company's credential without caching it."""

    def __init__(
        self,
        repositorio: PortRepositorioIntegraciones,
        cifrado: PortCifradoDeCredenciales,
        refrescador: PortRefrescarOAuth,
    ) -> None:
        self._repositorio = repositorio
        self._cifrado = cifrado
        self._refrescador = refrescador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        sistema: SistemaExterno,
        configuracion_id: UUID,
        ahora: datetime,
    ) -> str:
        configuracion = await self._repositorio.buscar(empresa_id, sistema)
        if configuracion is None or configuracion.id != configuracion_id:
            raise ValueError("No hay credencial OAuth conectada para este vinculo")
        if configuracion.estado is not EstadoDeConexion.CONECTADO:
            raise CredencialOAuthRevocada("La planilla requiere volver a conectarse")
        renovacion = self._cifrado.descifrar(configuracion.credencial)
        try:
            return await self._refrescador.renovar(renovacion)
        except CredencialOAuthRevocada:
            configuracion.registrar_verificacion(
                EstadoDeConexion.NO_CONECTADO,
                "Google revocó el acceso; reconectá la planilla.",
                ahora,
            )
            await self._repositorio.guardar(configuracion)
            raise
