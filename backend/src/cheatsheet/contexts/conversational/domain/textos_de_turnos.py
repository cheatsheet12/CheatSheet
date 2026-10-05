"""Los textos con los que el agente habla de turnos.

Constantes y funciones en un solo lugar, como `MENSAJE_SIN_TURNOS`: las historias escriben varias
frases como «por ejemplo», pero cambiarlas tiene que ser un cambio y no una búsqueda.

**El formato de una fecha no depende del locale del servidor.** `strftime("%A")` devuelve el día en
el idioma de la máquina donde corre el proceso, y el agente le habla a clientes argentinos desde
cualquier contenedor. Los nombres están acá, a mano.

Función pura, sin I/O (R1).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from cheatsheet.contexts.conversational.domain.dialogo import (
    OpcionDeHorario,
    OpcionDeServicio,
    OpcionDeTurno,
)
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

# -- reservar ---------------------------------------------------------------------------

MENSAJE_PEDIR_CUANDO = "¿Para qué día te queda cómodo?"
MENSAJE_SIN_HORARIOS = (
    "No tengo horarios disponibles en los próximos días. ¿Querés que te derive con un asesor?"
)
MENSAJE_SIN_SERVICIOS = (
    "Por ahora no tengo servicios para reservar. ¿Querés que te derive con un asesor?"
)
MENSAJE_FECHA_PASADA = "Esa fecha ya pasó."
MENSAJE_HORARIO_OCUPADO = "Ese horario se acaba de ocupar."
MENSAJE_HORARIO_PASADO = "Ese horario ya pasó."
MENSAJE_OFERTA_VENCIDA = "Esos horarios ya no están vigentes; te paso los actuales:"
MENSAJE_SIN_LO_PEDIDO = "No tengo horarios para lo que pedís. Estos son los más cercanos:"
ENCABEZADO_DE_LA_OFERTA = "Tengo estos horarios disponibles:"
MENSAJE_NO_ENTENDI_LA_ELECCION = "No te entendí. Contestame con el número de la opción (por ejemplo, «el primero») o con la hora."

# -- cancelar ---------------------------------------------------------------------------

MENSAJE_TURNO_SIGUE = "Perfecto, tu turno sigue en pie."
MENSAJE_NO_CANCELABLE = "Ese turno ya no se puede cancelar desde acá."
MENSAJE_TURNO_CON_SENA = (
    "Ese turno tiene una seña abonada, y su cancelación la define una persona del negocio."
)


def formatear_inicio(inicio: datetime) -> str:
    """«jueves 14/10 a las 10:30», en hora argentina."""
    local = inicio.astimezone(ZONA_ARGENTINA)
    return f"{_DIAS[local.weekday()]} {local:%d/%m} a las {local:%H:%M}"


def oferta_de_horarios(opciones: Sequence[OpcionDeHorario], *, antes: str = "") -> str:
    """El listado numerado de horarios, con una frase delante si hace falta explicar algo.

    Una frase que termina en dos puntos ya presenta la lista («Estos son los más cercanos:»), así
    que reemplaza al encabezado en vez de sumarse a él: dos presentaciones seguidas se leían
    como un error (hallazgo H-T1, PRU-05 en staging).
    """
    renglones = [f"{n}) {formatear_inicio(uno.inicio)}" for n, uno in enumerate(opciones, 1)]
    presenta_la_lista = antes.rstrip().endswith(":")
    encabezado = [] if presenta_la_lista else [ENCABEZADO_DE_LA_OFERTA]
    cuerpo = "\n".join([*encabezado, *renglones])
    pie = "¿Cuál preferís? Contestame con el número o con la hora."
    return "\n".join(parte for parte in (antes, cuerpo, pie) if parte)


def oferta_de_un_horario(opcion: OpcionDeHorario, *, antes: str = "") -> str:
    cuerpo = f"Tengo disponible el {formatear_inicio(opcion.inicio)}. ¿Te lo reservo?"
    return "\n".join(parte for parte in (antes, cuerpo) if parte)


def pregunta_de_servicio(servicios: Sequence[OpcionDeServicio]) -> str:
    renglones = [f"{n}) {uno.nombre}" for n, uno in enumerate(servicios, 1)]
    return "\n".join(["¿Para qué servicio?", *renglones])


def reserva_confirmada(inicio: datetime) -> str:
    return f"Listo, tu turno quedó reservado para el {formatear_inicio(inicio)}."


def descripcion_de_turno(turno: OpcionDeTurno) -> str:
    return f"{turno.servicio} del {formatear_inicio(turno.inicio)}"


def listado_de_turnos(turnos: Sequence[OpcionDeTurno]) -> str:
    renglones = [f"{n}) {descripcion_de_turno(uno)}" for n, uno in enumerate(turnos, 1)]
    return "\n".join(["Tenés estos turnos:", *renglones, "¿Cuál querés cancelar?"])


def confirmar_cancelacion(turno: OpcionDeTurno) -> str:
    return f"¿Confirmás que cancelamos tu turno de {descripcion_de_turno(turno)}?"


def cancelacion_confirmada(turno: OpcionDeTurno) -> str:
    return f"Listo, cancelamos tu turno de {descripcion_de_turno(turno)}."


__all__ = [
    "ENCABEZADO_DE_LA_OFERTA",
    "MENSAJE_FECHA_PASADA",
    "MENSAJE_HORARIO_OCUPADO",
    "MENSAJE_HORARIO_PASADO",
    "MENSAJE_NO_CANCELABLE",
    "MENSAJE_NO_ENTENDI_LA_ELECCION",
    "MENSAJE_OFERTA_VENCIDA",
    "MENSAJE_PEDIR_CUANDO",
    "MENSAJE_SIN_HORARIOS",
    "MENSAJE_SIN_LO_PEDIDO",
    "MENSAJE_SIN_SERVICIOS",
    "MENSAJE_TURNO_CON_SENA",
    "MENSAJE_TURNO_SIGUE",
    "cancelacion_confirmada",
    "confirmar_cancelacion",
    "descripcion_de_turno",
    "formatear_inicio",
    "listado_de_turnos",
    "oferta_de_horarios",
    "oferta_de_un_horario",
    "pregunta_de_servicio",
    "reserva_confirmada",
]
