"""Superficie HTTP de la reportería (HU-E10-01 … HU-E10-05).

`EmpresaMiddleware` ya puso la empresa, el usuario y el rol en `request.state`. El rol se pasa
al caso de uso en vez de comprobarlo acá, por lo que dicen los demás routers y probó PRU-09.

**El tablero lo lee todo el mundo; los archivos no.** Ver números agregados no identifica a
nadie (HU-E10-01 RN-04 y RN-05), pero un CSV de facturación es la lista de clientes de la
empresa con sus CUIT. Por eso `GET /reporteria/tablero` no exige rol y `POST
/reporteria/reportes` sí — y el guarda vive en el caso de uso, no en esta capa.

**El período por defecto se calcula acá** —el mes en curso, HU-E10-01 RN-01— porque «hoy»
depende de la zona horaria, que es presentación. `VerTablero` contesta por cualquier período,
que es lo que necesitan el paquete contable y el barrido mensual.

La ruta del contador **no está en este archivo**: vive en `contador.py`, que es público, y
separarlas es deliberado — una ruta sin sesión al lado de doce con sesión es la que un día
alguien mueve de grupo sin darse cuenta.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, TypeVar
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.reporteria import (
    armar_agenda_leida,
    armar_aviso_al_contador,
    armar_bitacora,
    armar_cobranzas,
    armar_facturacion,
    armar_nombre_de_empresa,
)
from cheatsheet.contexts.reporting.application.generacion import (
    DescargarReporte,
    GenerarReporte,
    ListarReportes,
)
from cheatsheet.contexts.reporting.application.paquete import (
    ConfigurarPaquete,
    DescargarPaquete,
    GenerarPaqueteContable,
    InvitarContador,
    ListarPaquetes,
    RevocarAccesoDelContador,
    VerConfiguracionDelPaquete,
    periodo_cerrado,
)
from cheatsheet.contexts.reporting.application.tablero import (
    Metrica,
    PrevisualizarReporte,
    Tablero,
    VerTablero,
    periodo_por_defecto,
)
from cheatsheet.contexts.reporting.domain.paquete import ContenidoDelPaquete, PaqueteContable
from cheatsheet.contexts.reporting.domain.reporte import (
    FormatoReporte,
    Periodo,
    Reporte,
    TipoReporte,
)
from cheatsheet.contexts.reporting.infrastructure.ensamblado import Reporteria
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Query, Request, Response, status
from pydantic import BaseModel

_T = TypeVar("_T")

RUTA_DEL_CONTADOR = "/contador"


# -- entradas -------------------------------------------------------------------------


class ReporteEntrada(BaseModel):
    tipo: str
    formato: str


class PaqueteEntrada(BaseModel):
    """El «paquete de prueba» del cuarto criterio de HU-E10-04.

    El período es opcional: sin él sale el del mes cerrado, que es el mismo que va a armar el
    barrido. Poder pedir otro es la respuesta a la pregunta D6 del roadmap — sí, el
    administrador puede generar el paquete de un mes anterior, porque es exactamente lo que
    hace falta cuando un envío se perdió.
    """

    anio: int | None = None
    mes: int | None = None


class ConfiguracionEntrada(BaseModel):
    dia_de_envio: int
    formatos: list[str]
    contenido: list[str]
    email_contador: str | None = None
    activo: bool


class ContadorEntrada(BaseModel):
    email: str


# -- salidas --------------------------------------------------------------------------


class MetricaSalida(BaseModel):
    """Un número del encabezado. Los importes viajan como **texto**, nunca como número JSON.

    Es la misma regla del épico 5 y del 6: un `float` en JSON redondea en el cuarto decimal,
    que es donde vive un centavo, y el frontend formatea a partir de la cadena exacta.
    """

    valor: str
    anterior: str
    #: `None` cuando el período anterior fue cero: «creció 0%» y «no hay con qué comparar» son
    #: cosas distintas, y la pantalla dibuja un guion.
    variacion: str | None


class TableroSalida(BaseModel):
    desde: date
    hasta: date
    facturado: MetricaSalida
    cobrado: MetricaSalida
    turnos: MetricaSalida
    operaciones: MetricaSalida
    por_tipo: dict[str, str]
    por_semana: dict[str, str]
    pendiente: str
    en_mora: str
    sin_actividad: bool


class PrevisualizacionSalida(BaseModel):
    tipo: str
    desde: date
    hasta: date
    cantidad: int
    total: str
    hay_datos: bool


class ReporteSalida(BaseModel):
    id: UUID
    tipo: str
    formato: str
    desde: date
    hasta: date
    estado: str
    descargable: bool


class ListadoDeReportes(BaseModel):
    reportes: list[ReporteSalida]


class PaqueteSalida(BaseModel):
    id: UUID
    periodo: str
    anio: int
    mes: int
    totales_por_tipo: dict[str, dict[str, str]]
    disponible: bool


class ListadoDePaquetes(BaseModel):
    paquetes: list[PaqueteSalida]


class ContadorSalida(BaseModel):
    email: str | None
    invitado: bool
    vence: str | None
    accesos: int


class ConfiguracionSalida(BaseModel):
    activo: bool
    dia_de_envio: int
    formatos: list[str]
    contenido: list[str]
    email_contador: str | None
    proximo_envio: str | None
    contador: ContadorSalida


def _a_metrica(metrica: Metrica) -> MetricaSalida:
    return MetricaSalida(
        valor=str(metrica.valor),
        anterior=str(metrica.anterior),
        variacion=str(metrica.variacion) if metrica.variacion is not None else None,
    )


def tablero_salida(tablero: Tablero) -> TableroSalida:
    return TableroSalida(
        desde=tablero.periodo.desde,
        hasta=tablero.periodo.hasta,
        facturado=_a_metrica(tablero.facturado),
        cobrado=_a_metrica(tablero.cobrado),
        turnos=_a_metrica(tablero.turnos),
        operaciones=_a_metrica(tablero.operaciones),
        por_tipo={clave: str(valor) for clave, valor in tablero.por_tipo.items()},
        por_semana={clave: str(valor) for clave, valor in tablero.por_semana.items()},
        pendiente=str(tablero.pendiente),
        en_mora=str(tablero.en_mora),
        sin_actividad=tablero.sin_actividad,
    )


def _a_reporte(reporte: Reporte) -> ReporteSalida:
    return ReporteSalida(
        id=reporte.id,
        tipo=reporte.tipo.value,
        formato=reporte.formato.value,
        desde=reporte.periodo.desde,
        hasta=reporte.periodo.hasta,
        estado=reporte.estado.value,
        descargable=reporte.es_descargable,
    )


def paquete_salida(paquete: PaqueteContable) -> PaqueteSalida:
    return PaqueteSalida(
        id=paquete.id,
        periodo=paquete.etiqueta,
        anio=paquete.periodo_anio,
        mes=paquete.periodo_mes,
        totales_por_tipo=paquete.totales_por_tipo,
        disponible=paquete.esta_disponible,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _periodo(desde: date | None, hasta: date | None, hoy: date) -> Periodo:
    """El período pedido, o el mes en curso (HU-E10-01 RN-01)."""
    if desde is not None and hasta is not None:
        return Periodo(desde=desde, hasta=hasta)
    return periodo_por_defecto(hoy)


def _tipo(texto: str) -> TipoReporte:
    if texto not in TipoReporte.__members__:
        raise EntradaInvalida(f"«{texto}» no es un tipo de reporte valido")
    return TipoReporte[texto]


def _formato(texto: str) -> FormatoReporte:
    if texto not in FormatoReporte.__members__:
        raise EntradaInvalida(f"«{texto}» no es un formato valido")
    return FormatoReporte[texto]


def _contenido(textos: list[str]) -> frozenset[ContenidoDelPaquete]:
    elegidos = set()
    for texto in textos:
        if texto not in ContenidoDelPaquete.__members__:
            raise EntradaInvalida(f"«{texto}» no es un contenido valido del paquete")
        elegidos.add(ContenidoDelPaquete[texto])
    return frozenset(elegidos)


def _exigir(salida: _T | None) -> _T:
    if salida is None:  # pragma: no cover - la unidad de trabajo siempre entrega una vuelta
        raise RuntimeError("La unidad de trabajo no produjo una respuesta")
    return salida


def descarga(contenido: bytes, tipo: str, nombre: str) -> Response:
    """`attachment` y no `inline`: esto se guarda, no se mira en una pestaña."""
    return Response(
        content=contenido,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(prefix="/reporteria", tags=["reporting"])
    router.include_router(_rutas_del_tablero(recursos))
    router.include_router(_rutas_de_reportes(recursos), prefix="/reportes")
    router.include_router(_rutas_de_paquetes(recursos), prefix="/paquetes")
    router.include_router(_rutas_de_configuracion(recursos))
    return router


def _rutas_del_tablero(recursos: Recursos) -> APIRouter:
    """PAN-REP-01 (HU-E10-01 y HU-E10-02). **Todos los roles leen.**"""
    router = APIRouter()

    @router.get("/tablero")
    async def tablero(
        request: Request,
        desde: Annotated[date | None, Query()] = None,
        hasta: Annotated[date | None, Query()] = None,
    ) -> TableroSalida:
        empresa_id, _, _ = _actor(request)
        salida: TableroSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            periodo = _periodo(desde, hasta, unidad.reloj.ahora().date())
            resultado = await VerTablero(
                facturacion=armar_facturacion(unidad),
                cobranzas=armar_cobranzas(unidad),
                agenda=armar_agenda_leida(unidad),
                bitacora=armar_bitacora(unidad),
            ).ejecutar(periodo)
            salida = tablero_salida(resultado)
        return _exigir(salida)

    @router.get("/previsualizacion")
    async def previsualizacion(
        request: Request,
        tipo: Annotated[str, Query()],
        desde: Annotated[date | None, Query()] = None,
        hasta: Annotated[date | None, Query()] = None,
    ) -> PrevisualizacionSalida:
        """HU-E10-02. **No escribe nada**: se puede llamar cuantas veces haga falta."""
        empresa_id, _, _ = _actor(request)
        salida: PrevisualizacionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            periodo = _periodo(desde, hasta, unidad.reloj.ahora().date())
            estimacion = await PrevisualizarReporte(
                facturacion=armar_facturacion(unidad),
                cobranzas=armar_cobranzas(unidad),
                bitacora=armar_bitacora(unidad),
            ).ejecutar(tipo=_tipo(tipo), periodo=periodo)
            salida = PrevisualizacionSalida(
                tipo=estimacion.tipo.value,
                desde=estimacion.periodo.desde,
                hasta=estimacion.periodo.hasta,
                cantidad=estimacion.cantidad,
                total=str(estimacion.total),
                hay_datos=estimacion.hay_datos,
            )
        return _exigir(salida)

    return router


def _rutas_de_reportes(recursos: Recursos) -> APIRouter:
    """HU-E10-03: generar, descargar y el historial."""
    router = APIRouter()

    @router.get("")
    async def listar(request: Request) -> ListadoDeReportes:
        empresa_id, _, _ = _actor(request)
        salida: ListadoDeReportes | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            encontrados = await ListarReportes(piezas.reportes).ejecutar()
            salida = ListadoDeReportes(reportes=[_a_reporte(uno) for uno in encontrados])
        return _exigir(salida)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def generar(
        request: Request,
        entrada: ReporteEntrada,
        desde: Annotated[date | None, Query()] = None,
        hasta: Annotated[date | None, Query()] = None,
    ) -> ReporteSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: ReporteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            ahora = unidad.reloj.ahora()
            reporte = await GenerarReporte(
                reportes=piezas.reportes,
                facturacion=armar_facturacion(unidad),
                cobranzas=armar_cobranzas(unidad),
                bitacora=armar_bitacora(unidad),
                archivos=piezas.archivos,
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                tipo=_tipo(entrada.tipo),
                formato=_formato(entrada.formato),
                periodo=_periodo(desde, hasta, ahora.date()),
                ahora=ahora,
            )
            salida = _a_reporte(reporte)
        return _exigir(salida)

    @router.get("/{reporte_id}/archivo")
    async def descargar(request: Request, reporte_id: UUID) -> Response:
        empresa_id, _, _ = _actor(request)
        salida: Response | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            contenido, tipo, nombre = await DescargarReporte(
                piezas.reportes, piezas.archivos
            ).ejecutar(reporte_id)
            salida = descarga(contenido, tipo, nombre)
        return _exigir(salida)

    return router


def _rutas_de_paquetes(recursos: Recursos) -> APIRouter:
    """HU-E10-04: el listado, el paquete de prueba y su descarga."""
    router = APIRouter()

    @router.get("")
    async def listar(request: Request) -> ListadoDePaquetes:
        empresa_id, _, _ = _actor(request)
        salida: ListadoDePaquetes | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            encontrados = await ListarPaquetes(piezas.paquetes).ejecutar()
            salida = ListadoDePaquetes(paquetes=[paquete_salida(uno) for uno in encontrados])
        return _exigir(salida)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def generar(request: Request, entrada: PaqueteEntrada) -> PaqueteSalida:
        """El «paquete de prueba», que es el mismo que arma el barrido. Ver `PaqueteEntrada`."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: PaqueteSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            ahora = unidad.reloj.ahora()
            if rol is not RolUsuario.ADMINISTRADOR:
                raise EntradaInvalida("Solo un Administrador puede generar el paquete contable")
            configuracion = await piezas.paquetes.configuracion()
            periodo = (
                Periodo.del_mes(entrada.anio, entrada.mes)
                if entrada.anio is not None and entrada.mes is not None
                else periodo_cerrado(ahora)
            )
            paquete = await GenerarPaqueteContable(
                paquetes=piezas.paquetes,
                facturacion=armar_facturacion(unidad),
                cobranzas=armar_cobranzas(unidad),
                bitacora=armar_bitacora(unidad),
                archivos=piezas.archivos,
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                periodo=periodo,
                contenido=(
                    configuracion.contenido if configuracion else frozenset(ContenidoDelPaquete)
                ),
                formatos=configuracion.formatos if configuracion else frozenset({"PDF"}),
                ahora=ahora,
            )
            salida = paquete_salida(paquete)
        return _exigir(salida)

    @router.get("/{paquete_id}/archivo")
    async def descargar(request: Request, paquete_id: UUID) -> Response:
        empresa_id, _, _ = _actor(request)
        salida: Response | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            contenido, tipo, nombre = await DescargarPaquete(
                paquetes=piezas.paquetes, archivos=piezas.archivos
            ).ejecutar(paquete_id)
            salida = descarga(contenido, tipo, nombre)
        return _exigir(salida)

    return router


def _rutas_de_configuracion(recursos: Recursos) -> APIRouter:
    """PAN-REP-02: el envío automático (HU-E10-04) y el acceso del contador (HU-E10-05)."""
    router = APIRouter()

    @router.get("/configuracion")
    async def ver(request: Request) -> ConfiguracionSalida:
        empresa_id, _, _ = _actor(request)
        salida: ConfiguracionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            vista = await VerConfiguracionDelPaquete(
                paquetes=piezas.paquetes, tokens=piezas.tokens
            ).ejecutar(empresa_id=empresa_id, ahora=unidad.reloj.ahora())
            salida = ConfiguracionSalida(
                activo=vista.configuracion.activo,
                dia_de_envio=vista.configuracion.dia_de_envio,
                formatos=sorted(vista.configuracion.formatos),
                contenido=sorted(uno.value for uno in vista.configuracion.contenido),
                email_contador=vista.configuracion.email_contador,
                proximo_envio=(
                    vista.proximo_envio.isoformat() if vista.proximo_envio is not None else None
                ),
                contador=ContadorSalida(
                    email=vista.contador.email,
                    invitado=vista.contador.invitado,
                    vence=(
                        vista.contador.vence.isoformat()
                        if vista.contador.vence is not None
                        else None
                    ),
                    accesos=vista.contador.accesos,
                ),
            )
        return _exigir(salida)

    @router.put("/configuracion")
    async def configurar(request: Request, entrada: ConfiguracionEntrada) -> ConfiguracionSalida:
        empresa_id, usuario_id, rol = _actor(request)
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            await ConfigurarPaquete(
                paquetes=piezas.paquetes, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                dia_de_envio=entrada.dia_de_envio,
                formatos=frozenset(entrada.formatos),
                contenido=_contenido(entrada.contenido),
                email_contador=entrada.email_contador,
                activo=entrada.activo,
                ahora=unidad.reloj.ahora(),
            )
        # Se relee en otra transacción a propósito: lo que la pantalla necesita después de
        # guardar incluye el próximo envío y el estado del contador, y devolver eso desde el
        # caso de uso que escribe lo obligaría a saber de tokens.
        return await ver(request)

    @router.post("/contador", status_code=status.HTTP_201_CREATED)
    async def invitar(request: Request, entrada: ContadorEntrada) -> ContadorSalida:
        """HU-E10-05. **La respuesta no lleva el enlace**: el enlace va al mail del contador.

        Devolvérselo al administrador lo pondría en el historial del navegador y en cualquier
        log de acceso del camino, que es justo lo que el hash en la base evita.
        """
        empresa_id, usuario_id, rol = _actor(request)
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            await InvitarContador(
                paquetes=piezas.paquetes,
                tokens=piezas.tokens,
                generador=piezas.enlaces,
                aviso=armar_aviso_al_contador(recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                email=entrada.email,
                nombre_de_la_empresa=await armar_nombre_de_empresa(unidad, empresa_id),
                base_del_enlace=f"{recursos.settings.app_base_url.rstrip('/')}{RUTA_DEL_CONTADOR}",
                ahora=unidad.reloj.ahora(),
            )
        vista = await ver(request)
        return vista.contador

    @router.delete("/contador", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
    async def revocar(request: Request) -> Response:
        """HU-E10-05 RN-03. 204 y sin cuerpo, como el `logout` del épico 1."""
        empresa_id, usuario_id, rol = _actor(request)
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            await RevocarAccesoDelContador(
                tokens=piezas.tokens, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                ahora=unidad.reloj.ahora(),
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


#: Lo público de este módulo incluye los tres convertidores, y no por comodidad: la ruta del
#: contador (`contador.py`) devuelve exactamente las mismas formas, y dos conversiones paralelas
#: del mismo objeto son dos lugares donde un campo se agrega en uno solo.
__all__ = [
    "RUTA_DEL_CONTADOR",
    "ListadoDePaquetes",
    "TableroSalida",
    "crear_router",
    "descarga",
    "paquete_salida",
    "tablero_salida",
]
