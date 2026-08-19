"""Re-reading the state of a number that is already stored.

Serves two callers with the same code, which is the reason it is one adapter and not two:
the on-screen check of HU-E2-05, and the background poll that waits out Meta's 24-to-72
hour review (HU-E2-03 RN-02).

It does **not** re-check that the number belongs to the account — the connector did that
once, and Meta cannot move a number into another account behind our back without the
number's state changing too.
"""

from __future__ import annotations

from typing import Any

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.application.ports import ResultadoDeVerificacion
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.whatsapp.cliente import ClienteGraph
from cheatsheet.contexts.integrations.infrastructure.whatsapp.mapeo import (
    CLAVE_PHONE_NUMBER_ID,
    interpretar,
)


class VerificadorWhatsApp:
    """Implements `PortVerificadorDeConexion`."""

    def __init__(self, cliente: ClienteGraph) -> None:
        self._cliente = cliente

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion:
        phone_number_id = parametros.get(CLAVE_PHONE_NUMBER_ID)
        if not isinstance(phone_number_id, str) or not phone_number_id:
            # The row was written without the identifier — nothing can be asked about it.
            # `ATENCION` rather than an exception: it is visible, and it is honestly what
            # this is, a configuration that answers no questions.
            return ResultadoDeVerificacion(
                EstadoDeConexion.ATENCION,
                "La integracion no tiene registrado el ID del numero de WhatsApp",
            )
        token = credencial.decode("utf-8", errors="ignore").strip()
        if not token:
            raise ProveedorNoDisponible("La credencial almacenada de WhatsApp esta vacia")
        datos = await self._cliente.numero(token=token, phone_number_id=phone_number_id)
        return interpretar(datos)
