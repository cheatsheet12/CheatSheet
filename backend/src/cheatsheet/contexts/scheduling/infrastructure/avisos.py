"""Por dónde sale el aviso de un turno (HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04), y su doble.

WhatsApp es el canal que las historias nombran y el que el **épico 8** va a construir de
verdad, junto con el agente. Hasta entonces este adaptador es honesto sobre lo que hace:
registra el aviso y no finge una entrega.

Es el mismo trato que `payments` hizo con los recordatorios de cobro, y por el mismo motivo:
un doble que dijera «entregado» pondría en la pantalla un dato que nadie confirmó.

**El texto del mensaje se arma acá.** La tabla `plantilla_de_notificacion` del DER todavía no
existe —es del épico 8, HU-E11-02—, así que el mensaje vive en el adaptador que lo manda. Es
el lugar correcto para un texto que hoy no es configurable: en el dominio sería una regla de
negocio que no lo es, y en la aplicación sería presentación fuera de lugar.
"""

from __future__ import annotations

from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

FORMATO_FECHA = "%d/%m/%Y a las %H:%M"


def texto_de_reserva(datos: DatosDeAviso) -> str:
    return (
        f"Hola {datos.nombre_del_cliente}, te confirmamos tu turno de {datos.servicio} "
        f"con {datos.recurso} el {datos.inicio.strftime(FORMATO_FECHA)}."
    )


def texto_de_cancelacion(datos: DatosDeAviso) -> str:
    return (
        f"Hola {datos.nombre_del_cliente}, tu turno de {datos.servicio} del "
        f"{datos.inicio.strftime(FORMATO_FECHA)} fue cancelado. "
        "Escribinos si querés reprogramarlo."
    )


def texto_de_reprogramacion(datos: DatosDeAviso) -> str:
    """Dice el horario **nuevo** y también el viejo.

    Sólo el nuevo dejaría a alguien que ya tenía el turno anotado sin saber si es el mismo o
    uno más — que es la manera de que aparezca en el horario equivocado.
    """
    anterior = (
        f" (antes {datos.inicio_anterior.strftime(FORMATO_FECHA)})"
        if datos.inicio_anterior is not None
        else ""
    )
    return (
        f"Hola {datos.nombre_del_cliente}, tu turno de {datos.servicio} pasó al "
        f"{datos.inicio.strftime(FORMATO_FECHA)}{anterior}."
    )


class AvisoPorConsola:
    """El doble: deja el aviso en el log y no manda nada.

    **Rechazado en producción**, como los demás simulados. Una empresa cuyos avisos de turno
    salen a un log es una empresa cuyos clientes se enteran de la cancelación cuando llegan.

    No registra el teléfono ni el nombre del cliente: son datos personales, y `CLAUDE.md` §5
    los prohíbe en un log aunque el log sea de desarrollo. Lo que se registra es qué clase de
    aviso salió, que es lo que un test necesita afirmar.
    """

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El aviso por consola no puede usarse en producción: los clientes no "
                "recibirían ninguna notificación de sus turnos"
            )
        self.avisos: list[tuple[str, str]] = []

    async def avisar_reserva(self, datos: DatosDeAviso) -> None:
        self._registrar("reserva", datos, texto_de_reserva(datos))

    async def avisar_cancelacion(self, datos: DatosDeAviso) -> None:
        self._registrar("cancelacion", datos, texto_de_cancelacion(datos))

    async def avisar_reprogramacion(self, datos: DatosDeAviso) -> None:
        self._registrar("reprogramacion", datos, texto_de_reprogramacion(datos))

    def _registrar(self, clase: str, datos: DatosDeAviso, texto: str) -> None:
        self.avisos.append((clase, texto))
        logger.info(
            "aviso_de_turno_simulado",
            clase=clase,
            servicio=datos.servicio,
            recurso=datos.recurso,
        )


__all__ = [
    "AvisoPorConsola",
    "texto_de_cancelacion",
    "texto_de_reprogramacion",
    "texto_de_reserva",
]
