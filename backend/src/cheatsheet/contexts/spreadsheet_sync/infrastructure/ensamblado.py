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
    PortEscrituraDePlanilla,
    PortModeloDeLenguaje,
    PortProveedorDePlanilla,
    PortRepositorioMapeo,
    PortRepositorioProcesamiento,
    PortRepositorioVinculo,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.escritura import (
    ConfiguracionDeEscritura,
    EscrituraEnGoogleSheets,
    EscrituraSimulada,
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
    RepositorioProcesamientoPostgres,
    RepositorioVinculoPostgres,
)
from cheatsheet.platform.almacenamiento import almacenamiento as platform_almacenamiento
from cheatsheet.platform.settings import (
    AdaptadorDeModelo,
    AdaptadorDePlanilla,
    Settings,
)


@dataclass(frozen=True, slots=True)
class Planillas:
    """The context's request-scoped adapters, bound to one transaction."""

    vinculos: PortRepositorioVinculo
    mapeos: PortRepositorioMapeo
    procesamientos: PortRepositorioProcesamiento

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> Planillas:
        return cls(
            vinculos=RepositorioVinculoPostgres(unidad.sesion),
            mapeos=RepositorioMapeoPostgres(unidad.sesion),
            procesamientos=RepositorioProcesamientoPostgres(unidad.sesion),
        )


def almacenamiento(settings: Settings) -> PortAlmacenamientoDeArchivos:
    """The object store, from `platform/`.

    The factory moved there when `billing` became the second consumer: the cache has to be
    shared, or the in-memory stand-in would be two different buckets. This wrapper stays so
    the context keeps naming its own port, which is the type its use cases ask for.
    """
    return platform_almacenamiento(settings)


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


@lru_cache(maxsize=1)
def escritura_de_planilla(settings: Settings) -> PortEscrituraDePlanilla:
    """The write-back adapter (HU-E3-07), built once per process.

    **The token is a placeholder and the real one is per company**, held encrypted in
    `configuracion_de_integracion` by `integrations` (ADR-0003). Resolving it per company
    is what the write-back needs before it can run against a real document, and it is the
    piece the unit record names as unfinished.
    """
    if settings.planilla_adaptador is AdaptadorDePlanilla.GOOGLE:
        return EscrituraEnGoogleSheets(ConfiguracionDeEscritura(token=""))
    return EscrituraSimulada(settings.entorno)
