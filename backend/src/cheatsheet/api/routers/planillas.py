"""HTTP surface for spreadsheet links (HU-E2-04, PAN-ING-01).

`EmpresaMiddleware` has already verified the token and put the company, the user and the
role on `request.state`. The role is **passed down to the use case** rather than checked
here, for the reason the other routers state and PRU-09 proved: the endpoint is one caller
among several, and the rule belongs next to the operation it guards.

**The upload is a raw binary body with the file name in the query string**, not
`multipart/form-data` and not JSON. Three reasons, in order of weight: base64 inside JSON
inflates a 25 MB workbook to 33 MB of string that has to be decoded in memory before
anything can look at it; multipart costs a parsing dependency and a full re-buffer of the
body for a request that carries exactly one part; and the client here is our own BFF
rather than a browser form, so there is no form encoding to be compatible with.

The name travels as a query parameter rather than a header because Spanish file names
carry accents, and a header would need its own encoding rules to survive
`clientes año 2026.xlsx`.

**The OAuth `state` travels in a cookie, not in the session.** This process is replicated
and holds no session state; the cookie is `HttpOnly`, `SameSite=lax` and expires in ten
minutes, which is the same shape epic 2 used for the MercadoPago round trip.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    ArchivoDemasiadoGrande,
    PermisosDePlanillaInsuficientes,
)
from cheatsheet.contexts.spreadsheet_sync.application.vinculos import (
    ConfirmarVinculacionConGoogle,
    DesvincularPlanilla,
    IniciarVinculacionConGoogle,
    ListarVinculos,
    SubirPlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    LIMITE_TAMANO_BYTES,
    MENSAJE_ARCHIVO_DEMASIADO_GRANDE,
    DireccionSync,
    ProveedorPlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.ensamblado import (
    Planillas,
    almacenamiento,
    proveedor_de_planilla,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

#: The `state` cookie of the Google round trip. Ten minutes is long enough to pick a file
#: and short enough that a forgotten tab is not a standing invitation.
COOKIE_ESTADO = "planilla_oauth_state"
COOKIE_TTL_SEGUNDOS = 600


class AutorizacionSalida(BaseModel):
    url: str


class ConfirmacionEntrada(BaseModel):
    """What the panel sends back after the user returns from Google."""

    codigo: str
    identificador_documento: str
    estado: str
    direccion: DireccionSync = DireccionSync.SOLO_LECTURA


class VinculoSalida(BaseModel):
    id: UUID
    proveedor: ProveedorPlanilla
    direccion: DireccionSync
    hoja_empresa: str
    nombre_archivo: str | None = None
    tamano_bytes: int | None = None
    pausado: bool
    motivo_de_pausa: str | None = None
    escribe_de_vuelta: bool
    tiene_mapeo: bool
    ultima_lectura: datetime | None = None
    created_at: datetime


class ListadoDeVinculosSalida(BaseModel):
    vinculos: list[VinculoSalida]


def _a_salida(vinculo: VinculoDePlanilla) -> VinculoSalida:
    return VinculoSalida(
        id=vinculo.id,
        proveedor=vinculo.proveedor,
        direccion=vinculo.direccion,
        hoja_empresa=vinculo.hoja_empresa,
        nombre_archivo=vinculo.archivo.nombre_original if vinculo.archivo else None,
        tamano_bytes=vinculo.archivo.tamano_bytes if vinculo.archivo else None,
        pausado=vinculo.pausado,
        motivo_de_pausa=vinculo.motivo_de_pausa,
        escribe_de_vuelta=vinculo.escribe_de_vuelta,
        tiene_mapeo=vinculo.mapeo_vigente_id is not None,
        ultima_lectura=vinculo.ultima_lectura,
        created_at=vinculo.created_at,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def crear_router(recursos: Recursos) -> APIRouter:
    # Split in two for the same reason the clients router is: one function holding every
    # route crosses the complexity ceiling of CLAUDE.md §5, and the split that means
    # something here is by how a spreadsheet arrives -- the OAuth round trip is a
    # different shape of operation from an upload.
    router = APIRouter(tags=["spreadsheet_sync"])
    router.include_router(_rutas_de_google(recursos), prefix="/planillas")
    router.include_router(_rutas_de_vinculos(recursos), prefix="/planillas")
    return router


def _rutas_de_google(recursos: Recursos) -> APIRouter:
    """The OAuth2 round trip of RN-01: leave for Google, come back with a document."""
    router = APIRouter()

    async def listar(request: Request) -> ListadoDeVinculosSalida:
        """`Cargas recientes` of PAN-ING-01. Every role reads (HU-E3-05 RN-04)."""
        empresa_id, _, _ = _actor(request)
        salida = ListadoDeVinculosSalida(vinculos=[])
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            vinculos = await ListarVinculos(piezas.vinculos).ejecutar()
            salida = ListadoDeVinculosSalida(vinculos=[_a_salida(v) for v in vinculos])
        return salida

    @router.post("/google/autorizacion")
    async def autorizar(request: Request, respuesta: Response) -> AutorizacionSalida:
        """RN-01 — where the user goes to pick a file and grant read access to it."""
        _, _, rol = _actor(request)
        pendiente = IniciarVinculacionConGoogle(proveedor_de_planilla(recursos.settings)).ejecutar(
            rol=rol
        )

        respuesta.set_cookie(
            COOKIE_ESTADO,
            pendiente.estado,
            max_age=COOKIE_TTL_SEGUNDOS,
            httponly=True,
            samesite="lax",
            # Over TLS everywhere except a local run, like every other cookie this app
            # sets; `app_base_url` is what tells the two apart.
            secure=recursos.settings.app_base_url.startswith("https://"),
        )
        return AutorizacionSalida(url=pendiente.url)

    @router.post("/google", status_code=status.HTTP_201_CREATED)
    async def confirmar(
        request: Request,
        entrada: ConfirmacionEntrada,
        respuesta: Response,
    ) -> VinculoSalida:
        """The callback's landing point: exchange the code and store the link."""
        empresa_id, usuario_id, rol = _actor(request)

        esperado = request.cookies.get(COOKIE_ESTADO)
        if not esperado or esperado != entrada.estado:
            # Without this, anybody who can make the user's browser reach this endpoint
            # can attach a spreadsheet of their choosing to that user's company.
            raise PermisosDePlanillaInsuficientes(
                "La autorizacion no coincide con la que iniciaste. Volve a intentarlo."
            )
        respuesta.delete_cookie(COOKIE_ESTADO)

        salida: VinculoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            vinculo = await ConfirmarVinculacionConGoogle(
                vinculos=piezas.vinculos,
                proveedor=proveedor_de_planilla(recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                codigo=entrada.codigo,
                identificador_documento=entrada.identificador_documento,
                direccion=entrada.direccion,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_salida(vinculo)
        return _exigir(salida)

    return router


def _rutas_de_vinculos(recursos: Recursos) -> APIRouter:
    """Reading the links, uploading a workbook, and unlinking."""
    router = APIRouter()

    @router.get("")
    async def listar(request: Request) -> ListadoDeVinculosSalida:
        """`Cargas recientes` of PAN-ING-01. Every role reads (HU-E3-05 RN-04)."""
        empresa_id, _, _ = _actor(request)
        salida = ListadoDeVinculosSalida(vinculos=[])
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            vinculos = await ListarVinculos(piezas.vinculos).ejecutar()
            salida = ListadoDeVinculosSalida(vinculos=[_a_salida(v) for v in vinculos])
        return salida

    @router.post("/archivo", status_code=status.HTTP_201_CREATED)
    async def subir(request: Request, nombre: str) -> VinculoSalida:
        """HU-E3-03's drop zone. The size is checked before the bytes are stored.

        No `direccion` parameter: an uploaded workbook is a snapshot and is always
        `SOLO_LECTURA`. Accepting the field and ignoring it would invite a caller to
        believe it does something.
        """
        empresa_id, usuario_id, rol = _actor(request)

        contenido = await request.body()
        if len(contenido) > LIMITE_TAMANO_BYTES:
            # Checked here as well as in `ReferenciaDeArchivo`, because reaching the
            # aggregate means the whole body was already read into memory. This is the
            # cheap refusal; that one is the guarantee.
            raise ArchivoDemasiadoGrande(MENSAJE_ARCHIVO_DEMASIADO_GRANDE)

        salida: VinculoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            vinculo = await SubirPlanilla(
                vinculos=piezas.vinculos,
                almacenamiento=almacenamiento(recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                nombre_de_archivo=nombre,
                contenido=contenido,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_salida(vinculo)
        return _exigir(salida)

    @router.delete("/{vinculo_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    async def desvincular(request: Request, vinculo_id: UUID) -> None:
        """`response_model=None` is mandatory on a 204 here.

        Every module carries `from __future__ import annotations`, so FastAPI receives
        `-> None` as the string `"None"`, resolves it to `NoneType` — a class, therefore
        truthy — and asserts that a 204 cannot have a response model. It fails at import,
        which takes down the whole application rather than this endpoint. Recorded in
        `TODO.md` §10 when `categorias-y-clasificacion` hit it.
        """
        empresa_id, usuario_id, rol = _actor(request)
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            await DesvincularPlanilla(
                vinculos=piezas.vinculos,
                almacenamiento=almacenamiento(recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                vinculo_id=vinculo_id,
                ahora=unidad.reloj.ahora(),
            )

    return router


def _exigir(salida: VinculoSalida | None) -> VinculoSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida


__all__ = ["COOKIE_ESTADO", "crear_router"]
