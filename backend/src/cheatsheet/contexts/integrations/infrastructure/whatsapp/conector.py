"""Connecting a WhatsApp Business number (HU-E2-03).

**The Administrator pastes the credentials — decision D-f.** Meta's own recommendation is
Embedded Signup, a popup from the Facebook JS SDK, and it is a better experience by far.
It also requires an approved Meta app, which does not exist yet, so it cannot be built or
demonstrated today. The manual form is what works now; the swap is one adapter and one
component when the app is approved, and it is recorded in the epic's TODO.

Two calls, in this order, and the order is the point: first confirm the number belongs to
the account that was declared, then read its verification state. Doing it the other way
would report a healthy number that belongs to somebody else.
"""

from __future__ import annotations

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    ResultadoDeConexion,
)
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.whatsapp.cliente import ClienteGraph
from cheatsheet.contexts.integrations.infrastructure.whatsapp.mapeo import (
    CLAVE_PHONE_NUMBER_ID,
    CLAVE_WABA_ID,
    interpretar,
)


def _identificador(material: MaterialDeConexion, clave: str, que_es: str) -> str:
    valor = material.parametros.get(clave)
    if not isinstance(valor, str) or not valor.strip():
        raise ConexionRechazada(f"Falta {que_es} de WhatsApp Business")
    return valor.strip()


class ConectorWhatsApp:
    """Implements `PortConectorDeIntegracion`."""

    def __init__(self, cliente: ClienteGraph) -> None:
        self._cliente = cliente

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        token = material.contenido.decode("utf-8", errors="ignore").strip()
        if not token:
            raise ConexionRechazada("Falta el token de acceso de WhatsApp Business")
        phone_number_id = _identificador(material, CLAVE_PHONE_NUMBER_ID, "el ID del numero")
        waba_id = _identificador(material, CLAVE_WABA_ID, "el ID de la cuenta")

        await self._exigir_que_el_numero_sea_de_la_cuenta(
            token=token, waba_id=waba_id, phone_number_id=phone_number_id
        )
        datos = await self._cliente.numero(token=token, phone_number_id=phone_number_id)
        resultado = interpretar(datos)

        if resultado.estado is EstadoDeConexion.NO_CONECTADO:
            # Meta answered and said no. Nothing is stored: HU-E2-03's third criterion
            # asks for the reason on screen and the integration left unconnected, and a
            # row in NO_CONECTADO would instead offer "Reconectar" for something that was
            # never connected.
            raise ConexionRechazada(resultado.detalle or "Meta rechazo el numero")

        return ResultadoDeConexion(
            credencial=token.encode("utf-8"),
            estado=resultado.estado,
            detalle=resultado.detalle,
            parametros={
                CLAVE_PHONE_NUMBER_ID: phone_number_id,
                CLAVE_WABA_ID: waba_id,
                **resultado.parametros,
            },
        )

    async def _exigir_que_el_numero_sea_de_la_cuenta(
        self, *, token: str, waba_id: str, phone_number_id: str
    ) -> None:
        """A token with access to several accounts must not be aimed by a typo.

        Meta would happily answer about a number the token can see but the company does
        not own; the company would then be sending messages from somebody else's line.
        """
        numeros = await self._cliente.numeros_de_la_cuenta(token=token, waba_id=waba_id)
        if not any(numero.get("id") == phone_number_id for numero in numeros):
            raise ConexionRechazada("El numero no pertenece a la cuenta de WhatsApp declarada")
