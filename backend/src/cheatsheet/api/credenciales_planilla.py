"""Composition root for per-company spreadsheet credentials."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.integrations.application.credenciales_oauth import (
    ObtenerAccesoOAuth,
    PortRefrescarOAuth,
    RegistrarCredencialOAuth,
)
from cheatsheet.contexts.integrations.application.ports import (
    PortCifradoDeCredenciales,
    PortRepositorioIntegraciones,
)
from cheatsheet.contexts.integrations.domain.valores import Ambiente, SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.cifrado import CifradoAesGcm
from cheatsheet.contexts.integrations.infrastructure.repositories import RepositorioIntegracionesSQL
from cheatsheet.contexts.spreadsheet_sync.infrastructure.ensamblado import proveedor_de_planilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.google_sheets import ProveedorGoogleSheets
from cheatsheet.platform.settings import AdaptadorDePlanilla, Entorno, Settings
from cheatsheet.shared.empresa import EmpresaId


class CredencialesDePlanilla:
    """The link stores a refresh token; the worker gets only a fresh access token."""

    def __init__(
        self,
        repositorio: PortRepositorioIntegraciones,
        cifrado: PortCifradoDeCredenciales,
        refrescador: PortRefrescarOAuth,
        ambiente: Ambiente,
    ) -> None:
        self._registro = RegistrarCredencialOAuth(repositorio, cifrado)
        self._acceso = ObtenerAccesoOAuth(repositorio, cifrado, refrescador)
        self._ambiente = ambiente

    async def guardar(self, *, empresa_id: EmpresaId, renovacion: str, ahora: datetime) -> UUID:
        return await self._registro.ejecutar(
            empresa_id=empresa_id,
            sistema=SistemaExterno.GOOGLE_SHEETS,
            renovacion=renovacion,
            ambiente=self._ambiente,
            ahora=ahora,
        )

    async def obtener(
        self, *, empresa_id: EmpresaId, configuracion_id: UUID, ahora: datetime
    ) -> str:
        return await self._acceso.ejecutar(
            empresa_id=empresa_id,
            sistema=SistemaExterno.GOOGLE_SHEETS,
            configuracion_id=configuracion_id,
            ahora=ahora,
        )


def credenciales_de_planilla(sesion: AsyncSession, settings: Settings) -> CredencialesDePlanilla:
    """Build per-transaction access without caching credentials across companies."""
    if settings.planilla_adaptador is not AdaptadorDePlanilla.GOOGLE:
        raise RuntimeError("Las credenciales reales requieren el adaptador de Google")
    proveedor = proveedor_de_planilla(settings)
    if not isinstance(proveedor, ProveedorGoogleSheets):
        raise RuntimeError("El proveedor de planillas no puede renovar credenciales")
    return CredencialesDePlanilla(
        RepositorioIntegracionesSQL(sesion),
        CifradoAesGcm(settings.secrets_encryption_key),
        proveedor,
        Ambiente.PRODUCCION if settings.entorno is Entorno.PRODUCTION else Ambiente.HOMOLOGACION,
    )
