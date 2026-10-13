"""HTTP surface for documents (HU-E5-01, HU-E5-02, HU-E5-03).

`EmpresaMiddleware` has already put the company, the user and the role on `request.state`.
The role is passed down to the use case rather than checked here, for the reason the other
routers state and PRU-09 proved.

**There is no `DELETE` and no `PUT` on a document.** An issued document is a legal record;
it is reversed with a credit note, which is a different document and the next unit's work.
The only mutation here is creating one.

The listing and the detail are open to every role (HU-E5-01 RN-04); issuing is not, and the
guard for that lives in `EmitirComprobante`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, TypeVar
from uuid import UUID, uuid4

from cheatsheet.api.arca import armar_autorizacion
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.padron import armar_emisor, armar_receptor
from cheatsheet.contexts.billing.application.consultas import (
    ListarComprobantes,
    VerComprobante,
)
from cheatsheet.contexts.billing.application.emision import (
    EmitirComprobante,
    TiposDisponibles,
    ValidarReceptor,
    item,
)
from cheatsheet.contexts.billing.application.errors import (
    MENSAJE_NO_DESCARGABLE,
    ComprobanteNoDescargable,
)
from cheatsheet.contexts.billing.application.notas_de_credito import (
    EmitirNotaDeCredito,
    EstadoDeAnulacion,
)
from cheatsheet.contexts.billing.application.ports import (
    FiltrosDeComprobante,
    PortColaDeEmision,
)
from cheatsheet.contexts.billing.domain.comprobante import (
    AlicuotaIVA,
    Comprobante,
    EstadoComprobante,
    ItemDeComprobante,
    Receptor,
)
from cheatsheet.contexts.billing.domain.leyendas import leyenda_de
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.contexts.billing.infrastructure.ensamblado import (
    Facturacion,
    pdf_de_comprobantes,
)
from cheatsheet.contexts.billing.infrastructure.pdf import TIPO_DE_CONTENIDO
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.fiscal import CondicionIVA
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Query, Request, Response, status
from pydantic import BaseModel


class ItemEntrada(BaseModel):
    descripcion: str
    #: Text, not `float`. A JSON number would arrive as a Python float, which is the type
    #: `CLAUDE.md` §3.5 forbids anywhere near money — and it would be wrong in the fourth
    #: decimal, which is exactly where a centavo lives.
    cantidad: str
    precio_unitario: str
    alicuota_iva: str


class ComprobanteEntrada(BaseModel):
    cliente_id: UUID
    punto_de_venta_id: UUID
    tipo: str
    receptor_cuit: str
    receptor_domicilio: str | None = None
    items: list[ItemEntrada]
    turno_id: UUID | None = None


class ItemSalida(BaseModel):
    id: UUID
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    alicuota_iva: Decimal
    subtotal: Decimal
    iva: Decimal


class ComprobanteSalida(BaseModel):
    id: UUID
    tipo: str
    estado: str
    numero: int | None
    punto_de_venta_id: UUID
    cliente_id: UUID
    receptor_nombre: str
    receptor_cuit: str
    receptor_condicion_iva: str
    cae: str | None
    cae_vence_el: date | None
    motivo_de_rechazo: str | None
    #: HU-E5-03 RN-13: shown in the detail and printed on the PDF.
    leyenda: str | None
    subtotal: Decimal
    total_iva: Decimal
    total: Decimal
    saldo_pendiente: Decimal
    fecha_emision: datetime | None
    created_at: datetime
    #: HU-E5-02: the PDF is offered only for an authorised document.
    descargable: bool
    items: list[ItemSalida]


class ListadoSalida(BaseModel):
    comprobantes: list[ComprobanteSalida]


class NotaDeCreditoEntrada(BaseModel):
    """HU-E5-04. **No `tipo` and no receptor**: both come from the original (RN-02).

    Accepting them would let a caller choose which kind of document reverses which, and
    ARCA rejects the ones that do not match.
    """

    items: list[ItemEntrada]


class AnulacionSalida(BaseModel):
    """What PAN-FAC-04 preloads, and what the detail shows (RN-05)."""

    total_original: Decimal
    total_anulado: Decimal
    #: The ceiling for the next credit note (RN-03), against what is **left**.
    disponible: Decimal
    es_total: bool
    es_parcial: bool
    notas: list[ComprobanteSalida]


class ReceptorSalida(BaseModel):
    """What PAN-FAC-03 fills the form with once the CUIT checks out (RN-02)."""

    nombre: str
    cuit: str
    condicion_iva: str
    #: RN-01: only the types this pair of VAT conditions allows. The screen offers these
    #: and nothing else, which is what turns the story's error message into one nobody
    #: should ever see.
    tipos_disponibles: list[str]


def _a_item(item_dominio: ItemDeComprobante) -> ItemSalida:
    return ItemSalida(
        id=item_dominio.id,
        descripcion=item_dominio.descripcion,
        cantidad=item_dominio.cantidad,
        precio_unitario=item_dominio.precio_unitario,
        alicuota_iva=item_dominio.alicuota_iva.tasa,
        subtotal=item_dominio.subtotal,
        iva=item_dominio.iva,
    )


def _a_salida(comprobante: Comprobante) -> ComprobanteSalida:
    return ComprobanteSalida(
        id=comprobante.id,
        tipo=comprobante.tipo.value,
        estado=comprobante.estado.value,
        numero=comprobante.numero,
        punto_de_venta_id=comprobante.punto_de_venta_id,
        cliente_id=comprobante.cliente_id,
        receptor_nombre=comprobante.receptor.nombre,
        receptor_cuit=comprobante.receptor.cuit,
        receptor_condicion_iva=comprobante.receptor.condicion_iva.value,
        cae=comprobante.cae.codigo if comprobante.cae else None,
        cae_vence_el=comprobante.cae.vence_el if comprobante.cae else None,
        motivo_de_rechazo=comprobante.motivo_de_rechazo,
        leyenda=leyenda_de(comprobante),
        subtotal=comprobante.subtotal,
        total_iva=comprobante.total_iva,
        total=comprobante.total,
        saldo_pendiente=comprobante.saldo_pendiente,
        fecha_emision=comprobante.fecha_emision,
        created_at=comprobante.created_at,
        descargable=comprobante.es_descargable,
        items=[_a_item(uno) for uno in comprobante.items],
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _filtros(
    desde: date | None, hasta: date | None, tipo: str | None, estado: str | None
) -> FiltrosDeComprobante:
    """Build the filter object, ignoring values that are not part of the catalogues.

    An unknown `tipo` becomes "no filter" rather than a 422: the query string comes from a
    URL somebody may have edited or bookmarked, and the honest answer to a filter we do not
    understand is the unfiltered listing, not an error page.
    """
    tipos = (
        (TipoComprobante[tipo],) if tipo is not None and tipo in TipoComprobante.__members__ else ()
    )
    estados = (
        (EstadoComprobante[estado],)
        if estado is not None and estado in EstadoComprobante.__members__
        else ()
    )
    return FiltrosDeComprobante(desde=desde, hasta=hasta, tipos=tipos, estados=estados)


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["billing"])
    router.include_router(_rutas(recursos), prefix="/comprobantes")
    # The PDF is its own router, and the reason is the complexity ceiling of `CLAUDE.md`
    # §5: with it inside, `_rutas` scored 13 against a limit of 10. Splitting is what the
    # rule asks for -- «if it does not fit, the design is wrong» -- and it happens to be an
    # honest seam, because this is the one route that answers bytes instead of JSON.
    router.include_router(_rutas_de_pdf(recursos), prefix="/comprobantes")
    router.include_router(_rutas_de_anulacion(recursos), prefix="/comprobantes")
    return router


def _rutas_de_anulacion(recursos: Recursos) -> APIRouter:
    """HU-E5-04. Its own router for the same reason the PDF has one: the complexity ceiling.

    It is also an honest seam -- these two routes are the only ones that talk about an
    *original*, which is what makes a credit note different from any other document.
    """
    router = APIRouter()

    @router.get("/{comprobante_id}/anulacion")
    async def ver_anulacion(request: Request, comprobante_id: UUID) -> AnulacionSalida:
        """RN-05, and what PAN-FAC-04 preloads: the ceiling for the next credit note.

        Derived from the authorised credit notes every time (decision D19), never read off
        a column.
        """
        empresa_id, _, _ = _actor(request)
        salida: AnulacionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            estado = await EstadoDeAnulacion(piezas.comprobantes).ejecutar(comprobante_id)
            notas = await piezas.comprobantes.notas_de(comprobante_id)
            salida = AnulacionSalida(
                total_original=estado.total_original,
                total_anulado=estado.total_anulado,
                disponible=estado.disponible,
                es_total=estado.es_total,
                es_parcial=estado.es_parcial,
                notas=[_a_salida(nota) for nota in notas],
            )
        return _exigir_anulacion(salida)

    @router.post("/{comprobante_id}/notas-de-credito", status_code=status.HTTP_202_ACCEPTED)
    async def anular(
        request: Request, comprobante_id: UUID, entrada: NotaDeCreditoEntrada
    ) -> ComprobanteSalida:
        """202, like an issue: the note exists and ARCA has not answered yet (RN-04)."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: ComprobanteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            emitida = await EmitirNotaDeCredito(
                comprobantes=piezas.comprobantes,
                emitir=EmitirComprobante(
                    comprobantes=piezas.comprobantes,
                    puntos=piezas.puntos,
                    arca=armar_autorizacion(unidad, recursos.settings),
                    cola=_cola(recursos),
                    publicador=unidad.publicador,
                ),
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                origen_id=comprobante_id,
                items=[
                    item(
                        descripcion=linea.descripcion,
                        cantidad=linea.cantidad,
                        precio_unitario=linea.precio_unitario,
                        alicuota_iva=AlicuotaIVA(linea.alicuota_iva),
                    )
                    for linea in entrada.items
                ],
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_salida(emitida)
        return _exigir(salida)

    return router


def _exigir_anulacion(salida: AnulacionSalida | None) -> AnulacionSalida:
    if salida is None:  # pragma: no cover -- the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida


def _rutas_de_pdf(recursos: Recursos) -> APIRouter:
    router = APIRouter()

    @router.get("/{comprobante_id}/pdf")
    async def descargar_pdf(request: Request, comprobante_id: UUID) -> Response:
        """HU-E5-02 RN-03 — the printable representation.

        **Only for an authorised document.** A PDF of something ARCA rejected would be a
        piece of paper that looks exactly like an invoice and is not one, and somebody
        would hand it to a customer. `es_descargable` is the aggregate's own answer to
        that, so the rule lives in one place.

        Rendered on demand and cached in the object store, regenerated when the cache does
        not have it. Every role may download: it is a read like any other.
        """
        empresa_id, _, _ = _actor(request)
        contenido: bytes | None = None
        nombre = "comprobante.pdf"
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            comprobante = await VerComprobante(piezas.comprobantes).ejecutar(comprobante_id)
            if not comprobante.es_descargable:
                raise ComprobanteNoDescargable(MENSAJE_NO_DESCARGABLE)
            punto = await piezas.puntos.buscar_por_id(comprobante.punto_de_venta_id)
            numero = punto.numero if punto is not None else 0
            contenido = await pdf_de_comprobantes(recursos.settings).obtener(comprobante, numero)
            nombre = f"{numero:04d}-{comprobante.numero or 0:08d}.pdf"

        if contenido is None:  # pragma: no cover -- the unit of work always yields once
            raise RuntimeError("La unidad de trabajo no produjo un resultado")
        return Response(
            content=contenido,
            media_type=TIPO_DE_CONTENIDO,
            # `inline`, not `attachment`: the browser shows it, and whoever wants the file
            # saves it from there. Forcing a download on somebody who only wanted to check
            # a CAE leaves a folder full of PDFs nobody asked for.
            headers={"Content-Disposition": f'inline; filename="{nombre}"'},
        )

    return router


def _rutas(recursos: Recursos) -> APIRouter:
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request,
        # `Annotated` and not a `Query(...)` default, which B008 rejects: a call in a
        # default is evaluated once at import, and ruff is right that the shape is a trap
        # even where FastAPI makes it work.
        desde: Annotated[date | None, Query()] = None,
        hasta: Annotated[date | None, Query()] = None,
        tipo: Annotated[str | None, Query()] = None,
        estado: Annotated[str | None, Query()] = None,
    ) -> ListadoSalida:
        """PAN-FAC-01. Every role reads (RN-04)."""
        empresa_id, _, _ = _actor(request)
        salida = ListadoSalida(comprobantes=[])
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            comprobantes = await ListarComprobantes(piezas.comprobantes).ejecutar(
                _filtros(desde, hasta, tipo, estado)
            )
            salida = ListadoSalida(comprobantes=[_a_salida(uno) for uno in comprobantes])
        return salida

    @router.get("/receptores/{cuit}")
    async def validar_receptor(request: Request, cuit: str) -> ReceptorSalida:
        """PAN-FAC-03's first step (RN-02): the CUIT, then the types it allows."""
        empresa_id, _, _ = _actor(request)
        salida: ReceptorSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            receptor = await ValidarReceptor(armar_receptor(unidad, recursos.settings)).ejecutar(
                empresa_id=empresa_id, cuit=cuit
            )
            emisor = await armar_emisor(unidad, recursos.settings).condicion_iva(
                empresa_id=empresa_id
            )
            salida = ReceptorSalida(
                nombre=receptor.nombre,
                cuit=receptor.cuit,
                condicion_iva=receptor.condicion_iva.value,
                tipos_disponibles=[
                    tipo.value
                    for tipo in TiposDisponibles.ejecutar(
                        emisor=emisor, receptor=receptor.condicion_iva
                    )
                ],
            )
        return _exigir(salida)

    @router.get("/{comprobante_id}")
    async def ver(request: Request, comprobante_id: UUID) -> ComprobanteSalida:
        """PAN-FAC-02. Every role reads."""
        empresa_id, _, _ = _actor(request)
        salida: ComprobanteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            comprobante = await VerComprobante(piezas.comprobantes).ejecutar(comprobante_id)
            salida = _a_salida(comprobante)
        return _exigir(salida)

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def emitir(request: Request, entrada: ComprobanteEntrada) -> ComprobanteSalida:
        """HU-E5-03. **202, not 201**: the document exists but ARCA has not answered yet.

        RN-04 makes issuance asynchronous, and the status code says so. Answering 201 would
        tell the client the thing it asked for is done, when what is done is the request.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: ComprobanteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            receptor = await ValidarReceptor(armar_receptor(unidad, recursos.settings)).ejecutar(
                empresa_id=empresa_id, cuit=entrada.receptor_cuit
            )
            emisor = await armar_emisor(unidad, recursos.settings).condicion_iva(
                empresa_id=empresa_id
            )
            comprobante = _armar(entrada, receptor, emisor, request, unidad.reloj.ahora())
            emitido = await EmitirComprobante(
                comprobantes=piezas.comprobantes,
                puntos=piezas.puntos,
                arca=armar_autorizacion(unidad, recursos.settings),
                cola=_cola(recursos),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                comprobante=comprobante,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_salida(emitido)
        return _exigir(salida)

    return router


def _armar(
    entrada: ComprobanteEntrada,
    receptor: Receptor,
    emisor: CondicionIVA,
    request: Request,
    ahora: datetime,
) -> Comprobante:
    """Turn the request into an aggregate. **The receptor is the padrón's, not the form's.**

    The client sends a CUIT and nothing else about the receptor: the name and the VAT
    condition come from ARCA's registry, which is the only source that decides which type of
    document is legal. Accepting them from the form would let a caller pick its own answer
    to RN-01.
    """
    comprobante = Comprobante(
        id=uuid4(),
        empresa_id=request.state.empresa_id,
        cliente_id=entrada.cliente_id,
        punto_de_venta_id=entrada.punto_de_venta_id,
        tipo=TipoComprobante(entrada.tipo),
        receptor=Receptor(
            nombre=receptor.nombre,
            cuit=receptor.cuit,
            condicion_iva=receptor.condicion_iva,
            domicilio=entrada.receptor_domicilio,
        ),
        emisor_condicion_iva=emisor,
        created_at=ahora,
        turno_id=entrada.turno_id,
    )
    for linea in entrada.items:
        comprobante.agregar_item(
            item(
                descripcion=linea.descripcion,
                cantidad=linea.cantidad,
                precio_unitario=linea.precio_unitario,
                alicuota_iva=AlicuotaIVA(linea.alicuota_iva),
            )
        )
    return comprobante


def _cola(recursos: Recursos) -> PortColaDeEmision:
    """Imported lazily so the API's import graph does not pull Celery in at startup."""
    from cheatsheet.workers.tasks_billing import ColaDeEmision

    return ColaDeEmision(recursos.settings)


_Salida = TypeVar("_Salida", ComprobanteSalida, ReceptorSalida)


def _exigir(salida: _Salida | None) -> _Salida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida
