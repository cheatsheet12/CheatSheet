"""Superficie HTTP del panel de auditoría, las notificaciones y el soporte (épico 10).

`EmpresaMiddleware` ya puso la empresa, el usuario y el rol en `request.state`. El rol se pasa
al caso de uso en vez de comprobarlo acá, por lo que dicen los demás routers y probó PRU-09.

**Tres superficies con tres audiencias distintas, y conviene decirlo en voz alta:**

- **La bitácora es de Administrador y Operador** (HU-E12-01 RN-05). Solo Lectura no entra, y el
  motivo lo escribe la épica: ese rol puede ser un actor externo, y la bitácora expone el
  registro crudo de todo —incluidos datos de clientes y mensajes de terceros—.
- **El centro de notificaciones lo lee cualquiera, y sólo el suyo.** No hay ruta que devuelva
  la bandeja de otra persona: el destinatario sale de la sesión, nunca de la URL.
- **Soporte lo abre el Administrador** (HU-E9-03), y el listado es de la empresa.

**No hay `DELETE` en ninguna de las tres.** Un registro de auditoría es inmutable (RN-04), una
notificación se marca leída y una solicitud la cierra el equipo de CheatSheet.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, TypeVar
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.observability.application.consultas import (
    ContarOperaciones,
    ListarOperaciones,
    VerOperacion,
)
from cheatsheet.contexts.observability.application.notificaciones import (
    ContarNoLeidas,
    ListarNotificaciones,
    MarcarComoLeida,
)
from cheatsheet.contexts.observability.application.ports import FiltrosDeBitacora
from cheatsheet.contexts.observability.application.soporte import (
    AbrirSolicitudDeSoporte,
    ListarSolicitudes,
)
from cheatsheet.contexts.observability.domain.notificacion import Notificacion
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.contexts.observability.domain.solicitud_de_soporte import (
    PrioridadDeSoporte,
    SolicitudDeSoporte,
)
from cheatsheet.contexts.observability.infrastructure.ensamblado import Observabilidad
from cheatsheet.shared.auditoria import Iniciador, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel

_T = TypeVar("_T")
_E = TypeVar("_E", bound=StrEnum)

#: Cuántas filas trae una página de la bitácora. La tabla de PAN-LOG-01 muestra veinticinco y
#: pagina; pedir mil para mostrar veinticinco es tráfico que nadie mira.
TAMANO_DE_PAGINA = 25


# -- entradas -------------------------------------------------------------------------


class SolicitudEntrada(BaseModel):
    asunto: str
    descripcion: str
    prioridad: str = "MEDIA"


# -- salidas --------------------------------------------------------------------------


class OperacionSalida(BaseModel):
    """Una fila de PAN-LOG-01 (HU-E12-01 RN-01)."""

    id: UUID
    timestamp: datetime
    modulo: str
    accion: str
    entidad_afectada: str
    #: RN-02: distingue si la ejecutó la IA, una persona o el sistema.
    iniciador: str
    resultado: str
    #: `None` cuando actuó el sistema. La pantalla muestra el iniciador, no un id vacío.
    usuario_id: UUID | None


class ListadoDeOperaciones(BaseModel):
    operaciones: list[OperacionSalida]
    #: El total del filtro, para el paginador. Se cuenta en la base y no contando filas.
    total: int


class DetalleSalida(BaseModel):
    """PAN-LOG-02 (HU-E12-02 RN-01 y RN-03)."""

    operacion: OperacionSalida
    #: Lo que la operación registró de sí misma. Vacío en casi todas, y la pantalla lo dice.
    detalle: dict[str, str]
    timeline: list[OperacionSalida]
    #: Milisegundos entre el primer paso y el último. `None` si dejó una sola fila: una
    #: operación instantánea no tiene duración medida, y «0 ms» sería afirmar lo que nadie midió.
    duracion_ms: int | None
    #: El primer paso que falló, que es lo que el tercer criterio pide señalar.
    paso_con_error: UUID | None


class NotificacionSalida(BaseModel):
    id: UUID
    categoria: str
    severidad: str
    cuerpo: str
    leida: bool
    #: RN-04: la pantalla destaca lo que esto marca. Alta **y sin leer**.
    se_destaca: bool
    created_at: datetime | None


class ListadoDeNotificaciones(BaseModel):
    notificaciones: list[NotificacionSalida]
    no_leidas: int


class SolicitudSalida(BaseModel):
    id: UUID
    asunto: str
    descripcion: str
    prioridad: str
    estado: str
    esta_abierta: bool
    created_at: datetime | None


class ListadoDeSolicitudes(BaseModel):
    solicitudes: list[SolicitudSalida]


def _a_operacion(registro: RegistroDeAuditoria) -> OperacionSalida:
    return OperacionSalida(
        id=registro.id,
        timestamp=registro.timestamp,
        modulo=registro.modulo.value,
        accion=registro.accion,
        entidad_afectada=registro.entidad_afectada,
        iniciador=registro.iniciador.value,
        resultado=registro.resultado.value,
        usuario_id=registro.usuario_id,
    )


def _a_notificacion(notificacion: Notificacion) -> NotificacionSalida:
    return NotificacionSalida(
        id=notificacion.id,
        categoria=notificacion.categoria,
        severidad=notificacion.severidad.value,
        cuerpo=notificacion.cuerpo,
        leida=notificacion.leida,
        se_destaca=notificacion.se_destaca,
        created_at=notificacion.created_at,
    )


def _a_solicitud(solicitud: SolicitudDeSoporte) -> SolicitudSalida:
    return SolicitudSalida(
        id=solicitud.id,
        asunto=solicitud.asunto,
        descripcion=solicitud.descripcion,
        prioridad=solicitud.prioridad.value,
        estado=solicitud.estado.value,
        esta_abierta=solicitud.esta_abierta,
        created_at=solicitud.created_at,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _miembros_de(catalogo: type[_E], valores: list[str] | None, etiqueta: str) -> tuple[_E, ...]:
    """Traduce una lista de textos al enum que corresponde, o rechaza el primero que no exista.

    **Se filtra por el mismo texto que el listado devuelve**, que es el valor del enum
    (`"identity"`, `"ia"`, `"error"`) y no el nombre del miembro. Un filtro que hay que
    escribir distinto de como se lee es un filtro que el frontend tiene que traducir, y esa
    traducción es donde una mayúscula de más devuelve la lista entera.

    Rechazar en vez de ignorar, por lo mismo: un filtro mal escrito que devuelve *todo* le hace
    creer al usuario que filtró.
    """
    if not valores:
        return ()
    miembros = []
    for valor in valores:
        try:
            miembros.append(catalogo(valor))
        except ValueError as error:
            raise EntradaInvalida(f"«{valor}» no es un {etiqueta} valido") from error
    return tuple(miembros)


def _exigir(salida: _T | None) -> _T:
    if salida is None:  # pragma: no cover - la unidad de trabajo siempre entrega una vuelta
        raise RuntimeError("La unidad de trabajo no produjo una respuesta")
    return salida


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["observability"])
    router.include_router(_rutas_de_bitacora(recursos), prefix="/bitacora")
    router.include_router(_rutas_de_notificaciones(recursos), prefix="/notificaciones")
    router.include_router(_rutas_de_soporte(recursos), prefix="/soporte")
    return router


def _rutas_de_bitacora(recursos: Recursos) -> APIRouter:
    """PAN-LOG-01 y PAN-LOG-02. **Administrador y Operador**; Solo Lectura no entra."""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request,
        desde: Annotated[datetime | None, Query()] = None,
        hasta: Annotated[datetime | None, Query()] = None,
        modulo: Annotated[list[str] | None, Query()] = None,
        resultado: Annotated[list[str] | None, Query()] = None,
        iniciador: Annotated[list[str] | None, Query()] = None,
        texto: Annotated[str | None, Query()] = None,
        #: #176: los clientes cuyo nombre coincide con la búsqueda, resueltos por la pantalla.
        cliente_id: Annotated[list[UUID] | None, Query()] = None,
        pagina: Annotated[int, Query(ge=1)] = 1,
    ) -> ListadoDeOperaciones:
        empresa_id, _, rol = _actor(request)
        filtros = FiltrosDeBitacora(
            desde=desde,
            hasta=hasta,
            modulos=_miembros_de(Modulo, modulo, "modulo"),
            resultados=_miembros_de(Resultado, resultado, "resultado"),
            iniciadores=_miembros_de(Iniciador, iniciador, "iniciador"),
            texto=texto,
            clientes=tuple(cliente_id or ()),
            limite=TAMANO_DE_PAGINA,
            desplazamiento=(pagina - 1) * TAMANO_DE_PAGINA,
        )
        salida: ListadoDeOperaciones | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Observabilidad.armar(unidad)
            encontradas = await ListarOperaciones(piezas.registros).ejecutar(filtros, rol=rol)
            total = await ContarOperaciones(piezas.registros).ejecutar(filtros)
            salida = ListadoDeOperaciones(
                operaciones=[_a_operacion(una) for una in encontradas], total=total
            )
        return _exigir(salida)

    @router.get("/{registro_id}")
    async def ver(request: Request, registro_id: UUID) -> DetalleSalida:
        empresa_id, _, rol = _actor(request)
        salida: DetalleSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Observabilidad.armar(unidad)
            detalle = await VerOperacion(piezas.registros).ejecutar(registro_id, rol=rol)
            con_error = detalle.paso_con_error
            salida = DetalleSalida(
                operacion=_a_operacion(detalle.registro),
                detalle=dict(detalle.registro.detalle or {}),
                timeline=[_a_operacion(uno) for uno in detalle.timeline],
                duracion_ms=(
                    int(detalle.duracion.total_seconds() * 1000)
                    if detalle.duracion is not None
                    else None
                ),
                paso_con_error=con_error.id if con_error is not None else None,
            )
        return _exigir(salida)

    return router


def _rutas_de_notificaciones(recursos: Recursos) -> APIRouter:
    """PAN-CFG-NOT. **La bandeja de quien pide, y sólo la suya.**"""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request, solo_no_leidas: Annotated[bool, Query()] = False
    ) -> ListadoDeNotificaciones:
        empresa_id, usuario_id, _ = _actor(request)
        salida: ListadoDeNotificaciones | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Observabilidad.armar(unidad)
            encontradas = await ListarNotificaciones(piezas.notificaciones).ejecutar(
                destinatario_id=usuario_id, solo_no_leidas=solo_no_leidas
            )
            salida = ListadoDeNotificaciones(
                notificaciones=[_a_notificacion(una) for una in encontradas],
                no_leidas=await ContarNoLeidas(piezas.notificaciones).ejecutar(usuario_id),
            )
        return _exigir(salida)

    @router.post("/{notificacion_id}/lectura")
    async def marcar_leida(request: Request, notificacion_id: UUID) -> NotificacionSalida:
        """HU-E11-03 RN-03. `POST` sobre un sub-recurso y no `PATCH` sobre la notificación:
        lo que se crea es el acuse de lectura, y no hay forma de deshacerlo."""
        empresa_id, usuario_id, _ = _actor(request)
        salida: NotificacionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Observabilidad.armar(unidad)
            notificacion = await MarcarComoLeida(piezas.notificaciones).ejecutar(
                notificacion_id=notificacion_id, destinatario_id=usuario_id
            )
            salida = _a_notificacion(notificacion)
        return _exigir(salida)

    return router


def _rutas_de_soporte(recursos: Recursos) -> APIRouter:
    """PAN-SOP-01 (HU-E9-03). El alta y la consulta; el estado lo mueve CheatSheet."""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request, solo_abiertas: Annotated[bool, Query()] = False
    ) -> ListadoDeSolicitudes:
        empresa_id, _, _ = _actor(request)
        salida: ListadoDeSolicitudes | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Observabilidad.armar(unidad)
            encontradas = await ListarSolicitudes(piezas.solicitudes).ejecutar(
                solo_abiertas=solo_abiertas
            )
            salida = ListadoDeSolicitudes(solicitudes=[_a_solicitud(una) for una in encontradas])
        return _exigir(salida)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def abrir(request: Request, entrada: SolicitudEntrada) -> SolicitudSalida:
        empresa_id, usuario_id, rol = _actor(request)
        if entrada.prioridad not in PrioridadDeSoporte.__members__:
            raise EntradaInvalida(f"«{entrada.prioridad}» no es una prioridad valida")
        salida: SolicitudSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Observabilidad.armar(unidad)
            solicitud = await AbrirSolicitudDeSoporte(
                solicitudes=piezas.solicitudes, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                asunto=entrada.asunto,
                descripcion=entrada.descripcion,
                prioridad=PrioridadDeSoporte[entrada.prioridad],
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_solicitud(solicitud)
        return _exigir(salida)

    return router


__all__ = ["TAMANO_DE_PAGINA", "crear_router"]
