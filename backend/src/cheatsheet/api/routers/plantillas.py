"""Superficie HTTP de las plantillas de notificación (HU-E11-02, U6): PAN-CFG-NOT.

Todos los roles leen y sólo el Administrador edita o reenvía. **No hay alta ni baja**: los códigos
los define el sistema, y `ListarPlantillas` siembra las que falten la primera vez que alguien entra.

Editar una plantilla de WhatsApp la **manda a Meta antes de guardarla**: si Meta la refuta, la
respuesta es un 422 con el texto de Meta y no se guardó nada; si no contesta, un 503 («reintentá»)
y tampoco. Vivía en `conversaciones.py` y se mudó acá para no pasar el tope de 400 líneas con los
campos y la ruta que trae esta unidad.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypeVar
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mensajeria import armar_revision_de_meta
from cheatsheet.contexts.business_config.application.errors import MetaNoDisponible
from cheatsheet.contexts.business_config.application.plantillas import (
    ListarPlantillas,
    variables_conocidas,
)
from cheatsheet.contexts.business_config.application.revision_de_meta import (
    EditarPlantilla,
    EnviarPlantillaAMeta,
)
from cheatsheet.contexts.business_config.domain.plantilla import PlantillaDeNotificacion
from cheatsheet.contexts.business_config.infrastructure.ensamblado import ConfiguracionDeNegocio
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = obtener_logger(__name__)

_T = TypeVar("_T")


class PlantillaEntrada(BaseModel):
    cuerpo: str


class PlantillaSalida(BaseModel):
    id: UUID
    codigo: str
    canal: str
    idioma: str
    cuerpo: str
    #: `NO_APLICA`, `SIN_ENVIAR`, `PENDIENTE`, `APROBADA`, `RECHAZADA`, `PAUSADA` o `DESHABILITADA`.
    estado_aprobacion: str
    #: Las variables que admite, para que la pantalla las ofrezca en vez de que alguien las
    #: adivine y se coma el 422 del tercer criterio.
    variables: list[str]
    puede_usarse: bool
    #: Lo que Meta dijo: el código del motivo de un rechazo, su texto y la categoría que le asignó.
    motivo_meta: str | None
    detalle_meta: str | None
    categoria_en_meta: str | None
    #: Cuándo se puede volver a editar una aprobada (Meta lo permite una vez cada 24 h).
    editable_desde: datetime | None


class ListadoDePlantillas(BaseModel):
    plantillas: list[PlantillaSalida]


def _a_plantilla(plantilla: PlantillaDeNotificacion) -> PlantillaSalida:
    return PlantillaSalida(
        id=plantilla.id,
        codigo=plantilla.codigo,
        canal=plantilla.canal.value,
        idioma=plantilla.idioma,
        cuerpo=plantilla.cuerpo,
        estado_aprobacion=plantilla.estado_aprobacion.value,
        variables=sorted(variables_conocidas(plantilla.codigo)),
        puede_usarse=plantilla.puede_usarse,
        motivo_meta=plantilla.motivo_meta,
        detalle_meta=plantilla.detalle_meta,
        categoria_en_meta=plantilla.categoria_en_meta,
        editable_desde=plantilla.editable_desde,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def manejar_meta_no_disponible(_: Request, exc: Exception) -> JSONResponse:
    """503 con un texto fijo: Meta no contestó y no se guardó nada, así que se puede reintentar.

    Registrado en `main.py`, más específico que el manejador genérico de errores de dominio.
    """
    incierto = isinstance(exc, MetaNoDisponible) and exc.incierto
    logger.warning("meta_no_disponible_al_editar_plantilla", incierto=incierto)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "MetaNoDisponible",
            "detalle": "Meta no respondió. No se guardó nada: volvé a intentarlo en un rato.",
        },
    )


def crear_router(recursos: Recursos) -> APIRouter:
    """PAN-CFG-NOT. Todos leen; sólo el Administrador edita y reenvía."""
    router = APIRouter(prefix="/plantillas", tags=["conversational"])

    @router.get("")
    async def listar(request: Request) -> ListadoDePlantillas:
        empresa_id, _, _ = _actor(request)
        salida: ListadoDePlantillas | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = ConfiguracionDeNegocio.armar(unidad)
            plantillas = await ListarPlantillas(piezas.plantillas).ejecutar(
                empresa_id=empresa_id, ahora=unidad.reloj.ahora()
            )
            salida = ListadoDePlantillas(plantillas=[_a_plantilla(una) for una in plantillas])
        return _exigir(salida)

    @router.put("/{plantilla_id}")
    async def editar(
        request: Request, plantilla_id: UUID, entrada: PlantillaEntrada
    ) -> PlantillaSalida:
        """Segundo y tercer criterio: guarda con variables válidas, rechaza con la frase.

        Si es de WhatsApp, Meta la revisa primero: un 422 trae su texto, un 503 pide reintentar.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: PlantillaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = ConfiguracionDeNegocio.armar(unidad)
            revision = await armar_revision_de_meta(
                unidad, recursos.settings, empresa_id=empresa_id
            )
            plantilla = await EditarPlantilla(
                piezas.plantillas, unidad.publicador, revision
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                plantilla_id=plantilla_id,
                cuerpo=entrada.cuerpo,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_plantilla(plantilla)
        return _exigir(salida)

    @router.post("/{plantilla_id}/envio")
    async def enviar_a_revision(request: Request, plantilla_id: UUID) -> PlantillaSalida:
        """«Enviar a revisión»: reenvía una `SIN_ENVIAR` o `RECHAZADA` sin tocar el texto."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: PlantillaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = ConfiguracionDeNegocio.armar(unidad)
            revision = await armar_revision_de_meta(
                unidad, recursos.settings, empresa_id=empresa_id
            )
            plantilla = await EnviarPlantillaAMeta(
                piezas.plantillas, unidad.publicador, revision
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                plantilla_id=plantilla_id,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_plantilla(plantilla)
        return _exigir(salida)

    return router


def _exigir(salida: _T | None) -> _T:
    if salida is None:  # pragma: no cover - la unidad de trabajo siempre entrega una vuelta
        raise RuntimeError("La unidad de trabajo no produjo una respuesta")
    return salida
