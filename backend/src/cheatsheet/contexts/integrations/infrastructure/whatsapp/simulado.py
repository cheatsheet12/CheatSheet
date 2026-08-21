"""A stand-in for Meta, for every environment without real credentials.

Same guard rails as `ProveedorOAuthSimulado` in identity and as the generic stand-ins of
the previous unit: it validates nothing against a real service, and **constructing it in
`production` raises** — a `RuntimeError` at build time, before the process serves a
request.

**It fabricates a Graph API payload and runs it through the real `interpretar`.** That is
deliberate and it is what makes this stand-in worth having: the simulated path and the
production path share the entire Anti-Corruption Layer, so a mapping bug shows up on a
laptop instead of on the day the first real number is connected. Only the socket is
missing.

The lifecycle is driven by a parameter rather than a timer, so a demo does not have to
wait 72 hours: connect with `simulado_name_status: "APPROVED"` and the next poll resolves.
Left unset it stays `PENDING_REVIEW`, which is what really happens.
"""

from __future__ import annotations

from typing import Any

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    ResultadoDeConexion,
    ResultadoDeVerificacion,
)
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion, SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.whatsapp.mapeo import (
    CLAVE_PHONE_NUMBER_ID,
    CLAVE_WABA_ID,
    interpretar,
)
from cheatsheet.platform.settings import Entorno

#: Drives the simulated lifecycle. Any `name_status` Meta can return is accepted, so the
#: unknown-value branch of the ACL is reachable from the running app too.
PARAMETRO_NAME_STATUS = "simulado_name_status"
PARAMETRO_CALIDAD = "simulado_quality_rating"

NAME_STATUS_POR_DEFECTO = "PENDING_REVIEW"
NOMBRE_SIMULADO = "Comercio de Prueba"
NUMERO_SIMULADO = "+54 9 11 5555-0000"


def _rechazar_en_produccion(entorno: Entorno) -> None:
    if entorno is Entorno.PRODUCTION:
        raise RuntimeError(
            f"El adaptador simulado de {SistemaExterno.WHATSAPP.value} no puede usarse en "
            f"produccion. Configura las credenciales reales de Meta."
        )


def _payload(parametros: dict[str, Any]) -> dict[str, Any]:
    """A Graph API phone-number object, shaped exactly like the real one."""
    crudo = parametros.get(PARAMETRO_NAME_STATUS)
    calidad = parametros.get(PARAMETRO_CALIDAD)
    return {
        "name_status": crudo if isinstance(crudo, str) and crudo else NAME_STATUS_POR_DEFECTO,
        "verified_name": NOMBRE_SIMULADO,
        "quality_rating": calidad if isinstance(calidad, str) and calidad else "GREEN",
        "display_phone_number": NUMERO_SIMULADO,
        "code_verification_status": "VERIFIED",
    }


class WhatsAppSimulado:
    """Implements `PortConectorDeIntegracion` and `PortVerificadorDeConexion`."""

    def __init__(self, entorno: Entorno) -> None:
        _rechazar_en_produccion(entorno)

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        """Checks the same three fields the real connector needs, and nothing else.

        Checking them matters: the form on PAN-CFG-INT is validated against this adapter
        during development, so a stand-in that accepted anything would let a missing field
        reach production unnoticed.
        """
        if not material.contenido.strip():
            raise ConexionRechazada("Falta el token de acceso de WhatsApp Business")
        for clave, que_es in (
            (CLAVE_PHONE_NUMBER_ID, "el ID del numero"),
            (CLAVE_WABA_ID, "el ID de la cuenta"),
        ):
            valor = material.parametros.get(clave)
            if not isinstance(valor, str) or not valor.strip():
                raise ConexionRechazada(f"Falta {que_es} de WhatsApp Business")

        resultado = interpretar(_payload(material.parametros))
        if resultado.estado is EstadoDeConexion.NO_CONECTADO:
            raise ConexionRechazada(resultado.detalle or "Meta rechazo el numero")
        return ResultadoDeConexion(
            credencial=material.contenido,
            estado=resultado.estado,
            detalle=resultado.detalle,
            # The simulation parameters are carried onto the row on purpose: the poll that
            # runs 30 minutes later has to find the same scenario the operator set up.
            parametros={**material.parametros, **resultado.parametros},
        )

    async def verificar(
        self,
        credencial: bytes,  # noqa: ARG002 — a stand-in has nothing to check it against
        parametros: dict[str, Any],
    ) -> ResultadoDeVerificacion:
        return interpretar(_payload(parametros))
