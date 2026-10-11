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

**También arma la revisión de las plantillas** (`armar_revision_de_meta`, U6, ADR-0011 §4): el
cliente de `conversational` sobre la WABA de la empresa, envuelto en un adaptador que traduce sus
errores tipados a los de `business_config`. Va acá y no en ninguno de los dos contextos porque
traducir exige conocer las excepciones de los dos lados, y solo la raíz puede importar ambos sin una
arista nueva.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Protocol

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.business_config.application.errors import (
    MetaNoConectada,
    MetaNoDisponible,
    MetaRechazoLaPlantilla,
)
from cheatsheet.contexts.business_config.application.ports import (
    EstadoEnMeta,
    PortRevisionDeMeta,
    RespuestaDeMeta,
)
from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.application.ports import PortMensajeria
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaSimulada,
    MensajeriaWhatsApp,
    SinCanal,
)
from cheatsheet.contexts.conversational.infrastructure.canal_errores import (
    SUBCODIGOS_NOMBRE_EN_USO,
)
from cheatsheet.contexts.conversational.infrastructure.plantillas_meta import (
    PlantillaEnMeta,
    PlantillasDeMeta,
    PlantillasSimuladas,
    RespuestaDePlantilla,
    SinCuentaDeMeta,
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

#: Ídem para el identificador de la cuenta de WhatsApp Business (WABA), de la que cuelgan las
#: plantillas.
CLAVE_WABA_ID = "waba_id"


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


class _CredencialIlegible(Exception):
    """La credencial existe y no se pudo leer: ya quedó registrada, quien llama cae a «sin canal»."""


async def _credencial_de(
    unidad: UnidadDeTrabajo, settings: Settings, empresa_id: EmpresaId
) -> tuple[str, Mapping[str, Any]] | None:
    """El token en claro y los parámetros de la integración de WhatsApp, o `None` si no hay.

    Compartido por el canal de mensajes y la revisión de plantillas: las dos leen la misma
    integración y las dos tratan igual una credencial ilegible. Solo el id de la empresa y la clase
    del error van al log: el texto de la excepción podría arrastrar material de la credencial.
    """
    piezas = Integraciones.armar(unidad.sesion, settings)
    configuracion = await piezas.integraciones.buscar(empresa_id, SistemaExterno.WHATSAPP)
    if configuracion is None:
        return None
    try:
        token = piezas.cifrado.descifrar(configuracion.credencial).decode("utf-8")
    except (CredencialIlegible, UnicodeDecodeError) as exc:
        logger.warning(
            "whatsapp_credencial_ilegible", empresa_id=str(empresa_id), causa=type(exc).__name__
        )
        raise _CredencialIlegible from exc
    return token, configuracion.parametros


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

    try:
        credencial = await _credencial_de(unidad, settings, empresa_id)
    except _CredencialIlegible:
        # Una credencial corrupta, o cifrada con otra clave, no puede voltear una reserva ni
        # abortar el barrido de cobros de toda la empresa: cae a `SinCanal` (también fuera de
        # producción: el simulado daría por enviado lo que no salió) y quien llama
        # registra el mensaje `FALLIDO`.
        return SinCanal()
    if credencial is None:
        logger.info("whatsapp_sin_conectar")
        return _sin_conectar(settings)
    token, parametros = credencial
    phone_number_id = str(parametros.get(CLAVE_PHONE_NUMBER_ID, ""))
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


class _ClienteDePlantillas(Protocol):
    """Lo que la raíz usa del cliente de `conversational`: sus tres operaciones."""

    async def crear(
        self, *, nombre: str, idioma: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla: ...

    async def editar(
        self, *, meta_plantilla_id: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla: ...

    @property
    def estados_completos(self) -> bool: ...

    async def estados(self) -> list[PlantillaEnMeta]: ...


@contextmanager
def _traducir_errores() -> Iterator[None]:
    """Los errores tipados del canal, a los de `business_config` (y nada más)."""
    try:
        yield
    except MensajeRechazado as exc:
        raise MetaRechazoLaPlantilla(
            exc.mensaje_para_el_usuario or str(exc),
            nombre_en_uso=exc.subcodigo in SUBCODIGOS_NOMBRE_EN_USO,
        ) from exc
    except MensajeriaSaturada as exc:
        raise MetaNoDisponible("Meta no respondió", incierto=False) from exc
    except EnvioIncierto as exc:
        raise MetaNoDisponible("Meta no respondió a tiempo", incierto=True) from exc
    except CanalNoConectado as exc:
        raise MetaNoConectada(str(exc)) from exc


class _RevisionViaMeta:
    """`PortRevisionDeMeta` sobre el cliente de plantillas de `conversational` (ADR-0011 §4).

    **Vive en la raíz** porque traducir exige conocer las excepciones de los dos contextos:
    `MensajeRechazado` → `MetaRechazoLaPlantilla` (con el texto de Meta y si el nombre estaba en
    uso), `MensajeriaSaturada` → `MetaNoDisponible`, `EnvioIncierto` → `MetaNoDisponible(incierto)`
    y `CanalNoConectado` → `MetaNoConectada`.
    """

    def __init__(self, cliente: _ClienteDePlantillas) -> None:
        self._cliente = cliente

    async def crear(
        self, *, nombre: str, idioma: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDeMeta:
        with _traducir_errores():
            respuesta = await self._cliente.crear(
                nombre=nombre, idioma=idioma, cuerpo=cuerpo, ejemplos=ejemplos
            )
        return _a_respuesta(respuesta)

    async def editar(
        self, *, meta_plantilla_id: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDeMeta:
        with _traducir_errores():
            respuesta = await self._cliente.editar(
                meta_plantilla_id=meta_plantilla_id, cuerpo=cuerpo, ejemplos=ejemplos
            )
        return _a_respuesta(respuesta)

    @property
    def estados_completos(self) -> bool:
        return self._cliente.estados_completos

    async def estados(self) -> list[EstadoEnMeta]:
        with _traducir_errores():
            filas = await self._cliente.estados()
        return [
            EstadoEnMeta(
                meta_plantilla_id=una.meta_plantilla_id,
                nombre=una.nombre,
                idioma=una.idioma,
                estado=una.estado,
                categoria=una.categoria,
                motivo=una.motivo,
                cuerpo=una.cuerpo,
            )
            for una in filas
        ]


def _a_respuesta(respuesta: RespuestaDePlantilla) -> RespuestaDeMeta:
    return RespuestaDeMeta(
        meta_plantilla_id=respuesta.meta_plantilla_id,
        estado=respuesta.estado,
        categoria=respuesta.categoria,
    )


def _sin_cuenta_de_meta(settings: Settings) -> PortRevisionDeMeta:
    """Misma regla que `_sin_conectar`: en producción no hay a quién pedirle, fuera de ella aprueba."""
    if settings.entorno is Entorno.PRODUCTION:
        return _RevisionViaMeta(SinCuentaDeMeta())
    return _RevisionViaMeta(PlantillasSimuladas(settings.entorno))


async def armar_revision_de_meta(
    unidad: UnidadDeTrabajo, settings: Settings, *, empresa_id: EmpresaId
) -> PortRevisionDeMeta:
    """Las plantillas de esta empresa, sobre su WABA (U6).

    - `simulado`: aprueba todo, sin red y sin leer `integrations`.
    - Sin integración o sin `waba_id`: fuera de producción, el simulado; en producción,
      `SinCuentaDeMeta` (la plantilla queda `SIN_ENVIAR` con «WhatsApp no está conectado»).
    - Credencial ilegible: `SinCuentaDeMeta` **en todo entorno**, igual que el canal: aprobar
      plantillas sin poder hablar con Meta daría por hecho lo que no pasó.
    """
    if settings.whatsapp_adaptador is AdaptadorDeWhatsApp.SIMULADO:
        return _RevisionViaMeta(PlantillasSimuladas(settings.entorno))

    try:
        credencial = await _credencial_de(unidad, settings, empresa_id)
    except _CredencialIlegible:
        return _RevisionViaMeta(SinCuentaDeMeta())
    if credencial is None:
        logger.info("whatsapp_sin_conectar")
        return _sin_cuenta_de_meta(settings)
    token, parametros = credencial
    waba_id = str(parametros.get(CLAVE_WABA_ID, ""))
    if not waba_id:
        logger.warning("whatsapp_sin_waba_id")
        return _sin_cuenta_de_meta(settings)
    return _RevisionViaMeta(
        PlantillasDeMeta(
            token=token,
            waba_id=waba_id,
            graph_url=settings.whatsapp_graph_url,
            graph_version=settings.whatsapp_graph_version,
            timeout_segundos=float(settings.whatsapp_timeout_segundos),
        )
    )


__all__ = ["CLAVE_PHONE_NUMBER_ID", "CLAVE_WABA_ID", "armar_mensajeria", "armar_revision_de_meta"]
