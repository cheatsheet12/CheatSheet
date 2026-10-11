"""Lo que el agente dice cuando el negocio está cerrado (HS-T2 RN-04, HU-E8-05 RN-04).

**El modelo no decide si el negocio está abierto**: lo calcula `business_config` sobre la hora
argentina y llega acá ya resuelto, en el vocabulario de este contexto (`AtencionDelNegocio`,
traducido por el ACL de `infrastructure/horario.py`; R3). Esto son los textos fijos del sistema
—no editables por la empresa en esta unidad— y la regla de «una vez por período de cierre».

Funciones puras, sin I/O (R1). Las fechas se dicen en hora argentina y **sin depender del
locale** del servidor: los nombres de día salen de `textos_de_turnos`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cheatsheet.contexts.conversational.domain.conversacion import (
    MENSAJE_DERIVACION,
    DireccionMensaje,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
)
from cheatsheet.contexts.conversational.domain.textos_de_turnos import formatear_inicio
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA


class PoliticaFueraDeHorario(StrEnum):
    """Qué hace el agente cerrado. Propia de este contexto: no importa la de `business_config`."""

    AGENTE_RESPONDE = "AGENTE_RESPONDE"
    MENSAJE_FIJO = "MENSAJE_FIJO"


@dataclass(frozen=True, slots=True)
class AtencionDelNegocio:
    """Lo único que este contexto sabe del horario de atención.

    `proxima_apertura` es `None` cuando no hay ninguna en el horizonte; `cerrado_desde` es
    el último cierre (relevante sólo con el negocio cerrado).
    """

    abierto: bool
    politica: PoliticaFueraDeHorario
    proxima_apertura: datetime | None
    cerrado_desde: datetime | None


def cuando_se_atiende(proxima_apertura: datetime, ahora: datetime) -> str:
    """«hoy a las 16:00» · «mañana a las 09:00» · «el martes 13/10 a las 09:00».

    Compara **fechas locales**: el domingo a las 22:30 de Argentina ya es lunes en UTC, y la
    apertura del lunes es «mañana», no «hoy». La fecha desambigua aunque falte más de una semana.
    """
    apertura = proxima_apertura.astimezone(ZONA_ARGENTINA)
    dias = (apertura.date() - ahora.astimezone(ZONA_ARGENTINA).date()).days
    if dias == 0:
        return f"hoy a las {apertura:%H:%M}"
    if dias == 1:
        return f"mañana a las {apertura:%H:%M}"
    return f"el {formatear_inicio(apertura)}"


def _a_partir_de(cuando: str) -> str:
    """«de hoy…», «de mañana…», pero «del martes…» y no «de el martes…»."""
    return f"del {cuando[3:]}" if cuando.startswith("el ") else f"de {cuando}"


def aviso_de_derivacion(atencion: AtencionDelNegocio, ahora: datetime) -> str:
    """El aviso de derivación con el negocio cerrado: dice desde cuándo atiende un asesor."""
    base = f"{MENSAJE_DERIVACION} Ahora estamos fuera del horario de atención: "
    if atencion.proxima_apertura is None:
        return f"{base}un asesor te va a responder cuando retomemos la atención."
    cuando = cuando_se_atiende(atencion.proxima_apertura, ahora)
    return f"{base}un asesor te va a responder a partir {_a_partir_de(cuando)}."


def mensaje_fuera_de_horario(atencion: AtencionDelNegocio, ahora: datetime) -> str:
    """El mensaje fijo de la política (b)."""
    base = "Hola, gracias por escribirnos. En este momento estamos fuera del horario de atención"
    if atencion.proxima_apertura is None:
        return (
            f"{base} y todavía no tenemos fecha de regreso. "
            "Escribinos más adelante y te respondemos."
        )
    cuando = cuando_se_atiende(atencion.proxima_apertura, ahora)
    return (
        f"{base}. Atendemos de nuevo {cuando}: escribinos a partir de ese momento y te respondemos."
    )


def posdata_fuera_de_horario(atencion: AtencionDelNegocio, ahora: datetime) -> str:
    """La oración al final de la respuesta a un diálogo que se siguió de noche (política (b))."""
    base = "Te recordamos que ahora estamos fuera del horario de atención"
    if atencion.proxima_apertura is None:
        return f"{base}."
    return f"{base}; atendemos de nuevo {cuando_se_atiende(atencion.proxima_apertura, ahora)}."


def ya_avisado(mensajes: Iterable[Mensaje], desde: datetime) -> bool:
    """¿El agente ya le habló al cliente en este período de cierre? (T9)

    Mientras el negocio está cerrado en la política (b), **todo** saliente del agente lleva la
    información de fuera de horario, así que alcanza con mirar el origen y el momento: no se
    relee ningún texto. Los avisos del sistema (recordatorios) y los del operador no cuentan, ni
    uno que **no salió** (`FALLIDO`): el cliente nunca se enteró, y el próximo mensaje reintenta.
    """
    return any(
        mensaje.direccion is DireccionMensaje.SALIENTE
        and mensaje.origen is OrigenDelMensaje.AGENTE
        and mensaje.estado_entrega is not EstadoEntrega.FALLIDO
        and mensaje.momento >= desde
        for mensaje in mensajes
    )


__all__ = [
    "AtencionDelNegocio",
    "PoliticaFueraDeHorario",
    "aviso_de_derivacion",
    "cuando_se_atiende",
    "mensaje_fuera_de_horario",
    "posdata_fuera_de_horario",
    "ya_avisado",
]
