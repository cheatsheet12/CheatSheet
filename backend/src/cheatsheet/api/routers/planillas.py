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
    ProveedorDePlanillaNoDisponible,
)
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import (
    OBLIGATORIOS_DE_CLIENTE,
    ConfirmarMapeo,
    CorregirMapeo,
    LeerEncabezados,
    ProponerMapeo,
    ReabrirMapeo,
    VistaDeMapeo,
)
from cheatsheet.contexts.spreadsheet_sync.application.procesamientos import (
    ConsultarProcesamiento,
    ListarProcesamientos,
    PrepararReproceso,
)
from cheatsheet.contexts.spreadsheet_sync.application.vinculos import (
    ConfirmarVinculacionConGoogle,
    DesvincularPlanilla,
    IniciarVinculacionConGoogle,
    ListarVinculos,
    SubirPlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import NivelDeConfianza
from cheatsheet.contexts.spreadsheet_sync.domain.procesamiento import (
    EstadoProcesamiento,
    ProcesamientoDePlanilla,
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
    modelo_de_lenguaje,
    proveedor_de_planilla,
)
from cheatsheet.contexts.spreadsheet_sync.infrastructure.lector import LectorDePlanilla
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
from cheatsheet.workers.tasks_spreadsheet import encolar_procesamiento
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
    #: Lo que identifica al documento para el proveedor, y lo único con lo que la persona
    #: puede distinguir dos planillas de Google en el listado: la hoja se llama «Clientes»
    #: en todas.
    identificador_externo: str | None = None
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


class ProcesamientoEntrada(BaseModel):
    vinculo_id: UUID


class EncoladoSalida(BaseModel):
    """The answer to a 202: the work was accepted, not done."""

    encolado: bool


class ErrorDeFilaSalida(BaseModel):
    """HU-E3-05 RN-02: the row number of the original file, and why it failed."""

    numero_fila: int
    motivo: str


class CargaSalida(BaseModel):
    id: UUID
    estado: EstadoProcesamiento
    filas_totales: int
    filas_ok: int
    filas_error: int
    es_reproceso: bool
    created_at: datetime


class ListadoDeCargasSalida(BaseModel):
    cargas: list[CargaSalida]


class DetalleDeCargaSalida(BaseModel):
    carga: CargaSalida
    errores: list[ErrorDeFilaSalida]
    #: False for Solo Lectura (RN-04), and also when nothing failed.
    puede_reprocesar: bool


def _carga_a_salida(procesamiento: ProcesamientoDePlanilla) -> CargaSalida:
    return CargaSalida(
        id=procesamiento.id,
        estado=procesamiento.estado,
        filas_totales=procesamiento.filas_totales,
        filas_ok=procesamiento.filas_ok,
        filas_error=procesamiento.filas_error,
        es_reproceso=procesamiento.es_reproceso,
        created_at=procesamiento.created_at,
    )


class ColumnaEntrada(BaseModel):
    """One header, and optionally a sample value read from the sheet.

    The sample travels **to** the panel, never to the model: decision D12. It arrives here
    from whoever read the spreadsheet and is stored so PAN-ING-02 can show it.
    """

    nombre: str
    ejemplo: str | None = None


class EncabezadosSalida(BaseModel):
    """Lo que el panel necesita para pedir una propuesta de mapeo.

    Reusa `ColumnaEntrada` en vez de declarar un gemelo: es exactamente la misma forma, y
    el panel devuelve estas columnas tal cual al pedir la propuesta.
    """

    columnas: list[ColumnaEntrada]


class PropuestaEntrada(BaseModel):
    vinculo_id: UUID
    columnas: list[ColumnaEntrada]
    para_servicios: bool = False


class CorreccionEntrada(BaseModel):
    columna: str
    #: `None` clears the assignment -- the `Sin asignar` of RN-03, chosen on purpose.
    atributo: str | None = None
    para_servicios: bool = False


class ConfirmacionDeMapeoEntrada(BaseModel):
    para_servicios: bool = False


class EntradaDeMapeoSalida(BaseModel):
    """The four things HU-E3-02's first criterion asks the review to show per column."""

    columna_origen: str
    atributo_destino: str | None
    confianza: NivelDeConfianza
    ejemplo: str | None
    corregida_a_mano: bool


class MapeoSalida(BaseModel):
    id: UUID
    estado: str
    version: int
    entradas: list[EntradaDeMapeoSalida]
    #: RN-02: which required attributes still have no column. Empty means confirmable.
    faltantes: list[str]
    puede_confirmarse: bool
    #: True when the model answered. The screen shows «Analizado por IA» on it.
    propuesto_por_el_modelo: bool
    #: True when RN-02 reused a stored mapping for this header structure. Separate from the
    #: flag above because the screen has three things to say and not two: lo propusimos,
    #: ya lo teníamos, y no pudimos proponerlo.
    reutilizado: bool = False


def _mapeo_a_salida(vista: VistaDeMapeo) -> MapeoSalida:
    return MapeoSalida(
        id=vista.mapeo.id,
        estado=vista.mapeo.estado.value,
        version=vista.mapeo.version,
        entradas=[
            EntradaDeMapeoSalida(
                columna_origen=e.columna_origen,
                atributo_destino=e.atributo_destino,
                confianza=e.confianza,
                ejemplo=e.ejemplo,
                corregida_a_mano=e.corregida_a_mano,
            )
            for e in vista.mapeo.entradas
        ],
        faltantes=list(vista.faltantes),
        puede_confirmarse=vista.puede_confirmarse,
        propuesto_por_el_modelo=vista.propuesto_por_el_modelo,
        reutilizado=vista.reutilizado,
    )


def _a_salida(vinculo: VinculoDePlanilla) -> VinculoSalida:
    return VinculoSalida(
        id=vinculo.id,
        proveedor=vinculo.proveedor,
        direccion=vinculo.direccion,
        hoja_empresa=vinculo.hoja_empresa,
        identificador_externo=vinculo.identificador_externo,
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
    router.include_router(_rutas_de_encabezados(recursos), prefix="/planillas")
    router.include_router(_rutas_de_mapeo(recursos), prefix="/planillas/mapeos")
    router.include_router(_rutas_de_procesamiento(recursos), prefix="/planillas/cargas")
    router.include_router(_rutas_de_lectura_de_cargas(recursos), prefix="/planillas/cargas")
    router.include_router(_rutas_de_reproceso(recursos), prefix="/planillas/cargas")
    return router


def _rutas_de_encabezados(recursos: Recursos) -> APIRouter:
    """El paso que conecta PAN-ING-01 con PAN-ING-02.

    `ProponerMapeo` recibe las columnas ya leídas, a propósito: así se lo prueba sin un
    archivo. Pero entre «subí el .xlsx» y «revisá el mapeo» alguien tiene que abrir el
    archivo, y ese alguien no puede ser el navegador — habría que meterle un parser de
    Excel al panel para leer algo que el backend ya sabe leer.
    """

    router = APIRouter()

    @router.get("/{vinculo_id}/encabezados")
    async def encabezados(request: Request, vinculo_id: UUID) -> EncabezadosSalida:
        """Todos los roles leen: revisar un mapeo es mirar, confirmarlo es otra cosa."""
        empresa_id, _, _ = _actor(request)
        salida: EncabezadosSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            columnas = await LeerEncabezados(
                vinculos=piezas.vinculos,
                almacenamiento=almacenamiento(recursos.settings),
                lector=LectorDePlanilla(),
            ).ejecutar(vinculo_id=vinculo_id)
            salida = EncabezadosSalida(
                columnas=[ColumnaEntrada(nombre=c.nombre, ejemplo=c.ejemplo) for c in columnas]
            )
        if salida is None:  # pragma: no cover — la unidad de trabajo siempre rinde una vez
            raise RuntimeError("La unidad de trabajo no produjo un resultado")
        return salida

    return router


def _rutas_de_mapeo(recursos: Recursos) -> APIRouter:
    """HU-E3-01 and HU-E3-02, on PAN-ING-02."""
    router = APIRouter()

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def proponer(request: Request, entrada: PropuestaEntrada) -> MapeoSalida:
        """The model proposes; a stored mapping for this structure short-circuits it."""
        empresa_id, usuario_id, _ = _actor(request)
        salida: MapeoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            vista = await ProponerMapeo(
                mapeos=piezas.mapeos,
                vinculos=piezas.vinculos,
                modelo=modelo_de_lenguaje(recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                vinculo_id=entrada.vinculo_id,
                columnas=tuple(c.nombre for c in entrada.columnas),
                ejemplos={c.nombre: c.ejemplo for c in entrada.columnas if c.ejemplo},
                ahora=unidad.reloj.ahora(),
                para_servicios=entrada.para_servicios,
            )
            salida = _mapeo_a_salida(vista)
        return _exigir_mapeo(salida)

    @router.put("/{mapeo_id}/columnas")
    async def corregir(request: Request, mapeo_id: UUID, entrada: CorreccionEntrada) -> MapeoSalida:
        """RN-01. The corrected entry stops being the model's opinion and becomes a fact."""
        empresa_id, _, rol = _actor(request)
        salida: MapeoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            vista = await CorregirMapeo(piezas.mapeos).ejecutar(
                mapeo_id=mapeo_id,
                rol=rol,
                columna=entrada.columna,
                atributo=entrada.atributo,
                ahora=unidad.reloj.ahora(),
                para_servicios=entrada.para_servicios,
            )
            salida = _mapeo_a_salida(vista)
        return _exigir_mapeo(salida)

    @router.post("/{mapeo_id}/confirmacion")
    async def confirmar(
        request: Request, mapeo_id: UUID, entrada: ConfirmacionDeMapeoEntrada
    ) -> MapeoSalida:
        """RN-02 and RN-03. Refuses while a required column is unassigned."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: MapeoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            mapeo = await ConfirmarMapeo(
                mapeos=piezas.mapeos, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                mapeo_id=mapeo_id,
                ahora=unidad.reloj.ahora(),
                para_servicios=entrada.para_servicios,
            )
            salida = _mapeo_a_salida(
                VistaDeMapeo(mapeo=mapeo, faltantes=(), propuesto_por_el_modelo=False)
            )
        return _exigir_mapeo(salida)

    @router.post("/{mapeo_id}/revision")
    async def reabrir(request: Request, mapeo_id: UUID) -> MapeoSalida:
        """La salida que `Mapeo.corregir` nombra al negarse sobre un mapeo confirmado."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: MapeoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            mapeo = await ReabrirMapeo(mapeos=piezas.mapeos, publicador=unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                mapeo_id=mapeo_id,
                ahora=unidad.reloj.ahora(),
            )
            # Se recalcula lo que falta: reabrir devuelve la pantalla al estado de revisión,
            # y ahí «qué obligatoria falta» vuelve a ser la pregunta.
            salida = _mapeo_a_salida(
                VistaDeMapeo(
                    mapeo=mapeo,
                    faltantes=mapeo.faltantes(OBLIGATORIOS_DE_CLIENTE),
                    propuesto_por_el_modelo=False,
                )
            )
        return _exigir_mapeo(salida)

    return router


def _exigir_mapeo(salida: MapeoSalida | None) -> MapeoSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida


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


def _rutas_de_procesamiento(recursos: Recursos) -> APIRouter:
    """The two operations that *start* work: processing and reprocessing (202).

    Split from the reads below for the reason the clients router gives -- one function
    with every route crosses the complexity ceiling of CLAUDE.md section 5 -- and the split
    that means something here is between what enqueues work and what looks at its result.
    """
    router = APIRouter()

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def procesar(request: Request, entrada: ProcesamientoEntrada) -> EncoladoSalida:
        """202, not 201: RN-01 says the processing is asynchronous.

        The screen shows «Procesando» and the row appears in `Cargas recientes` when the
        worker finishes. Answering 201 with a body would be claiming the import is done.
        """
        empresa_id, _, rol = _actor(request)
        if rol is RolUsuario.SOLO_LECTURA:
            raise EntradaInvalida("Un usuario de Solo Lectura no puede procesar una planilla")

        aceptado = encolar_procesamiento(
            recursos.settings, empresa_id=empresa_id, vinculo_id=entrada.vinculo_id
        )
        if not aceptado:
            # The broker is down. Told, rather than swallowed: somebody is watching this
            # screen waiting for it to say «Procesando».
            raise ProveedorDePlanillaNoDisponible(
                "No pudimos encolar el procesamiento. Intentalo de nuevo en un momento."
            )
        return EncoladoSalida(encolado=True)

    return router


def _rutas_de_lectura_de_cargas(recursos: Recursos) -> APIRouter:
    """What HU-E3-05 asks for: the result of a run and its failed rows."""
    router = APIRouter()

    @router.get("")
    async def listar(request: Request, vinculo_id: UUID | None = None) -> ListadoDeCargasSalida:
        """`Cargas recientes`. Every role reads (HU-E3-05 RN-04)."""
        empresa_id, _, _ = _actor(request)
        salida = ListadoDeCargasSalida(cargas=[])
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            cargas = await ListarProcesamientos(piezas.procesamientos).ejecutar(
                vinculo_id=vinculo_id
            )
            salida = ListadoDeCargasSalida(cargas=[_carga_a_salida(c) for c in cargas])
        return salida

    @router.get("/{procesamiento_id}")
    async def detalle(request: Request, procesamiento_id: UUID) -> DetalleDeCargaSalida:
        """PAN-ING-03. Readable by Solo Lectura, without the reprocess action (RN-04)."""
        empresa_id, _, rol = _actor(request)
        salida: DetalleDeCargaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            resumen = await ConsultarProcesamiento(piezas.procesamientos).ejecutar(
                procesamiento_id=procesamiento_id
            )
            salida = DetalleDeCargaSalida(
                carga=_carga_a_salida(resumen.procesamiento),
                errores=[
                    ErrorDeFilaSalida(numero_fila=e.numero_fila, motivo=e.motivo)
                    for e in resumen.procesamiento.errores
                ],
                puede_reprocesar=(
                    rol is not RolUsuario.SOLO_LECTURA
                    and bool(resumen.procesamiento.filas_a_reprocesar)
                ),
            )
        return _exigir_detalle(salida)

    return router


def _rutas_de_reproceso(recursos: Recursos) -> APIRouter:
    """HU-E3-06, on its own because it both reads a run and enqueues a new one."""
    router = APIRouter()

    @router.post("/{procesamiento_id}/reproceso", status_code=status.HTTP_202_ACCEPTED)
    async def reprocesar(request: Request, procesamiento_id: UUID) -> EncoladoSalida:
        """HU-E3-06. Only the rows that failed, so nothing is duplicated (RN-02)."""
        empresa_id, _, rol = _actor(request)
        aceptado = False
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Planillas.armar(unidad)
            original, filas = await PrepararReproceso(piezas.procesamientos).ejecutar(
                procesamiento_id=procesamiento_id, rol=rol
            )
            aceptado = encolar_procesamiento(
                recursos.settings,
                empresa_id=empresa_id,
                vinculo_id=original.vinculo_id,
                solo_filas=filas,
                origen_id=original.id,
            )
        if not aceptado:
            raise ProveedorDePlanillaNoDisponible(
                "No pudimos encolar el reproceso. Intentalo de nuevo en un momento."
            )
        return EncoladoSalida(encolado=True)

    return router


def _exigir_detalle(salida: DetalleDeCargaSalida | None) -> DetalleDeCargaSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida
