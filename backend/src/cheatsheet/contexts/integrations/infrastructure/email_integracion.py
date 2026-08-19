"""Telling the Administrator that a provider answered while nobody was looking.

HU-E2-03's second and third acceptance criteria happen 24 to 72 hours after the button was
pressed. There is no screen open by then, so the notice has to reach out.

**Email, not the notification centre.** HU-E11-03 builds a real notification centre and it
belongs to epic 10; until then a transactional email is the only push channel that exists.
When the centre lands, this adapter becomes one of its senders — the port above it does not
change.

The socket comes from `platform/email.py` (decision D-b). What lives here is what is this
context's own: which template, which subject, and the rule that **no credential is ever
mentioned** — the message names the system and the reason, never the token, the number's
identifier or the account.
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from string import Template

from cheatsheet.contexts.integrations.application.ports import AvisoDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion, SistemaExterno
from cheatsheet.platform.email import ErrorDeEnvioDeEmail, TransporteDeEmail
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

PLANTILLAS = Path(__file__).parent / "plantillas"

#: What a person calls each system. The enum values are for machines.
NOMBRES: dict[SistemaExterno, str] = {
    SistemaExterno.ARCA: "ARCA",
    SistemaExterno.MERCADOPAGO: "MercadoPago",
    SistemaExterno.WHATSAPP: "WhatsApp Business",
    SistemaExterno.GOOGLE_SHEETS: "Google Sheets",
    SistemaExterno.EXCEL_ONLINE: "Excel Online",
}

#: Where the Administrator goes to act on it — PAN-CFG-INT, decision D7 of the units map.
RUTA_DE_INTEGRACIONES = "/configuracion/integraciones"

#: One template per state, and **not** one per provider. The provider-specific wording —
#: "el certificado vence en 20 dias", "Meta rechazo el nombre para mostrar" — travels in
#: `detalle`, written by each Anti-Corruption Layer. A branch on `sistema` here would put
#: ARCA's vocabulary inside a module that is supposed to know nothing about it.
PLANTILLAS_POR_ESTADO: dict[EstadoDeConexion, str] = {
    EstadoDeConexion.CONECTADO: "integracion_conectada",
    EstadoDeConexion.ATENCION: "integracion_en_atencion",
    EstadoDeConexion.NO_CONECTADO: "integracion_desconectada",
    EstadoDeConexion.PENDIENTE: "integracion_desconectada",
}

ASUNTOS: dict[EstadoDeConexion, str] = {
    EstadoDeConexion.CONECTADO: "{nombre} quedo conectado en CheatSheet",
    EstadoDeConexion.ATENCION: "{nombre} necesita tu atencion en CheatSheet",
    EstadoDeConexion.NO_CONECTADO: "No pudimos conectar {nombre} en CheatSheet",
    EstadoDeConexion.PENDIENTE: "No pudimos conectar {nombre} en CheatSheet",
}


def _render(archivo: str, *, sistema: str, detalle: str, enlace: str) -> str:
    """`string.Template` on purpose — `$name` substitution and nothing else.

    Same rule the constitution sets for prompts: an f-string or Jinja over text that will
    eventually be edited outside the repository is an expression evaluator pointed at
    content nobody reviews as code.
    """
    plantilla = Template((PLANTILLAS / archivo).read_text(encoding="utf-8"))
    return plantilla.substitute(sistema=sistema, detalle=detalle, enlace=enlace)


class AvisoPorEmail:
    """Implements `PortAvisoDeIntegracion`."""

    def __init__(self, transporte: TransporteDeEmail, url_base_de_la_app: str) -> None:
        self._transporte = transporte
        self._url_base = url_base_de_la_app

    async def avisar(self, aviso: AvisoDeIntegracion) -> None:
        if not aviso.destinatarios:
            # Nobody to tell. Not an error: a company can be mid-onboarding with no
            # confirmed administrator address, and losing the state change over that
            # would be worse than a notice nobody receives.
            logger.info("aviso_de_integracion_sin_destinatarios", sistema=aviso.sistema.value)
            return

        nombre = NOMBRES.get(aviso.sistema, aviso.sistema.value)
        correo = EmailMessage()
        correo["From"] = self._transporte.remitente
        # One message per recipient would be the same content sent N times; `To` with the
        # full list is what a transactional notice about a shared resource actually is.
        correo["To"] = ", ".join(aviso.destinatarios)
        correo["Subject"] = ASUNTOS[aviso.estado].format(nombre=nombre)
        contexto = {
            "sistema": nombre,
            "detalle": aviso.detalle or "",
            "enlace": f"{self._url_base.rstrip('/')}{RUTA_DE_INTEGRACIONES}",
        }
        archivo = PLANTILLAS_POR_ESTADO[aviso.estado]
        correo.set_content(_render(f"{archivo}.txt", **contexto))
        correo.add_alternative(_render(f"{archivo}.html", **contexto), subtype="html")

        try:
            await self._transporte.enviar(correo)
        except ErrorDeEnvioDeEmail as exc:
            # Swallowed on purpose, unlike the invitation. The state change is already
            # committed and audited; turning a mail server outage into a failed Celery
            # task would retry the *poll*, and the poll is what writes the audit row.
            logger.warning(
                "aviso_de_integracion_no_enviado",
                sistema=aviso.sistema.value,
                tipo=type(exc).__name__,
            )
