"""Los avisos de turno, guardados como mensaje del sistema en la conversación del cliente (U7, D-U7-4).

`scheduling` ve un `CanalDeAvisos` (su `Protocol` local) y `conversational` publica
`NotificarAlCliente`; ninguno importa al otro (R3). Esta raíz de composición es lo único que conoce a
los dos: traduce el envío (`EnvioParaAviso` → `EnvioDeAviso`) y el resultado
(`ResultadoDeNotificacion` → `ResultadoLocal`).

**D2 sin excepciones que traducir.** `NotificarAlCliente` nunca levanta por el canal: ya convierte los
errores tipados de Meta (`motivo_de_falla_de`) en el motivo del resultado, así que `scheduling` no
necesita un `CanalConFallasTraducidas` como el de `payments`: el motivo viaja como dato.

**El mensaje se escribe en un savepoint** (`sesion.begin_nested`) dentro de la transacción de la
operación del panel: si la base lo rechaza, el turno queda cancelado igual y el adaptador de
`scheduling` deja `aviso_de_turno_sin_registrar`. El envío a Meta, que ya ocurrió, no se repite. La
E/S a Meta sigue corriendo dentro de esa transacción (hallazgo G5 / ADR-0015): este cambio no la
agrava ni la resuelve para los avisos de turno.
"""

from __future__ import annotations

from uuid import UUID

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.conversational.application.notificaciones import (
    EnvioDeAviso,
    NotificarAlCliente,
    PlantillaDeAviso,
)
from cheatsheet.contexts.conversational.application.ports import PortMensajeria
from cheatsheet.contexts.conversational.infrastructure.ensamblado import Conversaciones
from cheatsheet.contexts.scheduling.infrastructure.avisos import (
    CanalDeAvisos,
    EnvioParaAviso,
    ResultadoLocal,
)
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId


class CanalDeAvisosViaConversacion:
    """`CanalDeAvisos` de `scheduling` sobre `NotificarAlCliente` de `conversational`."""

    def __init__(self, caso: NotificarAlCliente, *, empresa_id: EmpresaId, reloj: Reloj) -> None:
        self._caso = caso
        self._empresa_id = empresa_id
        self._reloj = reloj

    async def notificar(
        self, *, cliente_id: UUID, telefono: str, envio: EnvioParaAviso
    ) -> ResultadoLocal:
        plantilla = envio.plantilla
        resultado = await self._caso.ejecutar(
            empresa_id=self._empresa_id,
            cliente_id=cliente_id,
            telefono=telefono,
            envio=EnvioDeAviso(
                texto=envio.texto,
                plantilla=(
                    PlantillaDeAviso(
                        nombre=plantilla.nombre,
                        idioma=plantilla.idioma,
                        parametros=plantilla.parametros,
                    )
                    if plantilla is not None
                    else None
                ),
            ),
            ahora=self._reloj.ahora(),
        )
        return ResultadoLocal(
            enviado=resultado.enviado,
            falla=resultado.falla,
            sin_registrar=resultado.sin_registrar,
            causa=resultado.causa,
            transitoria=resultado.transitoria,
        )


def armar_canal_de_avisos(
    unidad: UnidadDeTrabajo, *, empresa_id: EmpresaId, canal: PortMensajeria
) -> CanalDeAvisos:
    """El aviso de esta empresa: sale por `canal` y queda en los repositorios de esta unidad."""
    piezas = Conversaciones.armar(unidad)
    return CanalDeAvisosViaConversacion(
        NotificarAlCliente(
            conversaciones=piezas.conversaciones,
            mensajes=piezas.mensajes,
            mensajeria=canal,
            aislar=unidad.sesion.begin_nested,
        ),
        empresa_id=empresa_id,
        reloj=unidad.reloj,
    )


__all__ = ["CanalDeAvisosViaConversacion", "armar_canal_de_avisos"]
