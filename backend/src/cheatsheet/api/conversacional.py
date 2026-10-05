"""Donde `conversational` recibe todo lo que no es suyo.

La misma forma que `mercadopago.py` y `agenda.py`, y por la misma razón: acá se encuentran
contextos, y la infraestructura de uno no puede meter mano en la de otro (R3).

Seis piezas se arman acá, y son seis porque este contexto es el que habla con más gente:

- **El intérprete**, real o simulado según el `LLM_ADAPTADOR` de siempre.
- **La mensajería de WhatsApp**, cuyo token y `phone_number_id` administra `integrations`
  desde el épico 2. Es lo que los épicos 6 y 7 dejaron pendiente.
- **El transcriptor** de notas de voz (HS-T7).
- **Los embeddings**, hoy sólo el doble determinista — ver `canal.py`.
- **La agenda**, que es el ACL contra `scheduling` y la puerta angosta de la decisión D38.
- **El directorio de clientes**, que sale de `master_data`.

Se construyen **por request**: el token puede tener que refrescarse, y refrescarlo persiste.
Es la misma conclusión de `arca.py` y `mercadopago.py`.
"""

from __future__ import annotations

from cheatsheet.api.agenda import armar_catalogo
from cheatsheet.api.agenda import armar_directorio as armar_directorio_de_avisos
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.api.padron import armar_padron_de_clientes
from cheatsheet.contexts.business_config.application.plantillas import ResolverPlantilla
from cheatsheet.contexts.business_config.infrastructure.ensamblado import (
    ConfiguracionDeNegocio,
)
from cheatsheet.contexts.conversational.application.ports import (
    PortAgenda,
    PortDirectorio,
    PortEmbeddings,
    PortInterprete,
    PortMensajeria,
    PortPlantillas,
    PortTranscriptor,
)
from cheatsheet.contexts.conversational.infrastructure.acl import (
    AgendaViaScheduling,
    DirectorioViaMasterData,
)
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    EmbeddingsSimulados,
    MensajeriaSimulada,
    MensajeriaWhatsApp,
    TranscriptorSimulado,
)
from cheatsheet.contexts.conversational.infrastructure.interprete import (
    ConfiguracionDelInterprete,
    InterpreteAnthropic,
    InterpreteSimulado,
)
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.contexts.master_data.infrastructure.repositories import (
    RepositorioClientePostgres,
)
from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso
from cheatsheet.contexts.scheduling.application.turnos import Avisador
from cheatsheet.contexts.scheduling.infrastructure.ensamblado import Agenda
from cheatsheet.platform.settings import AdaptadorDeModelo, AdaptadorDeWhatsApp, Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario

logger = obtener_logger(__name__)

#: La clave con la que `integrations` guarda el identificador del número de WhatsApp. Escrita
#: acá y no importada de su `mapeo.py`: ese módulo es infraestructura de otro contexto (R3), y
#: lo que cruza es el valor, no el archivo que lo nombra.
CLAVE_PHONE_NUMBER_ID = "phone_number_id"


def armar_interprete(settings: Settings) -> PortInterprete:
    """El modelo que clasifica. Simulado o real, según el adaptador configurado."""
    if settings.llm_adaptador is AdaptadorDeModelo.SIMULADO:
        return InterpreteSimulado(settings.entorno)
    return InterpreteAnthropic(
        ConfiguracionDelInterprete(
            api_key=settings.anthropic_api_key,
            modelo=settings.llm_modelo,
            timeout_segundos=settings.llm_timeout_segundos,
            max_tokens=settings.llm_max_tokens,
        )
    )


def armar_transcriptor(settings: Settings) -> PortTranscriptor:
    """HS-T7. Un solo adaptador por ahora — ver los pendientes del épico."""
    return TranscriptorSimulado(settings.entorno)


def armar_embeddings() -> PortEmbeddings:
    """Los vectores de las FAQ. Hoy sólo el doble determinista — ver `canal.py`."""
    return EmbeddingsSimulados()


async def armar_mensajeria(
    unidad: UnidadDeTrabajo, settings: Settings, *, empresa_id: EmpresaId
) -> PortMensajeria:
    """Por dónde sale un mensaje de WhatsApp.

    El token y el `phone_number_id` salen de `integrations`, donde el OAuth y el refresco ya
    existen desde el épico 2. **Sin integración conectada se devuelve el simulado**, y eso es
    deliberado: una empresa que todavía no conectó WhatsApp no tiene que ver un 500 cuando
    alguien cancela un turno — tiene que ver el turno cancelado y ningún mensaje enviado, que
    es exactamente lo que pasa.
    """
    if settings.whatsapp_adaptador is AdaptadorDeWhatsApp.SIMULADO:
        return MensajeriaSimulada(settings.entorno)

    piezas = Integraciones.armar(unidad.sesion, settings)
    configuracion = await piezas.integraciones.buscar(empresa_id, SistemaExterno.WHATSAPP)
    if configuracion is None:
        logger.info("whatsapp_sin_conectar")
        return MensajeriaSimulada(settings.entorno)

    token = piezas.cifrado.descifrar(configuracion.credencial).decode("utf-8")
    phone_number_id = str(configuracion.parametros.get(CLAVE_PHONE_NUMBER_ID, ""))
    if not phone_number_id:
        logger.warning("whatsapp_sin_phone_number_id")
        return MensajeriaSimulada(settings.entorno)

    return MensajeriaWhatsApp(
        ConfiguracionDeMensajeria(
            token=token,
            phone_number_id=phone_number_id,
            graph_url=settings.whatsapp_graph_url,
            graph_version=settings.whatsapp_graph_version,
            timeout_segundos=float(settings.whatsapp_timeout_segundos),
        )
    )


def armar_directorio(
    unidad: UnidadDeTrabajo,
    settings: Settings,
    *,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId | None,
) -> PortDirectorio:
    """Quién es el número que escribió, y cómo darlo de alta si no está.

    El padrón viaja porque `RegistrarCliente` lo pide: el alta desde el canal **no** manda
    CUIT, así que ARCA no se consulta — pero el caso de uso es el mismo, y darle un doble en
    lugar del real sería inventar una diferencia entre dos altas que son la misma.
    """
    return DirectorioViaMasterData(
        RepositorioClientePostgres(unidad.sesion),
        padron=armar_padron_de_clientes(unidad, settings),
        publicador=unidad.publicador,
        reloj=unidad.reloj,
        empresa_id=empresa_id,
        usuario_id=usuario_id,
    )


class _NotificadorSilencioso:
    """`PortNotificadorDeTurnos` que **no manda nada** (Pregunta 1 del Gate 1).

    `ReservarTurno` y `CancelarTurno` avisan siempre. Cuando el que reserva o cancela es el agente,
    el cliente **ya recibe la confirmación en la conversación**, con su estado de entrega: un
    segundo aviso igual, seguido, parece un error. El panel sigue avisando como siempre, porque
    arma su propio `Avisador`; esto sólo cambia el de las operaciones del agente. Vive acá, en el
    composition root, para no tocar `scheduling`.
    """

    async def avisar_reserva(self, datos: DatosDeAviso) -> None:
        del datos

    async def avisar_cancelacion(self, datos: DatosDeAviso) -> None:
        del datos

    async def avisar_reprogramacion(self, datos: DatosDeAviso) -> None:
        del datos


def armar_agenda(
    unidad: UnidadDeTrabajo,
    *,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId | None,
) -> PortAgenda:
    """**La puerta angosta de la decisión D38.**

    Del otro lado están los casos de uso deterministas del épico 7. El agente no reserva: le
    pide a esto que reserve, y esto le pide al motor.

    - **`aislar`** es `begin_nested`: cada reserva o cancelación corre en un savepoint, para que
      un rechazo del motor —que en PostgreSQL aborta la transacción— no se lleve puesto lo que el
      agente escribe después (T9).
    - **El avisador no envía** (Pregunta 1): el agente confirma en la conversación.
    """
    piezas = Agenda.armar(unidad)
    catalogo = armar_catalogo(unidad, empresa_id=empresa_id, rol=RolUsuario.OPERADOR)
    return AgendaViaScheduling(
        turnos=piezas.turnos,
        recursos=piezas.recursos,
        servicios=catalogo,
        avisador=Avisador(
            clientes=armar_directorio_de_avisos(unidad, empresa_id=empresa_id),
            servicios=catalogo,
            notificador=_NotificadorSilencioso(),
        ),
        publicador=unidad.publicador,
        reloj=unidad.reloj,
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        aislar=unidad.sesion.begin_nested,
    )


def armar_plantillas(unidad: UnidadDeTrabajo) -> PortPlantillas:
    """Los textos salientes configurables (HU-E11-02).

    Devuelve `None` por código no configurado, y el adaptador usa su texto de fábrica — ver
    `ResolverPlantilla`.
    """
    caso = ResolverPlantilla(ConfiguracionDeNegocio.armar(unidad).plantillas)
    return _PlantillasViaConfiguracion(caso)


class _PlantillasViaConfiguracion:
    """`PortPlantillas`, respaldado por el caso de uso publicado de `business_config`.

    Una clase de cinco líneas y no el caso de uso directo: la firma de `ResolverPlantilla`
    coincide con la del puerto por ahora, y hacer que `conversational` dependa de esa
    coincidencia sería atarle su contrato a los parámetros de otro contexto.
    """

    def __init__(self, caso: ResolverPlantilla) -> None:
        self._caso = caso

    async def resolver(self, codigo: str, variables: dict[str, str]) -> str | None:
        return await self._caso.ejecutar(codigo, variables)


__all__ = [
    "armar_agenda",
    "armar_directorio",
    "armar_embeddings",
    "armar_interprete",
    "armar_mensajeria",
    "armar_plantillas",
    "armar_transcriptor",
]
