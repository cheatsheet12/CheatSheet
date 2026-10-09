"""`InvalidarDelegacionPorCambioDeCuit` — ADR-0014, found in the local test of 2026-10-08.

With delegation, the CUIT recorded on the ARCA integration decides on whose behalf documents
are authorised. If the company changes its CUIT and the integration stayed connected, a
document would be printed with the new CUIT (from `identity`) and authorised at ARCA with
the old one. So a CUIT change leaves ARCA not connected until the new CUIT's delegation is
verified.

Called by the composition root after `identity` saved the company: `integrations` learns
nothing about `identity`, it only receives the new CUIT.
"""

from __future__ import annotations

from datetime import datetime

from cheatsheet.contexts.integrations.application.integraciones import evento_auditable
from cheatsheet.contexts.integrations.application.ports import PortRepositorioIntegraciones
from cheatsheet.contexts.integrations.domain.valores import CLAVE_CUIT, SistemaExterno
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos

MOTIVO = (
    "La CUIT de la empresa cambio a {cuit}. Verifica de nuevo la delegacion de "
    "Facturacion Electronica en ARCA antes de facturar."
)


class InvalidarDelegacionPorCambioDeCuit:
    def __init__(
        self, *, integraciones: PortRepositorioIntegraciones, publicador: PublicadorDeEventos
    ) -> None:
        self._integraciones = integraciones
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        cuit: str,
        ahora: datetime,
        usuario_id: UsuarioId | None = None,
        direccion_ip: str | None = None,
    ) -> bool:
        """Returns whether the integration was invalidated."""
        digitos = "".join(c for c in cuit if c.isdigit())
        configuracion = await self._integraciones.buscar(empresa_id, SistemaExterno.ARCA)
        if configuracion is None:
            return False
        registrada = "".join(
            c for c in str(configuracion.parametros.get(CLAVE_CUIT, "")) if c.isdigit()
        )
        if registrada == digitos:
            return False
        cambio = configuracion.desactivar(MOTIVO.format(cuit=cuit), ahora)
        await self._integraciones.guardar(configuracion)
        if cambio is not None:
            await self._publicador.publicar(
                evento_auditable(
                    cambio,
                    empresa_id=empresa_id,
                    usuario_id=usuario_id,
                    direccion_ip=direccion_ip,
                    ahora=ahora,
                )
            )
        return True
