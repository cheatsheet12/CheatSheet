"""Transactional email for the invitation (HU-E1-04 RN-02).

Two adapters behind one port, chosen by configuration:

- **`EnviadorSMTP`** — production. Composes the message and hands it to the shared
  transport in `platform/email.py`; the socket, its timeout and its failure translation
  live there now (decision D-b of `conexion-whatsapp`). What stayed here is what is
  identity's alone: the template, the subject, and the rule that the token never reaches
  a log.
- **`EnviadorDeConsola`** — local development and tests. Writes to the structured log and
  **opens no socket**, so the suite can exercise the whole flow without a mail server.
  It does not use the shared transport at all: printing the acceptance link *is* its job,
  and a generic transport that dumped enough to make that work would be dumping message
  bodies for every context.

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

from email.message import EmailMessage
from pathlib import Path
from string import Template

from cheatsheet.contexts.identity.application.errors import EnvioDeEmailFallido
from cheatsheet.contexts.identity.application.ports import MensajeDeInvitacion
from cheatsheet.platform.email import ErrorDeEnvioDeEmail, TransporteDeEmail
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

PLANTILLAS = Path(__file__).parent / "plantillas"
FORMATO_DE_FECHA = "%d/%m/%Y a las %H:%M UTC"


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


def _armar(mensaje: MensajeDeInvitacion, remitente: str, url_base: str) -> EmailMessage:
    correo = EmailMessage()
    correo["From"] = remitente
    correo["To"] = str(mensaje.destinatario)
    correo["Subject"] = f"Te invitaron a {mensaje.nombre_de_empresa} en CheatSheet"
    correo.set_content(_render("invitacion.txt", mensaje, url_base))
    correo.add_alternative(_render("invitacion.html", mensaje, url_base), subtype="html")
    return correo


class EnviadorSMTP:
    """Implements `PortEnvioDeEmail`.

    The socket belongs to `platform/email.py`; what belongs here is the message and the
    two things nobody else can get right about it — that the subject names the company,
    and that **the token never reaches a log**. The logging stayed on this side for that
    second reason: a shared transport logging a body would defeat it.
    """

    def __init__(self, transporte: TransporteDeEmail, url_base_de_la_app: str) -> None:
        self._transporte = transporte
        self._url_base = url_base_de_la_app

    async def enviar_invitacion(self, mensaje: MensajeDeInvitacion) -> None:
        correo = _armar(mensaje, self._transporte.remitente, self._url_base)
        try:
            await self._transporte.enviar(correo)
        except ErrorDeEnvioDeEmail as exc:
            # Re-raised as the context's own error: the task above decides whether to
            # retry, and it should not have to know what a transport is.
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
