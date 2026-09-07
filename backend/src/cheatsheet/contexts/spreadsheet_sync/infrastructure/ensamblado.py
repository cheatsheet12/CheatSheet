"""Wiring of the spreadsheet context onto one unit of work.

Two halves with different lifetimes, and that is why they are two functions:

- **The repository is request-scoped.** It writes through the session the caller's
  transaction owns, like every other context's assembly.
- **The storage and the provider are process-scoped.** An R2 client holds a connection
  pool and a Google client holds configuration; building either per request would open a
  new pool for every upload. They are cached on the settings they were built from.

The choice between real and simulated adapters lives here, and follows the same rule as
the three integrations of epic 2: `Settings` has already refused a simulator in production
before this code runs, so there is no environment check left to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    PortAlmacenamientoDeArchivos,
    PortModeloDeLenguaje,
    PortProveedorDePlanilla,
    PortRepositorioMapeo,
    PortRepositorioVinculo,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.almacenamiento import (
    AlmacenamientoEnMemoria,
    AlmacenamientoR2,
    ConfiguracionR2,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.google_sheets import (
    ConfiguracionGoogleSheets,
    ProveedorDePlanillaSimulado,
    ProveedorGoogleSheets,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.modelo import (
    ConfiguracionDelModelo,
    ModeloDeLenguajeAnthropic,
    ModeloDeLenguajeSimulado,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.repositories import (
    RepositorioMapeoPostgres,
    RepositorioVinculoPostgres,
)
from cheatsheet.platform.settings import (
    AdaptadorDeAlmacenamiento,
    AdaptadorDeModelo,
    AdaptadorDePlanilla,
    Settings,
)


@dataclass(frozen=True, slots=True)
class Planillas:
    """The context's request-scoped adapters, bound to one transaction."""

    vinculos: PortRepositorioVinculo
    mapeos: PortRepositorioMapeo

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> Planillas:
        return cls(
            vinculos=RepositorioVinculoPostgres(unidad.sesion),
            mapeos=RepositorioMapeoPostgres(unidad.sesion),
        )


@lru_cache(maxsize=1)
def almacenamiento(settings: Settings) -> PortAlmacenamientoDeArchivos:
    """The object store, built once per process.

    The in-memory one is cached too, and has to be: two instances would be two different
    buckets, and a file uploaded through one would be missing from the other.
    """
    if settings.almacenamiento_adaptador is AdaptadorDeAlmacenamiento.R2:
        return AlmacenamientoR2(
            ConfiguracionR2(
                endpoint=settings.r2_endpoint,
                bucket=settings.r2_bucket,
                access_key_id=settings.r2_access_key_id,
                secret_access_key=settings.r2_secret_access_key,
            )
        )
    return AlmacenamientoEnMemoria(settings.entorno)


@lru_cache(maxsize=1)
def proveedor_de_planilla(settings: Settings) -> PortProveedorDePlanilla:
    """The ACL against Google Sheets, built once per process."""
    if settings.planilla_adaptador is AdaptadorDePlanilla.GOOGLE:
        return ProveedorGoogleSheets(
            ConfiguracionGoogleSheets(
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
                # The spreadsheet link comes back to its own callback, not to the one the
                # sign-in flow of epic 1 uses: the two consents grant different scopes and
                # land on different screens.
                redirect_uri=f"{settings.app_base_url}/api/planillas/google/callback",
            )
        )
    return ProveedorDePlanillaSimulado(settings.entorno)


@lru_cache(maxsize=1)
def modelo_de_lenguaje(settings: Settings) -> PortModeloDeLenguaje:
    """The LLM (ADR-0007), built once per process.

    Cached like the other two: the client holds a connection pool, and building one per
    request would open a new pool for every spreadsheet somebody links.
    """
    if settings.llm_adaptador is AdaptadorDeModelo.ANTHROPIC:
        return ModeloDeLenguajeAnthropic(
            ConfiguracionDelModelo(
                api_key=settings.anthropic_api_key,
                modelo=settings.llm_modelo,
                timeout_segundos=settings.llm_timeout_segundos,
                max_tokens=settings.llm_max_tokens,
            )
        )
    return ModeloDeLenguajeSimulado(settings.entorno)
