"""El canal de WhatsApp de una empresa, armado una vez por unidad de trabajo (ADR-0011 §2).

Vive acá, y no en `conversacional.py`, para que `agenda.py`, `mercadopago.py` y `workers/`
puedan pedirlo sin depender de `conversacional.py` (que ya importa `agenda.py`). Es la única
pieza que ata `conversational` con `payments` y `scheduling`: el canal se arma acá y se **pasa
hacia adentro** a los adaptadores de los otros dos contextos, que lo reciben como un `Protocol`
local y nunca importan a `conversational`.

El token y el `phone_number_id` salen de `integrations` en cada unidad de trabajo (ADR-0003):
no se cachean: la integración es la fuente de verdad y cada unidad la lee de nuevo. Acá **nada
refresca el token**: uno vencido hace que Meta conteste con su código permanente 190, y el mensaje
queda `FALLIDO` sin reintento.
"""

from __future__ import annotations

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.conversational.application.ports import PortMensajeria
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaSimulada,
    MensajeriaWhatsApp,
    SinCanal,
)
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.cifrado import CredencialIlegible
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.platform.settings import AdaptadorDeWhatsApp, Entorno, Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

#: La clave con la que `integrations` guarda el identificador del número de WhatsApp. Escrita
#: acá y no importada de su `mapeo.py`: ese módulo es infraestructura de otro contexto (R3), y
#: lo que cruza es el valor, no el archivo que lo nombra.
CLAVE_PHONE_NUMBER_ID = "phone_number_id"


def _sin_conectar(settings: Settings) -> PortMensajeria:
    """Lo que se devuelve cuando la empresa no tiene WhatsApp conectado.

    **Producción: `SinCanal`**, que levanta `CanalNoConectado` sin tocar la red, para que quien
    llama registre el mensaje como *no enviado* (ADR-0011 §3). El simulado se niega a arrancar
    ahí, y tampoco serviría: daría por enviado lo que no salió. Fuera de producción sigue el
    simulado, que deja el mensaje en un log.
    """
    if settings.entorno is Entorno.PRODUCTION:
        return SinCanal()
    return MensajeriaSimulada(settings.entorno)


async def armar_mensajeria(
    unidad: UnidadDeTrabajo, settings: Settings, *, empresa_id: EmpresaId
) -> PortMensajeria:
    """Por dónde sale un mensaje de WhatsApp de esta empresa.

    El token y el `phone_number_id` salen de `integrations`, donde el OAuth y el refresco ya
    existen desde el épico 2. **Sin integración conectada no hay 500**: una empresa que todavía
    no conectó WhatsApp tiene que ver el turno cancelado y ningún mensaje enviado (ver
    `_sin_conectar`).
    """
    if settings.whatsapp_adaptador is AdaptadorDeWhatsApp.SIMULADO:
        return MensajeriaSimulada(settings.entorno)

    piezas = Integraciones.armar(unidad.sesion, settings)
    configuracion = await piezas.integraciones.buscar(empresa_id, SistemaExterno.WHATSAPP)
    if configuracion is None:
        logger.info("whatsapp_sin_conectar")
        return _sin_conectar(settings)

    try:
        token = piezas.cifrado.descifrar(configuracion.credencial).decode("utf-8")
    except (CredencialIlegible, UnicodeDecodeError) as exc:
        # Una credencial corrupta, o cifrada con otra clave, no puede voltear una reserva ni
        # abortar el barrido de cobros de toda la empresa: cae a `SinCanal` (también fuera de
        # producción: el simulado daría por enviado lo que no salió) y quien llama
        # registra el mensaje `FALLIDO`. Sólo el id de la empresa y la clase del error: el
        # texto de la excepción podría arrastrar material de la credencial.
        logger.warning(
            "whatsapp_credencial_ilegible", empresa_id=str(empresa_id), causa=type(exc).__name__
        )
        return SinCanal()
    phone_number_id = str(configuracion.parametros.get(CLAVE_PHONE_NUMBER_ID, ""))
    if not phone_number_id:
        logger.warning("whatsapp_sin_phone_number_id")
        return _sin_conectar(settings)

    return MensajeriaWhatsApp(
        ConfiguracionDeMensajeria(
            token=token,
            phone_number_id=phone_number_id,
            graph_url=settings.whatsapp_graph_url,
            graph_version=settings.whatsapp_graph_version,
            timeout_segundos=float(settings.whatsapp_timeout_segundos),
        )
    )


__all__ = ["CLAVE_PHONE_NUMBER_ID", "armar_mensajeria"]
