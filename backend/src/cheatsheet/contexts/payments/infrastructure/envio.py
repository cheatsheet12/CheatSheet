"""Por donde sale un recordatorio de cobro (HS-T3 RN-02), y su doble.

WhatsApp es el canal que las historias nombran, y el que el epico 8 va a construir de verdad.
Hasta entonces **este adaptador es honesto sobre lo que hace**: registra el envio y devuelve
`ENVIADO`, sin fingir una entrega que nadie confirmo.

Es deliberado y no una omision: un doble que devolviera `ENTREGADO` haria que el detalle de
PAN-COB-02 mostrara un estado de lectura inventado, y ese es exactamente el dato que alguien
mira antes de llamar por telefono a un cliente que «no contesta».
"""

from __future__ import annotations

from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)


class EnvioPorConsola:
    """El doble: deja el recordatorio en el log y devuelve `ENVIADO`.

    **Rechazado en produccion**, como los demas simulados. Una empresa cuyos recordatorios
    salen a un log es una empresa que cree que esta cobrando y no esta haciendo nada.

    No registra el nombre del cliente ni su telefono: son datos personales, y `CLAUDE.md` §5
    prohibe que aparezcan en un log aunque el log sea de desarrollo.
    """

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El envio por consola no puede usarse en produccion: los recordatorios "
                "quedarian en un log y nadie los recibiria"
            )
        self.enviados: list[tuple[str, int]] = []

    async def enviar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> EstadoEntrega:
        del empresa_id
        self.enviados.append((str(cobro.id), paso))
        logger.info("recordatorio_simulado", cobro_id=str(cobro.id), paso=paso, canal=canal)
        # `ENVIADO` y no `ENTREGADO`: nadie confirmo nada. Ver el docstring del modulo.
        return EstadoEntrega.ENVIADO


__all__ = ["EnvioPorConsola"]
