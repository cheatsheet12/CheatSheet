"""`RegistrarEntregaDeRecordatorio` — lo que Meta informa de un recordatorio de cobro (U7).

El callback `statuses[]` se rutea por el `wamid` que se guardó al enviar (`Recordatorio.externo_id`).
Sin rol: lo invoca el webhook, que ya validó la firma y resolvió la empresa. El estado vive en la
fila de `recordatorio` (PAN-COB-02, HU-E6-02 RN-01) y **no** se duplica como mensaje de la
conversación: dos estados para un mismo `wamid` serían dos verdades.

**Idempotente y monótono**: lo decide `Recordatorio.marcar_entrega`. Sin evento de bitácora por
callback (serían tres por mensaje); el paso a `FALLIDO` sí publica `recordatorio_fallido`, una vez.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.payments.application.ports import PortRepositorioRecordatorios
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos


class RegistrarEntregaDeRecordatorio:
    def __init__(
        self, *, recordatorios: PortRepositorioRecordatorios, publicador: PublicadorDeEventos
    ) -> None:
        self._recordatorios = recordatorios
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        externo_id: str,
        estado: EstadoEntrega,
        ahora: datetime,
        codigo_de_error: str | None = None,
    ) -> bool:
        """Devuelve si el `wamid` es de un recordatorio de esta empresa (no si cambió algo)."""
        # Bloqueada: dos `failed` en paralelo publicarían `recordatorio_fallido` dos veces, y un
        # `delivered` retrasado podría pisar un `read`.
        recordatorio = await self._recordatorios.buscar_por_externo_id(
            externo_id, para_actualizar=True
        )
        if recordatorio is None:
            return False
        if not recordatorio.marcar_entrega(estado, motivo=codigo_de_error):
            return True
        await self._recordatorios.guardar(recordatorio)
        if estado is EstadoEntrega.FALLIDO:
            await self._publicador.publicar(
                EventoAuditable(
                    evento_id=uuid4(),
                    empresa_id=empresa_id,
                    ocurrido_en=ahora,
                    usuario_id=None,
                    modulo=Modulo.PAYMENTS,
                    accion="recordatorio_fallido",
                    entidad_afectada=f"Cobro:{recordatorio.cobro_id}",
                    resultado=Resultado.ERROR,
                )
            )
        return True


__all__ = ["RegistrarEntregaDeRecordatorio"]
