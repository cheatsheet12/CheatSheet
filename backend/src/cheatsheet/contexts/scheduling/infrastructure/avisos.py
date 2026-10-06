"""Por dónde sale el aviso de un turno (HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04): WhatsApp (U5).

`AvisoPorWhatsApp` arma el texto del aviso y lo manda por el canal que el composition root le
pasa (ADR-0011). **No importa a `conversational`** (R3): el canal es un `Protocol` local,
`CanalDeTexto`, que el cliente de la Cloud API satisface por estructura.

**Nunca levanta.** `Avisador` promete que «ningún método levanta por no poder avisar», y esa
promesa la sostiene este adaptador: un turno cancelado sigue cancelado aunque Meta esté caída
(D33), así que cualquier excepción del canal es un log y nada más. El `except` es amplio porque
el adaptador no puede importar las excepciones de `conversational`; el código de Meta ya quedó en
el log del canal. Fuera de la ventana de 24 h Meta sólo acepta plantillas (error 131047): hasta
la unidad `plantillas-de-whatsapp-en-meta`, ese aviso se loguea y el turno sigue.

**El texto del mensaje se arma acá.** La tabla `plantilla_de_notificacion` es de
`business_config` (HU-E11-02) y los textos configurables llegan con U6; mientras tanto el mensaje
vive en el adaptador que lo manda, que es el lugar correcto para un texto que hoy no es
configurable.

Ningún log lleva el nombre, el teléfono, el recurso ni el texto: son datos personales
(`CLAUDE.md` §5). Lo que se registra es qué clase de aviso falló y la clase de la excepción.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso
from cheatsheet.contexts.scheduling.domain.recurso import ZONA_DE_LA_AGENDA
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

FORMATO_FECHA = "%d/%m/%Y a las %H:%M"


class CanalDeTexto(Protocol):
    """Lo único que `scheduling` necesita del canal: mandar un texto y recibir el id."""

    async def enviar(self, *, telefono: str, texto: str) -> str: ...


def _fecha(instante: datetime) -> str:
    """El instante en la hora **del local**, no en UTC (H3).

    Un turno leído de la base llega en UTC; sin convertir, el cliente leería una hora tres horas
    corrida.
    """
    return instante.astimezone(ZONA_DE_LA_AGENDA).strftime(FORMATO_FECHA)


def texto_de_reserva(datos: DatosDeAviso) -> str:
    return (
        f"Hola {datos.nombre_del_cliente}, te confirmamos tu turno de {datos.servicio} "
        f"con {datos.recurso} el {_fecha(datos.inicio)}."
    )


def texto_de_cancelacion(datos: DatosDeAviso) -> str:
    return (
        f"Hola {datos.nombre_del_cliente}, tu turno de {datos.servicio} del "
        f"{_fecha(datos.inicio)} fue cancelado. "
        "Escribinos si querés reprogramarlo."
    )


def texto_de_reprogramacion(datos: DatosDeAviso) -> str:
    """Dice el horario **nuevo** y también el viejo.

    Sólo el nuevo dejaría a alguien que ya tenía el turno anotado sin saber si es el mismo o
    uno más — que es la manera de que aparezca en el horario equivocado.
    """
    anterior = (
        f" (antes {_fecha(datos.inicio_anterior)})" if datos.inicio_anterior is not None else ""
    )
    return (
        f"Hola {datos.nombre_del_cliente}, tu turno de {datos.servicio} pasó al "
        f"{_fecha(datos.inicio)}{anterior}."
    )


class AvisoPorWhatsApp:
    """`PortNotificadorDeTurnos` sobre el canal de WhatsApp de la empresa."""

    def __init__(self, canal: CanalDeTexto) -> None:
        self._canal = canal

    async def avisar_reserva(self, datos: DatosDeAviso) -> None:
        await self._mandar("reserva", datos, texto_de_reserva(datos))

    async def avisar_cancelacion(self, datos: DatosDeAviso) -> None:
        await self._mandar("cancelacion", datos, texto_de_cancelacion(datos))

    async def avisar_reprogramacion(self, datos: DatosDeAviso) -> None:
        await self._mandar("reprogramacion", datos, texto_de_reprogramacion(datos))

    async def _mandar(self, clase: str, datos: DatosDeAviso, texto: str) -> None:
        try:
            await self._canal.enviar(telefono=datos.telefono, texto=texto)
        except Exception as exc:  # noqa: BLE001 — ver el docstring del módulo
            # Acotado por el motivo: este adaptador no puede importar las excepciones de
            # `conversational` (R3), y **ningún fallo del canal puede voltear el turno**. Sólo
            # la clase de la excepción, nunca su texto: puede traer el número.
            logger.warning("aviso_de_turno_fallido", clase=clase, causa=type(exc).__name__)


__all__ = [
    "AvisoPorWhatsApp",
    "CanalDeTexto",
    "texto_de_cancelacion",
    "texto_de_reprogramacion",
    "texto_de_reserva",
]
