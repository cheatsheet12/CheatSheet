"""Por dónde sale el aviso de un turno (HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04): WhatsApp (U5).

`AvisoPorWhatsApp` manda el aviso por el canal que el composition root le pasa (ADR-0011). **No
importa a `conversational` ni a `business_config`** (R3): el canal y las plantillas son `Protocol`s
locales (`CanalDeTexto`, `PlantillasAprobadas`) que el cliente de la Cloud API y el caso de uso de
`business_config` satisfacen por estructura.

**Plantilla aprobada si la hay (U6).** Fuera de la ventana de 24 h Meta solo acepta plantillas, y
dentro de ella una plantilla de utilidad cuesta lo mismo que un texto: por eso, si la empresa tiene
aprobada la plantilla del aviso (`turno_confirmado`, `turno_cancelado` o `turno_reprogramado`), sale
**siempre** como plantilla. Si no, sale el texto de fabrica de este modulo, **nunca el cuerpo
editado de una plantilla no aprobada** (RN-04). El recordatorio de turno (`recordatorio_de_turno`)
no es de este adaptador: lo manda la unidad del barrido de turnos.

**Nunca levanta.** `Avisador` promete que «ningún método levanta por no poder avisar», y esa
promesa la sostiene este adaptador: un turno cancelado sigue cancelado aunque Meta esté caída
(D33), así que cualquier excepción del canal es un log y nada más. El `except` es amplio porque
el adaptador no puede importar las excepciones de `conversational`; el código de Meta ya quedó en
el log del canal. Sin plantilla aprobada, fuera de la ventana Meta contesta 131047: ese aviso se
loguea y el turno sigue.

**El texto de fábrica se arma acá.** Es el respaldo cuando no hay plantilla aprobada; el texto
configurable vive en `business_config` (HU-E11-02).

Ningún log lleva el nombre, el teléfono, el recurso ni el texto: son datos personales
(`CLAUDE.md` §5). Lo que se registra es qué clase de aviso falló y la clase de la excepción.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso
from cheatsheet.contexts.scheduling.domain.recurso import ZONA_DE_LA_AGENDA
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

#: Los códigos de plantilla de `business_config` (HU-E11-02) de cada aviso.
CODIGO_RESERVA = "turno_confirmado"
CODIGO_CANCELACION = "turno_cancelado"
CODIGO_REPROGRAMACION = "turno_reprogramado"


class CanalDeTexto(Protocol):
    """Lo único que `scheduling` necesita del canal: mandar un texto o una plantilla aprobada."""

    async def enviar(self, *, telefono: str, texto: str) -> str: ...

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str: ...


class PlantillaParaMandar(Protocol):
    """Lo que `scheduling` lee de una plantilla aprobada: cómo se llama en Meta y sus parámetros."""

    @property
    def nombre_en_meta(self) -> str: ...

    @property
    def idioma(self) -> str: ...

    @property
    def parametros(self) -> Mapping[str, str]: ...


class PlantillasAprobadas(Protocol):
    """La plantilla **aprobada** de un código, o `None` (no existe, no está aprobada, otro canal).

    La raíz de composición la respalda con `ConsultarPlantillaParaEnviar` de `business_config`.
    `None` significa «mandá tu texto de fábrica».
    """

    async def para(
        self, codigo: str, variables: Mapping[str, str]
    ) -> PlantillaParaMandar | None: ...


def _dia(instante: datetime) -> str:
    """El día del instante en la hora **del local**, no en UTC (H3).

    Un turno leído de la base llega en UTC; sin convertir, el cliente leería una hora tres horas
    corrida (y, de noche, un día corrido).
    """
    return instante.astimezone(ZONA_DE_LA_AGENDA).strftime("%d/%m/%Y")


def _hora(instante: datetime) -> str:
    return instante.astimezone(ZONA_DE_LA_AGENDA).strftime("%H:%M")


def _fecha(instante: datetime) -> str:
    return f"{_dia(instante)} a las {_hora(instante)}"


def variables_de_aviso(datos: DatosDeAviso) -> dict[str, str]:
    """Las variables de la plantilla de un aviso, todas `str`: `fecha` y `hora` por separado.

    Las del horario anterior solo van si el turno las trae: sin ellas la plantilla de
    reprogramación no se puede completar y el aviso sale como texto.
    """
    variables = {
        "nombre": datos.nombre_del_cliente,
        "servicio": datos.servicio,
        "recurso": datos.recurso,
        "fecha": _dia(datos.inicio),
        "hora": _hora(datos.inicio),
    }
    if datos.inicio_anterior is not None:
        variables["fecha_anterior"] = _dia(datos.inicio_anterior)
        variables["hora_anterior"] = _hora(datos.inicio_anterior)
    return variables


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

    def __init__(self, canal: CanalDeTexto, plantillas: PlantillasAprobadas) -> None:
        self._canal = canal
        self._plantillas = plantillas

    async def avisar_reserva(self, datos: DatosDeAviso) -> None:
        await self._mandar("reserva", CODIGO_RESERVA, datos, texto_de_reserva(datos))

    async def avisar_cancelacion(self, datos: DatosDeAviso) -> None:
        await self._mandar("cancelacion", CODIGO_CANCELACION, datos, texto_de_cancelacion(datos))

    async def avisar_reprogramacion(self, datos: DatosDeAviso) -> None:
        await self._mandar(
            "reprogramacion", CODIGO_REPROGRAMACION, datos, texto_de_reprogramacion(datos)
        )

    async def _mandar(self, clase: str, codigo: str, datos: DatosDeAviso, texto: str) -> None:
        try:
            plantilla = await self._plantillas.para(codigo, variables_de_aviso(datos))
            if plantilla is not None:
                await self._canal.enviar_plantilla(
                    telefono=datos.telefono,
                    nombre=plantilla.nombre_en_meta,
                    idioma=plantilla.idioma,
                    parametros=plantilla.parametros,
                )
            else:
                await self._canal.enviar(telefono=datos.telefono, texto=texto)
        except Exception as exc:  # noqa: BLE001 — ver el docstring del módulo
            # Acotado por el motivo: este adaptador no puede importar las excepciones de
            # `conversational` (R3), y **ningún fallo del canal puede voltear el turno**. Sólo
            # la clase de la excepción, nunca su texto: puede traer el número.
            logger.warning("aviso_de_turno_fallido", clase=clase, causa=type(exc).__name__)


__all__ = [
    "CODIGO_CANCELACION",
    "CODIGO_REPROGRAMACION",
    "CODIGO_RESERVA",
    "AvisoPorWhatsApp",
    "CanalDeTexto",
    "PlantillaParaMandar",
    "PlantillasAprobadas",
    "texto_de_cancelacion",
    "texto_de_reprogramacion",
    "texto_de_reserva",
    "variables_de_aviso",
]
