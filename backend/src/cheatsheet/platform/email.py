"""Outbound email transport, shared by every context that has to send one.

**Why this moved here — decision D-b of `conexion-whatsapp`.** `identity` declared
`PortEnvioDeEmail` in epic 1 and its docstring left the question open on purpose:
"whether the adapter is worth extracting somewhere shared is a question for the second
consumer — answering it now, with one, would be guessing the shape the second needs."
`integrations` is that second consumer, and the answer turns out to be narrow: what the
two share is the **socket**, not the message. So only the socket moved.

What is *not* here, deliberately:

- **No port.** A hexagonal port belongs to the `application/` layer of the context whose
  use case needs it, and both contexts keep theirs (`PortEnvioDeEmail`,
  `PortAvisoDeIntegracion`). `TransporteDeEmail` below is an infrastructure detail that
  only other `infrastructure/` modules touch — which is why it is not called `Port…`.
- **No templates and no subjects.** The text a person reads is the context's business,
  reviewed and versioned with it.

`integrations` reaching into `identity/infrastructure/` for the SMTP client would have
broken R3, and copying it would have left two implementations of the same timeout to
drift apart — with `payments` (epic 6) inheriting the problem multiplied by three.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from cheatsheet.platform.settings import AdaptadorDeEmail, Settings
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)


class ErrorDeEnvioDeEmail(RuntimeError):
    """The message could not be handed to the mail server.

    Each context wraps this in its own application error — `EnvioDeEmailFallido` in
    `identity` — because what a failed send *means* differs: a lost invitation is
    recoverable by resending, a lost integration notice is not.
    """


@dataclass(frozen=True, slots=True)
class ConfiguracionSMTP:
    """Where the mail server is and how long we are willing to wait for it."""

    host: str
    puerto: int
    usuario: str
    contrasena: str
    remitente: str
    usar_tls: bool
    timeout_segundos: int


class TransporteDeEmail(Protocol):
    """Puts one already-composed message on the wire.

    Takes an `EmailMessage` rather than fields: composing the message — subject, bodies,
    template — is the sending context's job, and a transport that knew about subjects
    would have to grow a parameter per context.
    """

    @property
    def remitente(self) -> str:
        """The `From` header to stamp, so callers do not each read settings for it."""
        ...

    async def enviar(self, correo: EmailMessage) -> None:
        """Raises `ErrorDeEnvioDeEmail`. The caller decides whether that is fatal."""
        ...


class TransporteSMTP:
    """Implements `TransporteDeEmail`. SMTP rather than a provider SDK.

    Which transactional provider is used (SendGrid, Postmark, SES) stays a deployment
    decision instead of a line in `pyproject.toml`. Explicit timeout, as CLAUDE.md §5
    requires of every outbound call; the retry with backoff belongs to the Celery task,
    which is what survives a restart.
    """

    def __init__(self, config: ConfiguracionSMTP) -> None:
        self._config = config

    @property
    def remitente(self) -> str:
        return self._config.remitente

    async def enviar(self, correo: EmailMessage) -> None:
        destinatario = str(correo["To"])
        try:
            await aiosmtplib.send(
                correo,
                hostname=self._config.host,
                port=self._config.puerto,
                username=self._config.usuario or None,
                password=self._config.contrasena or None,
                start_tls=self._config.usar_tls,
                timeout=self._config.timeout_segundos,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            # Narrow on purpose: `OSError` covers the connection and timeout failures
            # aiosmtplib lets through, and nothing else is swallowed.
            logger.warning(
                "envio_de_email_fallido", destinatario=destinatario, tipo=type(exc).__name__
            )
            raise ErrorDeEnvioDeEmail(f"No se pudo enviar el correo: {type(exc).__name__}") from exc
        logger.info("email_enviado", destinatario=destinatario, asunto=str(correo["Subject"]))


class TransporteDeConsola:
    """Implements `TransporteDeEmail`. Development and tests — **opens no socket**.

    Logs the envelope and the subject, never the body. A body can carry a token, and the
    context that has a link worth printing during development prints it itself, from the
    message it already holds, instead of hoping a generic transport dumps enough.
    """

    def __init__(self, remitente: str) -> None:
        self._remitente = remitente

    @property
    def remitente(self) -> str:
        return self._remitente

    async def enviar(self, correo: EmailMessage) -> None:
        logger.info(
            "email_no_enviado_modo_consola",
            destinatario=str(correo["To"]),
            asunto=str(correo["Subject"]),
        )


def configuracion_smtp(settings: Settings) -> ConfiguracionSMTP:
    return ConfiguracionSMTP(
        host=settings.smtp_host,
        puerto=settings.smtp_port,
        usuario=settings.smtp_usuario,
        contrasena=settings.smtp_password,
        remitente=settings.smtp_remitente,
        usar_tls=settings.smtp_tls,
        timeout_segundos=settings.smtp_timeout_segundos,
    )


def crear_transporte(settings: Settings) -> TransporteDeEmail:
    """Pick the transport. Process-lifetime: it holds no transaction.

    `Settings` has already refused `consola` in production, so this does not second-guess
    the choice — a validation that lives in two places gets relaxed in one of them.
    """
    if settings.email_adaptador is AdaptadorDeEmail.CONSOLA:
        return TransporteDeConsola(settings.smtp_remitente)
    return TransporteSMTP(configuracion_smtp(settings))
