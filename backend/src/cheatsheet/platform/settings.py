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


class AdaptadorDeEmail(StrEnum):
    """Which implementation of `PortEnvioDeEmail` gets wired.

    `CONSOLA` writes the invitation link to the log instead of sending it, so the flow is
    completable on a laptop with no mail server. `Settings` refuses it in production —
    see `desde_entorno`.
    """

    SMTP = "smtp"
    CONSOLA = "consola"


class AdaptadorDeWhatsApp(StrEnum):
    """Which implementation answers for WhatsApp Business (HU-E2-03).

    `SIMULADO` fabricates Meta's payloads and runs them through the real Anti-Corruption
    Layer, so the whole flow is completable on a laptop with no Meta app. It is
    **rejected in production** — see `desde_entorno` — for the same reason
    `EMAIL_ADAPTADOR=consola` is: a company would believe its number is connected while
    nothing has ever reached Meta.
    """

    META = "meta"
    SIMULADO = "simulado"


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


def _booleano(nombre: str, por_defecto: bool) -> bool:
    crudo = os.environ.get(nombre, "").strip().lower()
    if not crudo:
        return por_defecto
    return crudo in {"1", "true", "yes", "si"}


def _entero(nombre: str, por_defecto: int) -> int:
    crudo = os.environ.get(nombre, "").strip()
    if not crudo:
        return por_defecto
    try:
        return int(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(f"{nombre} debe ser un numero entero, no '{crudo}'") from exc


def _adaptador_de_email(entorno: Entorno) -> AdaptadorDeEmail:
    """Defaults to the console outside production, and is forbidden inside it.

    An invitation that silently goes to a log file instead of to a person is the kind of
    misconfiguration nobody notices until somebody asks why they never got their email.
    In production the variable has to say `smtp`, or the process does not start.
    """
    crudo = _opcional("EMAIL_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno EMAIL_ADAPTADOR. En produccion debe valer 'smtp'."
            )
        return AdaptadorDeEmail.CONSOLA
    try:
        adaptador = AdaptadorDeEmail(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"EMAIL_ADAPTADOR debe ser 'smtp' o 'consola', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeEmail.CONSOLA and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "EMAIL_ADAPTADOR=consola no es valido en produccion: "
            "las invitaciones quedarian sin enviar."
        )
    return adaptador


def _adaptador_de_whatsapp(entorno: Entorno) -> AdaptadorDeWhatsApp:
    """Defaults to the simulator outside production, and is forbidden inside it."""
    crudo = _opcional("WHATSAPP_ADAPTADOR", "")
    if not crudo:
        if entorno is Entorno.PRODUCTION:
            raise ConfiguracionFaltante(
                "Falta la variable de entorno WHATSAPP_ADAPTADOR. En produccion debe valer 'meta'."
            )
        return AdaptadorDeWhatsApp.SIMULADO
    try:
        adaptador = AdaptadorDeWhatsApp(crudo)
    except ValueError as exc:
        raise ConfiguracionFaltante(
            f"WHATSAPP_ADAPTADOR debe ser 'meta' o 'simulado', no '{crudo}'"
        ) from exc
    if adaptador is AdaptadorDeWhatsApp.SIMULADO and entorno is Entorno.PRODUCTION:
        raise ConfiguracionFaltante(
            "WHATSAPP_ADAPTADOR=simulado no es valido en produccion: "
            "ninguna verificacion llegaria a Meta."
        )
    return adaptador


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
    app_base_url: str
    invitacion_ttl_dias: int
    email_adaptador: AdaptadorDeEmail
    smtp_host: str
    smtp_port: int
    smtp_usuario: str
    smtp_password: str
    smtp_remitente: str
    smtp_tls: bool
    smtp_timeout_segundos: int
    secrets_encryption_key: str
    integracion_timeout_segundos: int
    whatsapp_adaptador: AdaptadorDeWhatsApp
    whatsapp_graph_url: str
    whatsapp_graph_version: str
    whatsapp_timeout_segundos: int
    whatsapp_sondeo_minutos: int
    whatsapp_sondeo_maximo_dias: int

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
            # The invitation email carries a link back into the panel; without this it
            # would carry a broken one, which is a support ticket per invitation.
            app_base_url=_opcional("APP_BASE_URL", "http://localhost:3000"),
            invitacion_ttl_dias=_entero("INVITACION_TTL_DIAS", 7),
            email_adaptador=_adaptador_de_email(entorno),
            smtp_host=_opcional("SMTP_HOST", ""),
            smtp_port=_entero("SMTP_PORT", 587),
            smtp_usuario=_opcional("SMTP_USUARIO", ""),
            smtp_password=_opcional("SMTP_PASSWORD", ""),
            # No default, for the same reason as JWT_SECRET: a fallback key means every
            # deployment encrypts company tax credentials with a constant the repository
            # knows. See contexts/integrations/infrastructure/cifrado.py.
            secrets_encryption_key=_requerida("SECRETS_ENCRYPTION_KEY"),
            integracion_timeout_segundos=_entero("INTEGRACION_TIMEOUT_SEGUNDOS", 5),
            whatsapp_adaptador=_adaptador_de_whatsapp(entorno),
            whatsapp_graph_url=_opcional("WHATSAPP_GRAPH_URL", "https://graph.facebook.com"),
            # Pinned by configuration, never hardcoded: Meta deprecates a Graph version
            # roughly every quarter, and the fix must not require a release.
            whatsapp_graph_version=_opcional("WHATSAPP_GRAPH_VERSION", "v21.0"),
            whatsapp_timeout_segundos=_entero("WHATSAPP_TIMEOUT_SEGUNDOS", 10),
            # 30 minutes against a wait Meta measures in days (HU-E2-03 RN-02): it bounds
            # the delay to about 1% of the wait at 48 calls per number per day.
            whatsapp_sondeo_minutos=_entero("WHATSAPP_SONDEO_MINUTOS", 30),
            # More than double RN-02's 72-hour ceiling. Without it, a number Meta never
            # answers about is polled forever.
            whatsapp_sondeo_maximo_dias=_entero("WHATSAPP_SONDEO_MAXIMO_DIAS", 7),
            smtp_remitente=_opcional("SMTP_REMITENTE", "CheatSheet <no-reply@localhost>"),
            smtp_tls=_booleano("SMTP_TLS", True),
            smtp_timeout_segundos=_entero("SMTP_TIMEOUT_SEGUNDOS", 10),
        )

    @property
    def google_oauth_configurado(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)
