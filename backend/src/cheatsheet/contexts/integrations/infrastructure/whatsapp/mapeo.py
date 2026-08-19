"""Meta's vocabulary in, ours out. The whole Anti-Corruption Layer is this file.

Pure functions over the JSON Graph API returns, so the translation is testable without a
socket and the rest of the adapter is left doing nothing but HTTP.

**The catch-all matters more than the happy path.** Meta adds values to these enums
without announcing it, and a `KeyError` inside a Beat task is an integration that goes
quiet — the Administrator sees "Pendiente" forever and no error anywhere says why. So an
unrecognised status becomes `ATENCION` with the raw value in the detail: visible, honest,
and it destroys nothing.
"""

from __future__ import annotations

from typing import Any

from cheatsheet.contexts.integrations.application.ports import ResultadoDeVerificacion
from cheatsheet.contexts.integrations.domain.valores import CLAVE_ETIQUETA, EstadoDeConexion

#: Parameter keys this adapter writes onto the aggregate. Ours, not Meta's — the aggregate
#: is not supposed to learn a provider's field names.
CLAVE_PHONE_NUMBER_ID = "phone_number_id"
CLAVE_WABA_ID = "waba_id"
CLAVE_DISPLAY_NAME = "display_name"
CLAVE_CALIDAD = "calidad_de_linea"
CLAVE_NUMERO = "numero_visible"

#: `name_status` values that mean Meta is still reviewing (HU-E2-03 RN-02).
EN_REVISION = frozenset({"PENDING_REVIEW"})
#: Values that mean the number can be used.
APROBADOS = frozenset({"APPROVED", "AVAILABLE_WITHOUT_REVIEW"})
#: Values that mean Meta said no, mapped to the reason the Administrator reads.
RECHAZADOS: dict[str, str] = {
    "DECLINED": "Meta rechazo el nombre para mostrar del numero",
    "EXPIRED": "La verificacion del numero venció y hay que iniciarla de nuevo",
    "NONE": "El numero no tiene una verificacion iniciada en Meta",
}

#: A line Meta has flagged red is about to be restricted. That is `ATENCION`'s exact
#: definition — answering, and degraded — and surfacing it before the line stops working
#: is the difference between a warning and a support ticket.
CALIDAD_DEGRADADA = "RED"


def parametros_informados(datos: dict[str, Any]) -> dict[str, Any]:
    """What Meta told us about the number, in our field names (RN-03).

    Absent fields are simply not returned, so a partial response never blanks out what a
    previous complete one recorded.
    """
    leidos = {
        CLAVE_DISPLAY_NAME: datos.get("verified_name"),
        CLAVE_CALIDAD: datos.get("quality_rating"),
        CLAVE_NUMERO: datos.get("display_phone_number"),
    }
    informados = {c: v for c, v in leidos.items() if isinstance(v, str) and v}
    etiqueta = _etiqueta(informados)
    return {**informados, CLAVE_ETIQUETA: etiqueta} if etiqueta else informados


def _etiqueta(informados: dict[str, str]) -> str:
    """What the card shows under "WhatsApp Business" — the verified name and the number.

    The identifiers the Administrator pasted (`phone_number_id`, `waba_id`) are
    deliberately not here: they identify the account to Meta, they mean nothing to a
    person, and they have no business crossing the API when a name will do.
    """
    nombre = informados.get(CLAVE_DISPLAY_NAME, "")
    numero = informados.get(CLAVE_NUMERO, "")
    if nombre and numero:
        return f"{nombre} · {numero}"
    return nombre or numero


def interpretar(datos: dict[str, Any]) -> ResultadoDeVerificacion:
    """Turn one phone-number payload into a state, a reason and the fields to record."""
    parametros = parametros_informados(datos)
    estado_meta = datos.get("name_status")

    if not isinstance(estado_meta, str) or not estado_meta:
        return ResultadoDeVerificacion(
            EstadoDeConexion.ATENCION,
            "Meta no informo el estado de verificacion del numero",
            parametros,
        )
    if estado_meta in EN_REVISION:
        return ResultadoDeVerificacion(
            EstadoDeConexion.PENDIENTE,
            "Meta esta revisando el nombre para mostrar. Puede demorar entre 24 y 72 horas",
            parametros,
        )
    if estado_meta in RECHAZADOS:
        return ResultadoDeVerificacion(
            EstadoDeConexion.NO_CONECTADO, RECHAZADOS[estado_meta], parametros
        )
    if estado_meta in APROBADOS:
        if parametros.get(CLAVE_CALIDAD) == CALIDAD_DEGRADADA:
            return ResultadoDeVerificacion(
                EstadoDeConexion.ATENCION,
                "Meta califico la calidad de la linea como baja: puede restringirla",
                parametros,
            )
        return ResultadoDeVerificacion(EstadoDeConexion.CONECTADO, None, parametros)

    return ResultadoDeVerificacion(
        EstadoDeConexion.ATENCION,
        f"Meta informo un estado desconocido: {estado_meta}",
        parametros,
    )
