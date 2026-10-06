"""HTTP surface for the customer catalogue (HU-E4-01, PAN-DM-01).

`EmpresaMiddleware` has already verified the access token and put the company, the user
and the role on `request.state`. **The role is passed down to the use case rather than
checked here**, for the reason the users router states: the endpoint is one caller among
several, and the rule belongs next to the operation it guards.

**There is no `DELETE`.** Taking a client out of circulation is `PUT /clientes/{id}/estado`
— see `application/clientes.py` for why a physical delete is not on offer.

The one handler that is not generic lives here: `ClienteDuplicado` carries the id of the
existing client, and the uniform error response of `api/errors.py` has nowhere to put it.
HU-E4-01 asks the screen to «ofrecer ver el duplicado», so the id has to reach it.
"""

from __future__ import annotations

from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.padron import armar_padron_de_clientes
from cheatsheet.contexts.master_data.application.clientes import (
    CambiarEstadoDeCliente,
    DatosDeCliente,
    EditarCliente,
    ListarClientes,
    RegistrarCliente,
    VerCliente,
    VistaDeCliente,
)
from cheatsheet.contexts.master_data.application.errors import ClienteDuplicado
from cheatsheet.contexts.master_data.application.padron import (
    ConsultarPadronParaCliente,
    EstadoDeConsulta,
    VistaDePadron,
)
from cheatsheet.contexts.master_data.domain.cliente import FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.valores import OrigenDato
from cheatsheet.contexts.master_data.infrastructure.ensamblado import DatosMaestros
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.fiscal import CondicionIVA
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ClienteEntrada(BaseModel):
    """`nombre` is optional because a valid CUIT can supply it — see `DatosDeCliente`."""

    nombre: str | None = None
    cuit: str | None = None
    condicion_iva: CondicionIVA | None = None
    contacto_whatsapp: str | None = None
    contacto_email: str | None = None


class EstadoEntrada(BaseModel):
    activo: bool


class ConsultaDePadronEntrada(BaseModel):
    cuit: str


class DatosDePadronSalida(BaseModel):
    razon_social: str | None = None
    condicion_iva: CondicionIVA | None = None
    activo: bool


class PadronSalida(BaseModel):
    """Three states, never two. See `master_data/application/padron.py`."""

    estado: EstadoDeConsulta
    datos: DatosDePadronSalida | None = None
    motivo: str | None = None


class ClienteSalida(BaseModel):
    id: str
    nombre: str
    cuit: str | None = None
    condicion_iva: CondicionIVA | None = None
    contacto_whatsapp: str | None = None
    contacto_email: str | None = None
    origen: OrigenDato
    activo: bool
    #: How ARCA answered on this save. Absent on reads and when there was no CUIT to ask
    #: about; `NO_DISPONIBLE` is what the screen turns into «no se pudo validar».
    validacion: PadronSalida | None = None


class ListadoSalida(BaseModel):
    clientes: list[ClienteSalida]
    total: int


def _padron_a_salida(vista: VistaDePadron | None) -> PadronSalida | None:
    if vista is None:
        return None
    return PadronSalida(
        estado=vista.estado,
        datos=(
            DatosDePadronSalida(
                razon_social=vista.datos.razon_social,
                condicion_iva=vista.datos.condicion_iva,
                activo=vista.datos.activo,
            )
            if vista.datos is not None
            else None
        ),
        motivo=vista.motivo,
    )


def _a_salida(vista: VistaDeCliente) -> ClienteSalida:
    cliente = vista.cliente
    return ClienteSalida(
        id=str(cliente.id),
        nombre=cliente.nombre,
        cuit=cliente.cuit.formateado if cliente.cuit else None,
        condicion_iva=cliente.condicion_iva,
        contacto_whatsapp=str(cliente.contacto_whatsapp) if cliente.contacto_whatsapp else None,
        contacto_email=str(cliente.contacto_email) if cliente.contacto_email else None,
        origen=cliente.origen,
        activo=cliente.activo,
        validacion=_padron_a_salida(vista.validacion),
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _datos(entrada: ClienteEntrada) -> DatosDeCliente:
    return DatosDeCliente(
        nombre=entrada.nombre,
        cuit=entrada.cuit,
        condicion_iva=entrada.condicion_iva,
        contacto_whatsapp=entrada.contacto_whatsapp,
        contacto_email=entrada.contacto_email,
    )


def _exigir(salida: ClienteSalida | None) -> ClienteSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida


async def manejar_duplicado(_: Request, exc: Exception) -> JSONResponse:
    """409 with the id of the client that already holds the CUIT.

    Registered in `create_app` beside the generic domain handler. It has to be more
    specific than that one because the generic body is `{error, detalle}` and the screen
    needs a third field to build the «ver el duplicado» link.
    """
    duplicado = exc if isinstance(exc, ClienteDuplicado) else ClienteDuplicado(str(exc))
    cuerpo: dict[str, str] = {
        "error": type(duplicado).__name__,
        "detalle": str(duplicado),
    }
    if duplicado.cliente_existente_id is not None:
        cuerpo["cliente_existente_id"] = str(duplicado.cliente_existente_id)
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=cuerpo)


def crear_router(recursos: Recursos) -> APIRouter:
    # The prefix is applied on inclusion rather than on the parent router, for the reason
    # the users router states: the listing route is `GET /clientes` with no path of its
    # own, and FastAPI rejects an empty path on a router included without a prefix.
    router = APIRouter(tags=["master_data"])
    router.include_router(_rutas_de_padron(recursos), prefix="/clientes")
    router.include_router(_rutas_de_lectura(recursos), prefix="/clientes")
    router.include_router(_rutas_de_catalogo(recursos), prefix="/clientes")
    return router


def _rutas_de_lectura(recursos: Recursos) -> APIRouter:
    """Reading the catalogue: the listing and one client by id.

    Apart from the writes because a route handler is one branch each and the module-level
    function that declares them shares the complexity ceiling of `CLAUDE.md` section 5.
    """
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request,
        texto: str | None = None,
        origen: OrigenDato | None = None,
        solo_activos: bool = False,
        categoria_id: UUID | None = None,
        limite: int = 50,
        desplazamiento: int = 0,
    ) -> ListadoSalida:
        """The catalogue of PAN-DM-01. Readable by Solo Lectura too (navigation map §5)."""
        empresa_id, _, rol = _actor(request)
        salida: ListadoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            listado = await ListarClientes(clientes=piezas.clientes).ejecutar(
                empresa_id=empresa_id,
                rol=rol,
                filtros=FiltrosDeCliente(
                    texto=texto,
                    origen=origen,
                    solo_activos=solo_activos,
                    categoria_id=categoria_id,
                ),
                pagina=Pagina(limite=limite, desplazamiento=desplazamiento),
            )
            salida = ListadoSalida(
                clientes=[_a_salida(VistaDeCliente(cliente)) for cliente in listado.clientes],
                total=listado.total,
            )
        if salida is None:  # pragma: no cover — the unit of work always yields once
            raise RuntimeError("La unidad de trabajo no produjo un resultado")
        return salida

    @router.get("/{cliente_id}")
    async def ver(cliente_id: UUID, request: Request) -> ClienteSalida:
        """One client by id, for the screens that preselect one (PAN-COB-03).

        A missing client and another company's answer the same, on purpose: see `VerCliente`.
        """
        empresa_id, _, rol = _actor(request)
        salida: ClienteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            cliente = await VerCliente(clientes=piezas.clientes).ejecutar(
                rol=rol, cliente_id=cliente_id
            )
            salida = _a_salida(VistaDeCliente(cliente))
        return _exigir(salida)

    return router


def _rutas_de_catalogo(recursos: Recursos) -> APIRouter:
    """The writes of HU-E4-01: creating, editing, taking out of use."""
    router = APIRouter()

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def registrar(entrada: ClienteEntrada, request: Request) -> ClienteSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: ClienteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            vista = await RegistrarCliente(
                clientes=piezas.clientes,
                padron=armar_padron_de_clientes(unidad, recursos.settings),
                publicador=unidad.publicador,
                reloj=unidad.reloj,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                datos=_datos(entrada),
                direccion_ip=_ip(request),
            )
            salida = _a_salida(vista)
        return _exigir(salida)

    @router.put("/{cliente_id}")
    async def editar(cliente_id: UUID, entrada: ClienteEntrada, request: Request) -> ClienteSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: ClienteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            vista = await EditarCliente(
                clientes=piezas.clientes,
                padron=armar_padron_de_clientes(unidad, recursos.settings),
                publicador=unidad.publicador,
                reloj=unidad.reloj,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                cliente_id=cliente_id,
                datos=_datos(entrada),
                direccion_ip=_ip(request),
            )
            salida = _a_salida(vista)
        return _exigir(salida)

    @router.put("/{cliente_id}/estado")
    async def cambiar_estado(
        cliente_id: UUID, entrada: EstadoEntrada, request: Request
    ) -> ClienteSalida:
        """Deactivate or reactivate. This is what the catalogue has instead of a delete."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: ClienteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            vista = await CambiarEstadoDeCliente(
                clientes=piezas.clientes,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                cliente_id=cliente_id,
                activo=entrada.activo,
                direccion_ip=_ip(request),
            )
            salida = _a_salida(vista)
        return _exigir(salida)

    return router


def _rutas_de_padron(recursos: Recursos) -> APIRouter:
    """Mounted before the catalogue routes, so `/clientes/padron` is never read as an id.

    Today the two could not collide — one is a `POST`, the other a `PUT` — but the day
    somebody adds `GET /clientes/{cliente_id}` they would, and the failure would be a
    UUID parse error on a route that used to work.
    """
    router = APIRouter()

    @router.post("/padron")
    async def consultar_padron(entrada: ConsultaDePadronEntrada, request: Request) -> PadronSalida:
        """The «Validar contra ARCA» button of the form. Writes nothing.

        A `POST` on a read for the reason the onboarding endpoint gives: the CUIT is
        somebody's tax id, and in a query string it would end up in access logs and in
        browser history.
        """
        empresa_id, _, rol = _actor(request)
        salida: PadronSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            vista = await ConsultarPadronParaCliente(
                padron=armar_padron_de_clientes(unidad, recursos.settings)
            ).ejecutar(empresa_id=empresa_id, cuit=entrada.cuit, rol=rol)
            salida = _padron_a_salida(vista)
        if salida is None:  # pragma: no cover — the unit of work always yields once
            raise RuntimeError("La unidad de trabajo no produjo un resultado")
        return salida

    return router
