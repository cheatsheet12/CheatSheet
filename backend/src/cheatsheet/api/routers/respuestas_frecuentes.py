"""Superficie HTTP de las respuestas frecuentes (HU-E9-04, PAN-WA-02).

Salió de `conversaciones.py`, que ya pasaba las 400 líneas de `CLAUDE.md` §5; el prefijo sigue
siendo `/faqs` y `conversaciones.crear_router` lo monta.

`EmpresaMiddleware` ya puso la empresa, el usuario y el rol en `request.state`. El rol se pasa al
caso de uso en vez de comprobarlo acá. Todos los roles leen; sólo el Administrador escribe.

**Los usos se cuentan por mes calendario en hora de Argentina** (ADR-0012): cada FAQ trae
`usos_este_mes`, `usos_mes_anterior` y `usos_total`, y el detalle (`GET /{faq_id}/uso`) trae su
participación antes y después de la última edición. Los porcentajes viajan como texto
(`"12.5"`), porque `Decimal` es la regla del sistema y un `float` redondea distinto.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

from cheatsheet.api.conversacional import armar_embeddings
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.conversational.application.faqs import (
    Comparacion,
    CrearFAQ,
    DetalleDeUso,
    EditarFAQ,
    EliminarFAQ,
    FAQConUsos,
    ListarFAQs,
    VerUsoDeFAQ,
)
from cheatsheet.contexts.conversational.domain.uso_de_faq import SIN_USOS, Participacion
from cheatsheet.contexts.conversational.infrastructure.ensamblado import Conversaciones
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

_T = TypeVar("_T")


class FAQEntrada(BaseModel):
    pregunta: str
    respuesta: str


class FAQSalida(BaseModel):
    id: UUID
    pregunta: str
    respuesta: str
    #: HU-E9-04 RN-02: «Este mes», «Mes anterior» y «Total», con los meses en hora de Argentina.
    usos_este_mes: int
    usos_mes_anterior: int
    usos_total: int
    #: La última vez que cambió el texto (no cuenta guardar lo mismo ni reindexar).
    editada_en: datetime | None
    #: `True` mientras el vector no se haya calculado: la FAQ existe y todavía no se encuentra
    #: por significado. La pantalla lo dice en vez de fingir que está lista.
    sin_indexar: bool


class ListadoDeFAQs(BaseModel):
    faqs: list[FAQSalida]


class ParticipacionSalida(BaseModel):
    usos: int
    #: Todas las respuestas con FAQ de la empresa en el lapso.
    total: int
    #: Porcentaje con un decimal (`"12.5"`); `None` si la empresa no respondió con ninguna FAQ.
    participacion: Decimal | None


class ComparacionSalida(BaseModel):
    dias: int
    antes: ParticipacionSalida
    despues: ParticipacionSalida


class DetalleDeUsoSalida(BaseModel):
    usos_este_mes: int
    usos_mes_anterior: int
    usos_total: int
    editada_en: datetime | None
    comparacion: ComparacionSalida | None
    #: `SIN_EDICIONES`, `EDICION_RECIENTE` o `SIN_HISTORIA_PREVIA` cuando no hay comparación.
    motivo_sin_comparacion: str | None


def _a_faq(vista: FAQConUsos) -> FAQSalida:
    faq = vista.faq
    return FAQSalida(
        id=faq.id,
        pregunta=faq.pregunta,
        respuesta=faq.respuesta,
        usos_este_mes=vista.conteo.este_mes,
        usos_mes_anterior=vista.conteo.mes_anterior,
        usos_total=vista.usos_total,
        editada_en=faq.editada_en,
        sin_indexar=faq.embedding_obsoleto,
    )


def _a_participacion(participacion: Participacion) -> ParticipacionSalida:
    return ParticipacionSalida(
        usos=participacion.usos, total=participacion.total, participacion=participacion.porcentaje
    )


def _a_comparacion(comparacion: Comparacion) -> ComparacionSalida:
    return ComparacionSalida(
        dias=comparacion.dias,
        antes=_a_participacion(comparacion.antes),
        despues=_a_participacion(comparacion.despues),
    )


def _a_detalle(detalle: DetalleDeUso) -> DetalleDeUsoSalida:
    return DetalleDeUsoSalida(
        usos_este_mes=detalle.conteo.este_mes,
        usos_mes_anterior=detalle.conteo.mes_anterior,
        usos_total=detalle.usos_total,
        editada_en=detalle.faq.editada_en,
        comparacion=_a_comparacion(detalle.comparacion) if detalle.comparacion else None,
        motivo_sin_comparacion=detalle.motivo.value if detalle.motivo else None,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _exigir(salida: _T | None) -> _T:
    if salida is None:  # pragma: no cover - la unidad de trabajo siempre entrega una vuelta
        raise RuntimeError("La unidad de trabajo no produjo una respuesta")
    return salida


def rutas_de_faqs(recursos: Recursos) -> APIRouter:
    """PAN-WA-02 (HU-E9-04). Todos leen; sólo el Administrador escribe."""
    router = APIRouter()
    _lecturas(router, recursos)
    _escrituras(router, recursos)
    return router


def _lecturas(router: APIRouter, recursos: Recursos) -> None:
    @router.get("")
    async def listar(request: Request) -> ListadoDeFAQs:
        empresa_id, _, _ = _actor(request)
        salida: ListadoDeFAQs | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            faqs = await ListarFAQs(piezas.faqs, piezas.usos).ejecutar(ahora=unidad.reloj.ahora())
            salida = ListadoDeFAQs(faqs=[_a_faq(una) for una in faqs])
        return _exigir(salida)

    @router.get("/{faq_id}/uso")
    async def ver_uso(request: Request, faq_id: UUID) -> DetalleDeUsoSalida:
        """El detalle de PAN-WA-02: los conteos y la participación antes y después de editar."""
        empresa_id, _, _ = _actor(request)
        salida: DetalleDeUsoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            detalle = await VerUsoDeFAQ(piezas.faqs, piezas.usos).ejecutar(
                faq_id=faq_id, ahora=unidad.reloj.ahora()
            )
            salida = _a_detalle(detalle)
        return _exigir(salida)


def _escrituras(router: APIRouter, recursos: Recursos) -> None:
    @router.post("", status_code=status.HTTP_201_CREATED)
    async def crear(request: Request, entrada: FAQEntrada) -> FAQSalida:
        """Primer criterio: aparece con contador en cero y disponible para el agente."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: FAQSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            faq = await CrearFAQ(piezas.faqs, armar_embeddings(), unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                pregunta=entrada.pregunta,
                respuesta=entrada.respuesta,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_faq(FAQConUsos(faq=faq, conteo=SIN_USOS))
        return _exigir(salida)

    @router.put("/{faq_id}")
    async def editar(request: Request, faq_id: UUID, entrada: FAQEntrada) -> FAQSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: FAQSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            faq = await EditarFAQ(
                piezas.faqs, armar_embeddings(), unidad.publicador, piezas.usos
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                faq_id=faq_id,
                pregunta=entrada.pregunta,
                respuesta=entrada.respuesta,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_faq(faq)
        return _exigir(salida)

    @router.delete(
        "/{faq_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        # `response_class=Response`, como el logout de `auth.py`: sin esto FastAPI le arma un
        # modelo de respuesta a un 204, que por definicion no tiene cuerpo, y falla al crear
        # la ruta — no al llamarla.
        response_class=Response,
    )
    async def eliminar(request: Request, faq_id: UUID) -> Response:
        """HU-E9-04 RN-03: el agente deja de usarla de inmediato.

        **El único borrado real del sistema.** Una FAQ no es un registro del negocio: no hay
        nada que auditar en una pregunta que ya no se hace.
        """
        empresa_id, usuario_id, rol = _actor(request)
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Conversaciones.armar(unidad)
            await EliminarFAQ(piezas.faqs, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                faq_id=faq_id,
                ahora=unidad.reloj.ahora(),
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
