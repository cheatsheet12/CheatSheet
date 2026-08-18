"""Transactional email for the invitation (HU-E1-04 RN-02).

Two adapters behind one port, chosen by configuration:

- **`EnviadorSMTP`** — production. SMTP rather than a provider's SDK, so which
  transactional provider is used stays a deployment decision instead of a dependency in
  `pyproject.toml`. Explicit timeout, as CLAUDE.md §5 requires of every outbound call;
  the retry with backoff belongs to the Celery task, which is what survives a restart.
- **`EnviadorDeConsola`** — local development and tests. Writes to the structured log and
  **opens no socket**, so the suite can exercise the whole flow without a mail server.

**The template is a file, not a string in this module.** Same rule the constitution sets
for prompts: text that goes out to a person gets reviewed and versioned without touching
code. `string.Template` is the renderer on purpose — `$name` substitution and nothing
else. An f-string or Jinja over content that will eventually be editable outside the repo
is an expression evaluator pointed at untrusted text.

**The link never reaches the log.** The console adapter prints it because printing it *is*
its job in development; the SMTP adapter logs the recipient and the message id and never
the token. A live invitation link in an aggregated log is an account waiting to be taken.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from string import Template

import aiosmtplib

from cheatsheet.contexts.identity.application.errors import EnvioDeEmailFallido
from cheatsheet.contexts.identity.application.ports import MensajeDeInvitacion
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

PLANTILLAS = Path(__file__).parent / "plantillas"
FORMATO_DE_FECHA = "%d/%m/%Y a las %H:%M UTC"


@dataclass(frozen=True, slots=True)
class ConfiguracionSMTP:
    host: str
    puerto: int
    usuario: str
    contrasena: str
    remitente: str
    usar_tls: bool
    timeout_segundos: int
    #: Where the panel lives, so the link points at something real.
    url_base_de_la_app: str


def _enlace(base: str, token: str) -> str:
    return f"{base.rstrip('/')}/invitacion/{token}"


def _render(nombre: str, mensaje: MensajeDeInvitacion, url_base: str) -> str:
    plantilla = Template((PLANTILLAS / nombre).read_text(encoding="utf-8"))
    return plantilla.substitute(
        empresa=mensaje.nombre_de_empresa,
        invitado_por=mensaje.invitado_por,
        enlace=_enlace(url_base, mensaje.token),
        vence=mensaje.expira_en.strftime(FORMATO_DE_FECHA),
    )


def _armar(mensaje: MensajeDeInvitacion, config: ConfiguracionSMTP) -> EmailMessage:
    correo = EmailMessage()
    correo["From"] = config.remitente
    correo["To"] = str(mensaje.destinatario)
    correo["Subject"] = f"Te invitaron a {mensaje.nombre_de_empresa} en CheatSheet"
    correo.set_content(_render("invitacion.txt", mensaje, config.url_base_de_la_app))
    correo.add_alternative(
        _render("invitacion.html", mensaje, config.url_base_de_la_app), subtype="html"
    )
    return correo


class EnviadorSMTP:
    """Implements `PortEnvioDeEmail`."""

    def __init__(self, config: ConfiguracionSMTP) -> None:
        self._config = config

    async def enviar_invitacion(self, mensaje: MensajeDeInvitacion) -> None:
        try:
            await aiosmtplib.send(
                _armar(mensaje, self._config),
                hostname=self._config.host,
                port=self._config.puerto,
                username=self._config.usuario or None,
                password=self._config.contrasena or None,
                start_tls=self._config.usar_tls,
                timeout=self._config.timeout_segundos,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            # Narrow on purpose: `OSError` covers the connection and timeout failures
            # aiosmtplib lets through, and nothing else is swallowed. The task above
            # decides whether to retry.
            logger.warning(
                "envio_de_invitacion_fallido",
                destinatario=str(mensaje.destinatario),
                tipo=type(exc).__name__,
            )
            raise EnvioDeEmailFallido(
                f"No se pudo enviar la invitacion: {type(exc).__name__}"
            ) from exc
        logger.info("invitacion_enviada", destinatario=str(mensaje.destinatario))


class EnviadorDeConsola:
    """Implements `PortEnvioDeEmail`. Development and tests only.

    Prints the acceptance link, which is the point: without a mail server there has to be
    some way to complete the flow. It is selected by `EMAIL_ADAPTADOR=consola`, and
    `crear_enviador` refuses to select it in production.
    """

    def __init__(self, url_base_de_la_app: str) -> None:
        self._url_base = url_base_de_la_app

    async def enviar_invitacion(self, mensaje: MensajeDeInvitacion) -> None:
        logger.info(
            "invitacion_no_enviada_modo_consola",
            destinatario=str(mensaje.destinatario),
            empresa=mensaje.nombre_de_empresa,
            enlace=_enlace(self._url_base, mensaje.token),
            vence=mensaje.expira_en.isoformat(),
        )
