"""El aviso de cobro confirmado, guardado como mensaje del sistema en la conversación (HU-E8-04 RN-01).

`payments` ve un `CanalDeAvisos` (su `Protocol` local) y `conversational` publica
`NotificarAlCliente`; ninguno importa al otro (R3). Esta raíz de composición es lo único que conoce a
los dos: traduce el envío (`EnvioParaAviso` → `EnvioDeAviso`) y el resultado
(`ResultadoDeNotificacion` → `ResultadoLocal`). Es el mismo patrón que `api/avisos_de_turno.py`, y con
esto la arista `conversational → payments` del Context Map cubre también este aviso (ADR-0011 §2).

**Corre después del commit del pago.** El webhook confirma el cobro en su unidad de trabajo; recién
entonces `avisar_pago_confirmado` abre **otra** (canal, repositorios de `conversational`, savepoint
del mensaje). Así el aviso es idempotente por construcción —solo el request que aprobó el cobro
llega acá— y un fallo del aviso no puede deshacer un pago ya guardado.

**Nunca levanta.** `NotificarAlCliente` ya convierte los errores del canal en el motivo del
resultado, y esta función atrapa el resto (credencial ilegible, base caída al guardar el mensaje):
el webhook contesta 200 igual, porque el pago está guardado. La llamada a Meta tiene timeout
(`ConfiguracionDeMensajeria`), el aviso entero tiene un plazo total
(`PLAZO_DEL_AVISO_EN_SEGUNDOS`) y no se reintenta (D6 de U7).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, UnidadDeTrabajo, unidad_de_trabajo
from cheatsheet.api.mensajeria import armar_mensajeria
from cheatsheet.api.mercadopago import armar_contactos
from cheatsheet.api.plantillas_salientes import armar_plantillas_aprobadas
from cheatsheet.contexts.conversational.application.notificaciones import (
    EnvioDeAviso,
    NotificarAlCliente,
    PlantillaDeAviso,
)
from cheatsheet.contexts.conversational.application.ports import PortMensajeria
from cheatsheet.contexts.conversational.infrastructure.ensamblado import Conversaciones
from cheatsheet.contexts.payments.application.avisos import AvisarPagoConfirmado
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.infrastructure.avisos import (
    AvisoDePagoPorWhatsApp,
    CanalDeAvisos,
    EnvioParaAviso,
    ResultadoLocal,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

#: Plazo total del aviso, en segundos, contado desde que arranca hasta que termina. El canal de
#: WhatsApp (`canal_http.py`) puede tardar ~33 s en el peor caso (3 intentos de 10 s más el
#: backoff) y MercadoPago deja de esperar la respuesta del webhook a los ~22 s: pasado eso lo da
#: por fallido y reintenta, y el reintento ya no avisa (`ya_procesado`). 8 s cubre de sobra un
#: envío sano a Meta (cientos de milisegundos), deja margen a la confirmación del pago que ya se
#: hizo y queda lejos de los 22 s. Si vence, el aviso se abandona sin reintento (D6 de U7): su
#: transacción se descarta, así que el mensaje puede no quedar en el hilo aunque Meta lo haya
#: enviado, y eso es preferible a un webhook que MercadoPago ya no está esperando.
PLAZO_DEL_AVISO_EN_SEGUNDOS = 8.0


class CanalDeAvisosViaConversacion:
    """`CanalDeAvisos` de `payments` sobre `NotificarAlCliente` de `conversational`."""

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
        )


def armar_canal_de_avisos_de_cobro(
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


def armar_aviso_de_pago(
    unidad: UnidadDeTrabajo, *, empresa_id: EmpresaId, canal: PortMensajeria
) -> AvisarPagoConfirmado:
    """El caso de uso del aviso, con el contacto, la plantilla y el canal de esta empresa."""
    return AvisarPagoConfirmado(
        contactos=armar_contactos(unidad),
        aviso=AvisoDePagoPorWhatsApp(
            armar_canal_de_avisos_de_cobro(unidad, empresa_id=empresa_id, canal=canal),
            armar_plantillas_aprobadas(unidad),
        ),
    )


async def avisar_pago_confirmado(
    recursos: Recursos, *, empresa_id: EmpresaId, cobro: Cobro
) -> None:
    """Avisa al cliente que su cobro quedó aprobado. **Nunca levanta.**

    Se llama después de que cerró la unidad de trabajo del pago y solo si el cobro se aprobó en
    ese request (`ResultadoDeConfirmacion.recien_aprobado`).
    """
    try:
        async with asyncio.timeout(PLAZO_DEL_AVISO_EN_SEGUNDOS):
            async for unidad in unidad_de_trabajo(recursos, empresa_id):
                canal = await armar_mensajeria(unidad, recursos.settings, empresa_id=empresa_id)
                await armar_aviso_de_pago(unidad, empresa_id=empresa_id, canal=canal).ejecutar(
                    cobro=cobro
                )
    except TimeoutError:
        # Ni teléfono, ni nombre, ni texto: solo qué cobro y cuánto se esperó.
        logger.warning(
            "aviso_de_pago_vencido",
            cobro_id=str(cobro.id),
            plazo_en_segundos=PLAZO_DEL_AVISO_EN_SEGUNDOS,
        )
    except Exception as exc:  # noqa: BLE001 — ver el docstring del módulo
        # El pago ya está confirmado: nada de acá puede hacer que MercadoPago reintente. Solo la
        # clase de la excepción, nunca su texto: puede traer el número.
        logger.warning("aviso_de_pago_fallido", cobro_id=str(cobro.id), causa=type(exc).__name__)


__all__ = [
    "PLAZO_DEL_AVISO_EN_SEGUNDOS",
    "CanalDeAvisosViaConversacion",
    "armar_aviso_de_pago",
    "armar_canal_de_avisos_de_cobro",
    "avisar_pago_confirmado",
]
