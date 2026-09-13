"""El mail con el enlace del contador (HU-E10-05 RN-01).

Dos adaptadores detrás de un puerto, elegidos por configuración, igual que la invitación del
épico 1: el que manda por SMTP a través del transporte compartido de `platform/email.py`, y el
de consola, que **no abre ningún socket** y por eso deja correr el flujo entero en una máquina
sin servidor de correo.

**Si el mail no sale, la invitación no ocurrió.** Es la decisión contraria a la del aviso de un
turno (D33) y a la del canal del agente (D48), y la diferencia es cuál es el hecho de negocio:
allá el turno ya estaba reservado y el aviso era una consecuencia; acá **el enlace es el mail**.
Un token guardado que nadie recibió no es un acceso compartido, es una fila que va a hacer que
la próxima invitación choque contra «ya hay un contador con acceso».

**El enlace nunca llega al log.** El adaptador de consola lo imprime porque imprimirlo *es* su
trabajo en desarrollo; el de SMTP registra el destinatario y nada más. Un enlace vivo en un log
agregado es la documentación fiscal de una empresa esperando a que alguien la mire.
"""

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from string import Template

from cheatsheet.contexts.reporting.application.errors import InvitacionNoEnviada
from cheatsheet.platform.email import ErrorDeEnvioDeEmail, TransporteDeEmail
from cheatsheet.platform.settings import AdaptadorDeEmail, Settings
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

PLANTILLAS = Path(__file__).parent / "plantillas"
FORMATO_DE_FECHA = "%d/%m/%Y"


def _render(nombre: str, *, empresa: str, enlace: str, vence: datetime) -> str:
    """`string.Template` y no una f-string, por lo mismo que las plantillas del épico 1: el
    texto que lee una persona se revisa y se versiona sin tocar código, y un renderizador que
    evalúa expresiones apuntado a texto editable es un intérprete regalado."""
    plantilla = Template((PLANTILLAS / nombre).read_text(encoding="utf-8"))
    return plantilla.substitute(
        empresa=empresa, enlace=enlace, vence=vence.strftime(FORMATO_DE_FECHA)
    )


def _armar(
    *, remitente: str, email: str, empresa: str, enlace: str, vence: datetime
) -> EmailMessage:
    correo = EmailMessage()
    correo["From"] = remitente
    correo["To"] = email
    correo["Subject"] = f"{empresa} te compartió su paquete contable"
    correo.set_content(_render("paquete.txt", empresa=empresa, enlace=enlace, vence=vence))
    correo.add_alternative(
        _render("paquete.html", empresa=empresa, enlace=enlace, vence=vence), subtype="html"
    )
    return correo


class AvisoAlContadorPorEmail:
    """`PortAvisoAlContador` sobre el transporte compartido."""

    def __init__(self, transporte: TransporteDeEmail) -> None:
        self._transporte = transporte

    async def enviar_enlace(
        self, *, email: str, enlace: str, empresa: str, vence: datetime
    ) -> None:
        correo = _armar(
            remitente=self._transporte.remitente,
            email=email,
            empresa=empresa,
            enlace=enlace,
            vence=vence,
        )
        try:
            await self._transporte.enviar(correo)
        except ErrorDeEnvioDeEmail as exc:
            logger.warning("aviso_al_contador_fallido", tipo=type(exc).__name__)
            raise InvitacionNoEnviada(
                "No se pudo enviar el correo al contador. Revisá el email e intentá de nuevo."
            ) from exc
        # El destinatario, nunca el enlace. Ver el docstring del módulo.
        logger.info("aviso_al_contador_enviado", destinatario=email)


class AvisoAlContadorPorConsola:
    """`PortAvisoAlContador` para desarrollo y tests. **No abre ningún socket.**

    Imprime el enlace, que es justamente lo que hace falta para completar el flujo sin un
    servidor de correo. `crear_aviso_al_contador` se niega a elegirlo en producción.
    """

    async def enviar_enlace(
        self, *, email: str, enlace: str, empresa: str, vence: datetime
    ) -> None:
        logger.info(
            "aviso_al_contador_no_enviado_modo_consola",
            destinatario=email,
            empresa=empresa,
            enlace=enlace,
            vence=vence.isoformat(),
        )


def crear_aviso_al_contador(
    settings: Settings, transporte: TransporteDeEmail
) -> AvisoAlContadorPorEmail | AvisoAlContadorPorConsola:
    """Cuál de los dos, según la configuración.

    `Settings` ya se negó a aceptar `consola` en producción, así que esto no vuelve a
    decidirlo: una validación que vive en dos lugares es una validación que alguien relaja en
    uno de los dos.
    """
    if settings.email_adaptador is AdaptadorDeEmail.CONSOLA:
        return AvisoAlContadorPorConsola()
    return AvisoAlContadorPorEmail(transporte)


__all__ = [
    "AvisoAlContadorPorConsola",
    "AvisoAlContadorPorEmail",
    "crear_aviso_al_contador",
]
