"""Typed configuration, read once from the environment.

Two rules shape this module:

1. **No default for anything that is a secret or an address.** A `DATABASE_URL` that
   falls back to localhost is how a staging job quietly writes to a developer's
   laptop, and how a missing variable is discovered in production instead of at boot.
   Missing means the process does not start, with a message naming the variable.
2. **No pydantic here.** `platform/` is the floor everything else stands on; keeping
   it to the standard library means settings can be constructed in a test, in a
   migration and in a Celery worker without dragging a validation framework into
   places that only need three strings.

Real values travel over a private encrypted channel, never through the repository
(docs/configuration-management.md §4.3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class Entorno(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class ConfiguracionFaltante(RuntimeError):
    """A required environment variable is absent. Raised at boot, never later."""


def _requerida(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise ConfiguracionFaltante(
            f"Falta la variable de entorno {nombre}. "
            f"Copiá backend/.env.example y completala antes de arrancar."
        )
    return valor


def _opcional(nombre: str, por_defecto: str) -> str:
    return os.environ.get(nombre, "").strip() or por_defecto


def _entero(nombre: str, por_defecto: int) -> int:
    crudo = os.environ.get(nombre, "").strip()
    if not crudo:
        return por_defecto
    try:
        return int(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(f"{nombre} debe ser un numero entero, no '{crudo}'") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the backend needs to know about where it is running."""

    entorno: Entorno
    database_url: str
    database_url_migrations: str
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str
    log_level: str
    jwt_secret: str
    jwt_access_ttl_minutos: int
    refresh_ttl_dias: int
    terminos_version_vigente: str
    google_oauth_client_id: str
    google_oauth_client_secret: str
    google_oauth_redirect_uri: str

    @property
    def es_produccion(self) -> bool:
        return self.entorno is Entorno.PRODUCTION

    @classmethod
    def desde_entorno(cls) -> Settings:
        entorno = Entorno(_opcional("APP_ENV", Entorno.LOCAL.value))
        redis_url = _requerida("REDIS_URL")
        return cls(
            entorno=entorno,
            database_url=_requerida("DATABASE_URL"),
            # Migrations connect as the table owner; the application does not. That is
            # what makes Row-Level Security real — see migrations/versions/0001.
            database_url_migrations=_requerida("DATABASE_URL_MIGRATIONS"),
            redis_url=redis_url,
            celery_broker_url=_opcional("CELERY_BROKER_URL", redis_url),
            celery_result_backend=_opcional("CELERY_RESULT_BACKEND", redis_url),
            log_level=_opcional("LOG_LEVEL", "INFO"),
            # No default: a JWT secret that falls back to a constant is every
            # deployment signing tokens the world can forge.
            jwt_secret=_requerida("JWT_SECRET"),
            jwt_access_ttl_minutos=_entero("JWT_ACCESS_TTL_MINUTOS", 15),
            refresh_ttl_dias=_entero("REFRESH_TTL_DIAS", 30),
            terminos_version_vigente=_opcional("TERMINOS_VERSION_VIGENTE", "1.0"),
            # Platform-wide OAuth client, not per company. Optional so the API can boot
            # without Google configured; the endpoint refuses instead of the process
            # failing to start.
            google_oauth_client_id=_opcional("GOOGLE_OAUTH_CLIENT_ID", ""),
            google_oauth_client_secret=_opcional("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            google_oauth_redirect_uri=_opcional("GOOGLE_OAUTH_REDIRECT_URI", ""),
        )

    @property
    def google_oauth_configurado(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)
