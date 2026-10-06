"""`Dialogo` ↔ JSON, para la columna `conversacion.dialogo` (T2).

En el dominio el diálogo es un value object tipado; **el JSON existe sólo acá**, en el borde con la
base. Lleva una clave `version` para poder evolucionar el formato sin una migración de datos: un
JSON de otra versión, o ilegible, no se interpreta (ver `RepositorioConversacionPostgres`).

Las fechas viajan en ISO 8601 con zona, los ids como texto, y los enums por su valor. Nada de lo
que se lee de acá se ejecuta: se reconstruye un `Dialogo` que **vuelve a validar sus invariantes**
al construirse.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from uuid import UUID

from cheatsheet.contexts.conversational.domain.dialogo import (
    Dialogo,
    Opcion,
    OpcionDeHorario,
    OpcionDeServicio,
    OpcionDeTurno,
    PasoDelDialogo,
)
from cheatsheet.contexts.conversational.domain.pedido_de_turno import (
    AccionDeTurno,
    Cuando,
    MomentoDelDia,
    PedidoDeTurno,
    ReferenciaDeDia,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

logger = obtener_logger(__name__)

#: La versión del formato que se escribe. Cualquier otra se lee como «sin diálogo».
VERSION_DEL_FORMATO = 1


def dialogo_a_json(dialogo: Dialogo) -> dict[str, Any]:
    return {
        "version": VERSION_DEL_FORMATO,
        "paso": dialogo.paso.value,
        "abierto_en": dialogo.abierto_en.isoformat(),
        "vence_en": dialogo.vence_en.isoformat(),
        "servicio_id": None if dialogo.servicio_id is None else str(dialogo.servicio_id),
        "pedido": None if dialogo.pedido is None else _pedido_a_json(dialogo.pedido),
        "opciones": [_opcion_a_json(uno) for uno in dialogo.opciones],
    }


def dialogo_de_json(crudo: dict[str, Any]) -> Dialogo:
    """Reconstruye el diálogo. Levanta `ValueError` si la versión no es la que se escribe.

    Cualquier otra falla de forma (`KeyError`, `TypeError`) o de invariantes
    (`InvarianteViolada`, `EntradaInvalida`) también sale: quien llama decide qué hacer.
    """
    if crudo.get("version") != VERSION_DEL_FORMATO:
        raise ValueError(f"Versión de diálogo desconocida: {crudo.get('version')!r}")
    servicio_id = crudo["servicio_id"]
    pedido = crudo["pedido"]
    return Dialogo(
        paso=PasoDelDialogo(crudo["paso"]),
        abierto_en=datetime.fromisoformat(crudo["abierto_en"]),
        vence_en=datetime.fromisoformat(crudo["vence_en"]),
        servicio_id=None if servicio_id is None else UUID(servicio_id),
        pedido=None if pedido is None else _pedido_de_json(pedido),
        opciones=tuple(_opcion_de_json(uno) for uno in crudo["opciones"]),
    )


def leer_dialogo_guardado(crudo: dict[str, Any] | None, *, conversacion_id: UUID) -> Dialogo | None:
    """El diálogo guardado, o `None` si no hay **o no se pudo leer**.

    Un JSON ilegible o de una versión que no conocemos se lee como «sin diálogo» y se registra:
    **nunca se reserva ni se cancela sobre algo que no se pudo leer**. El cliente recibe una
    repregunta, que es lo barato de equivocarse.
    """
    if crudo is None:
        return None
    try:
        return dialogo_de_json(crudo)
    except (AttributeError, KeyError, TypeError, ValueError, InvarianteViolada, EntradaInvalida):
        logger.warning("dialogo_ilegible", conversacion=str(conversacion_id))
        return None


def _opcion_a_json(opcion: Opcion) -> dict[str, Any]:
    if isinstance(opcion, OpcionDeServicio):
        return {"tipo": "servicio", "id": str(opcion.id), "nombre": opcion.nombre}
    if isinstance(opcion, OpcionDeHorario):
        return {
            "tipo": "horario",
            "inicio": opcion.inicio.isoformat(),
            "servicio_id": str(opcion.servicio_id),
            "recursos": [str(uno) for uno in opcion.recursos],
        }
    return {
        "tipo": "turno",
        "turno_id": str(opcion.turno_id),
        "servicio": opcion.servicio,
        "inicio": opcion.inicio.isoformat(),
        "tiene_sena": opcion.tiene_sena,
    }


def _opcion_de_json(crudo: dict[str, Any]) -> Opcion:
    tipo = crudo["tipo"]
    if tipo == "servicio":
        return OpcionDeServicio(id=UUID(crudo["id"]), nombre=str(crudo["nombre"]))
    if tipo == "horario":
        return OpcionDeHorario(
            inicio=datetime.fromisoformat(crudo["inicio"]),
            servicio_id=UUID(crudo["servicio_id"]),
            recursos=tuple(UUID(uno) for uno in crudo["recursos"]),
        )
    if tipo == "turno":
        return OpcionDeTurno(
            turno_id=UUID(crudo["turno_id"]),
            servicio=str(crudo["servicio"]),
            inicio=datetime.fromisoformat(crudo["inicio"]),
            tiene_sena=bool(crudo["tiene_sena"]),
        )
    raise ValueError(f"Tipo de opción desconocido: {tipo!r}")


def _pedido_a_json(pedido: PedidoDeTurno) -> dict[str, Any]:
    return {
        "accion": pedido.accion.value,
        "cuandos": [
            {
                "referencia": uno.referencia.value,
                "dia_semana": uno.dia_semana,
                "dia": uno.dia,
                "mes": uno.mes,
            }
            for uno in pedido.cuandos
        ],
        "momento": None if pedido.momento is None else pedido.momento.value,
        "hora": None if pedido.hora is None else pedido.hora.isoformat(timespec="minutes"),
        "servicio": pedido.servicio,
    }


def _pedido_de_json(crudo: dict[str, Any]) -> PedidoDeTurno:
    momento = crudo["momento"]
    hora = crudo["hora"]
    return PedidoDeTurno(
        accion=AccionDeTurno(crudo["accion"]),
        cuandos=tuple(
            Cuando(
                referencia=ReferenciaDeDia(uno["referencia"]),
                dia_semana=uno["dia_semana"],
                dia=uno["dia"],
                mes=uno["mes"],
            )
            for uno in crudo["cuandos"]
        ),
        momento=None if momento is None else MomentoDelDia(momento),
        hora=None if hora is None else time.fromisoformat(hora),
        servicio=crudo["servicio"],
    )


__all__ = ["VERSION_DEL_FORMATO", "dialogo_a_json", "dialogo_de_json", "leer_dialogo_guardado"]
