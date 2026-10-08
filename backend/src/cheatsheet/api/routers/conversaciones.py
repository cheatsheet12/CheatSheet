"""Superficie HTTP del canal conversacional (HU-E9-01, HU-E9-02).

`EmpresaMiddleware` ya puso la empresa, el usuario y el rol en `request.state`. El rol se pasa
al caso de uso en vez de comprobarlo acá, por lo que dicen los demás routers y probó PRU-09.

**El webhook de WhatsApp no está acá**: vive en `webhooks.py`, con el de MercadoPago, porque
entra sin sesión y el middleware lo tiene que dejar pasar.

Las rutas de las FAQ (HU-E9-04) viven en `respuestas_frecuentes.py` y se montan acá, bajo el
mismo prefijo `/faqs`.

Las plantillas de notificación (HU-E11-02) viven en `plantillas.py`.

**No hay `DELETE` en este módulo.** Una conversación es el registro de lo que se le dijo a un
cliente y un escalamiento cerrado es un caso atendido. (La única baja real del sistema, la de una
FAQ, está en `respuestas_frecuentes.py`.)
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, TypeVar
from uuid import UUID

from cheatsheet.api.conversacional import (
    armar_directorio,
    armar_interprete,
)
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mensajeria import armar_mensajeria
from cheatsheet.api.routers.respuestas_frecuentes import rutas_de_faqs
from cheatsheet.contexts.conversational.application.atencion import (
    CerrarEscalamiento,
    ListarConversaciones,
    ResponderComoOperador,
    TomarEscalamiento,
    VerConversacion,
    VistaDeConversacion,
)
from cheatsheet.contexts.conversational.domain.conversacion import Intencion, Mensaje
from cheatsheet.contexts.conversational.infrastructure.ensamblado import Conversaciones
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel

_T = TypeVar("_T")


# -- entradas -------------------------------------------------------------------------


class RespuestaEntrada(BaseModel):
    texto: str


class CierreEntrada(BaseModel):
    devolver_al_agente: bool
    #: HU-E9-01 RN-05: el operador puede corregir la clasificación antes de devolver.
    clasificacion: str | None = None


# -- salidas --------------------------------------------------------------------------


class MensajeSalida(BaseModel):
    id: UUID
    direccion: str
    tipo_contenido: str
    contenido: str
    momento: datetime
    intencion: str | None
    estado_entrega: str | None
    #: HU-E9-01 RN-04: lo que hace que la pantalla distinga al operador del agente.
    origen: str | None
    #: Por qué falló un saliente (U7): un código de Meta o una clase corta, nunca el texto del error.
    motivo_de_falla: str | None


class ConversacionSalida(BaseModel):
    id: UUID
    cliente_id: UUID
    estado: str
    ultimo_mensaje_en: datetime | None
    #: HU-E9-01 RN-01: se **deriva** del escalamiento abierto, no es un estado del hilo.
    esta_escalada: bool
    escalamiento_id: UUID | None
    motivo: str | None
    estado_escalamiento: str | None
    usuario_asignado_id: UUID | None


class DetalleDeConversacion(ConversacionSalida):
    mensajes: list[MensajeSalida]


class ListadoDeConversaciones(BaseModel):
    conversaciones: list[ConversacionSalida]


def _a_conversacion(vista: VistaDeConversacion) -> ConversacionSalida:
    escalamiento = vista.escalamiento
    return ConversacionSalida(
        id=vista.conversacion.id,
        cliente_id=vista.conversacion.cliente_id,
        estado=vista.conversacion.estado.value,
        ultimo_mensaje_en=vista.conversacion.ultimo_mensaje_en,
        esta_escalada=vista.esta_escalada,
        escalamiento_id=escalamiento.id if escalamiento else None,
        motivo=escalamiento.motivo if escalamiento else None,
        estado_escalamiento=escalamiento.estado.value if escalamiento else None,
        usuario_asignado_id=escalamiento.usuario_asignado_id if escalamiento else None,
    )


def _a_mensaje(mensaje: Mensaje) -> MensajeSalida:
    return MensajeSalida(
        id=mensaje.id,
        direccion=mensaje.direccion.value,
        tipo_contenido=mensaje.tipo_contenido.value,
        contenido=mensaje.contenido,
        momento=mensaje.momento,
        intencion=mensaje.intencion.value if mensaje.intencion else None,
        estado_entrega=mensaje.estado_entrega.value if mensaje.estado_entrega else None,
        origen=mensaje.origen.value if mensaje.origen else None,
        motivo_de_falla=mensaje.motivo_de_falla,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _clasificacion(texto: str | None) -> Intencion | None:
    """La corrección manual de HU-E9-01 RN-05, o `None` para que el agente reevalúe.

    Un valor desconocido se trata como `None` y no como un 422: significa «no me dijiste una
    clasificación válida», y la consecuencia correcta es que reevalúe el agente, que es lo que
    la regla pide por defecto.
    """
    if texto is None or texto not in Intencion.__members__:
        return None
    return Intencion[texto]


def _exigir(salida: _T | None) -> _T:
    if salida is None:  # pragma: no cover - la unidad de trabajo siempre entrega una vuelta
        raise RuntimeError("La unidad de trabajo no produjo una respuesta")
    return salida


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["conversational"])
    router.include_router(_rutas_de_conversaciones(recursos), prefix="/conversaciones")
    router.include_router(_rutas_de_escalamientos(recursos), prefix="/escalamientos")
    router.include_router(rutas_de_faqs(recursos), prefix="/faqs")
    return router


def _rutas_de_conversaciones(recursos: Recursos) -> APIRouter:
    """PAN-WA-01. Todos los roles leen; Administrador y Operador atienden."""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request, solo_escaladas: Annotated[bool, Query()] = False
    ) -> ListadoDeConversaciones:
        """La bandeja del operador. `solo_escaladas` es lo que la pantalla usa por defecto."""
        empresa_id, _, _ = _actor(request)
        salida: ListadoDeConversaciones | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            vistas = await ListarConversaciones(
                piezas.conversaciones, piezas.escalamientos
            ).ejecutar(solo_escaladas=solo_escaladas)
            salida = ListadoDeConversaciones(
                conversaciones=[_a_conversacion(una) for una in vistas]
            )
        return _exigir(salida)

    @router.get("/{conversacion_id}")
    async def ver(request: Request, conversacion_id: UUID) -> DetalleDeConversacion:
        """El hilo completo. **El contexto previo de HU-E8-05 RN-03.**"""
        empresa_id, _, _ = _actor(request)
        salida: DetalleDeConversacion | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            vista = await VerConversacion(
                piezas.conversaciones, piezas.mensajes, piezas.escalamientos
            ).ejecutar(conversacion_id)
            salida = DetalleDeConversacion(
                **_a_conversacion(vista).model_dump(),
                mensajes=[_a_mensaje(uno) for uno in vista.mensajes],
            )
        return _exigir(salida)

    @router.post("/{conversacion_id}/mensajes", status_code=status.HTTP_201_CREATED)
    async def responder(
        request: Request, conversacion_id: UUID, entrada: RespuestaEntrada
    ) -> MensajeSalida:
        """HU-E9-01, tercer criterio: sale por WhatsApp y se distingue del agente.

        Requiere el escalamiento tomado: sin eso, el agente sigue contestando el mismo hilo y
        el cliente tendría dos interlocutores.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: MensajeSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            mensaje = await ResponderComoOperador(
                conversaciones=piezas.conversaciones,
                mensajes=piezas.mensajes,
                escalamientos=piezas.escalamientos,
                directorio=armar_directorio(
                    unidad, recursos.settings, empresa_id=empresa_id, usuario_id=usuario_id
                ),
                mensajeria=await armar_mensajeria(unidad, recursos.settings, empresa_id=empresa_id),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                conversacion_id=conversacion_id,
                texto=entrada.texto,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_mensaje(mensaje)
        return _exigir(salida)

    return router


def _rutas_de_escalamientos(recursos: Recursos) -> APIRouter:
    """Las dos acciones de HU-E9-01 y HU-E9-02."""
    router = APIRouter()

    @router.post("/{escalamiento_id}/toma")
    async def tomar(request: Request, escalamiento_id: UUID) -> ConversacionSalida:
        """HU-E9-01 RN-02: a partir de acá el agente no contesta ese hilo."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: ConversacionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            escalamiento = await TomarEscalamiento(
                piezas.escalamientos, unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                escalamiento_id=escalamiento_id,
                ahora=unidad.reloj.ahora(),
            )
            vista = await VerConversacion(
                piezas.conversaciones, piezas.mensajes, piezas.escalamientos
            ).ejecutar(escalamiento.conversacion_id)
            salida = _a_conversacion(vista)
        return _exigir(salida)

    @router.post("/{escalamiento_id}/cierre")
    async def cerrar(
        request: Request, escalamiento_id: UUID, entrada: CierreEntrada
    ) -> ConversacionSalida:
        """HU-E9-02. Devolver al agente **reclasifica** el hilo (RN-05).

        Un escalamiento ya cerrado contesta 422 con la frase que la historia pide: hay que
        decir que un pedido nuevo genera uno nuevo, no sólo negar la operación.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: ConversacionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            escalamiento = await CerrarEscalamiento(
                conversaciones=piezas.conversaciones,
                mensajes=piezas.mensajes,
                escalamientos=piezas.escalamientos,
                interprete=armar_interprete(recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                escalamiento_id=escalamiento_id,
                devolver_al_agente=entrada.devolver_al_agente,
                clasificacion=_clasificacion(entrada.clasificacion),
                ahora=unidad.reloj.ahora(),
            )
            vista = await VerConversacion(
                piezas.conversaciones, piezas.mensajes, piezas.escalamientos
            ).ejecutar(escalamiento.conversacion_id)
            salida = _a_conversacion(vista)
        return _exigir(salida)

    return router
