"""Superficie HTTP de los cobros (HU-E6-01 … HU-E6-06).

`EmpresaMiddleware` ya puso la empresa, el usuario y el rol en `request.state`. El rol se pasa
al caso de uso en vez de comprobarlo acá, por lo que dicen los demás routers y probó PRU-09.

**No hay `DELETE`.** Un cobro aprobado es plata que entró: se reembolsa. Uno pendiente se
cancela, que deja el motivo y el rastro que HU-E6-04 RN-04 pide. El backend no otorga el
permiso, así que una ruta acá sólo podría fallar.

**Los montos entran como texto.** Un número JSON llega como `float` de Python, que es el tipo
que `CLAUDE.md` §3.5 prohíbe cerca de la plata — y está mal en el cuarto decimal, que es
exactamente donde vive un centavo.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, TypeVar
from uuid import UUID

from cheatsheet.api.clave_de_pedido import exigir_clave_de_pedido
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mercadopago import armar_clientes, armar_pasarela, armar_saldos
from cheatsheet.contexts.payments.application.cobros import (
    CancelarCobro,
    ListarCobros,
    MetricasDelPeriodo,
    RegenerarLink,
    VerCobro,
    monto_desde,
)
from cheatsheet.contexts.payments.application.generacion_de_cobro import GenerarCobro
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro
from cheatsheet.contexts.payments.application.recordatorios import VerRecordatorios
from cheatsheet.contexts.payments.application.reembolsos_manuales import VerReembolsos
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro
from cheatsheet.contexts.payments.domain.recordatorio import Recordatorio
from cheatsheet.contexts.payments.domain.reembolso import Reembolso
from cheatsheet.contexts.payments.infrastructure.ensamblado import Cobros
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel


class CobroEntrada(BaseModel):
    cliente_id: UUID
    #: Texto, nunca un número. Ver el docstring del módulo.
    monto: str
    descripcion: str
    comprobante_id: UUID | None = None


class CancelacionEntrada(BaseModel):
    motivo: str


class RecordatorioSalida(BaseModel):
    id: UUID
    paso: int
    canal: str
    enviado_en: datetime | None
    estado_entrega: str | None
    #: Cuántos envíos empezaron (U7). Con `proximo_intento_en` arma «Reintentando · intento n de 3».
    intentos: int
    #: Cuándo toca el próximo intento. **Solo** mientras la fila espera un reintento: en un envío en
    #: curso la columna es la ventana de la reserva y mostrarla como «próximo» engañaría.
    proximo_intento_en: datetime | None
    #: Por qué falló: un código de Meta o una clase corta (`INCIERTO`, `COBRO_CERRADO`…).
    ultimo_error: str | None


class ReembolsoSalida(BaseModel):
    """Una fila del historial (HU-E6-05 RN-08): un reembolso o la corrección de uno."""

    id: UUID
    monto: Decimal
    fecha_devolucion: datetime
    origen: str
    referencia: str | None
    motivo: str | None
    #: La fila que esta anula; `null` si no es una corrección.
    corrige_a: UUID | None
    #: `true` si otra fila ya la anuló: la pantalla no ofrece corregirla de nuevo.
    corregido: bool


class CobroSalida(BaseModel):
    id: UUID
    cliente_id: UUID
    comprobante_id: UUID | None
    turno_id: UUID | None
    monto: Decimal
    #: El acumulado de reembolsos (ADR-0010): `0.00` mientras no hubo ninguno.
    monto_reembolsado: Decimal
    descripcion: str
    estado: str
    url_de_pago: str | None
    tiene_link_activo: bool
    vence_el: datetime
    #: Cuándo pagó el cliente (D91). `fecha_pago_aproximada` avisa cuándo es una estimación.
    fecha_pago: datetime | None
    fecha_pago_aproximada: bool
    medio_de_pago: str
    #: Solo las transferencias lo tienen (HU-E6-02 RN-05); los links lo dejan en `null`.
    numero_de_operacion: str | None
    #: HU-E6-05: la pantalla muestra «Reembolso en proceso» a partir de esto (decisión D27).
    reembolso_en_proceso: bool
    #: Cuánto se pidió, mientras el reembolso está en vuelo; `null` si no hay ninguno.
    reembolso_en_proceso_monto: Decimal | None
    #: HU-E6-04: entró plata por el link de un cobro cancelado. PAN-COB-02 lo muestra
    #: porque el aviso de severidad alta que lo acompaña manda al administrador acá.
    tiene_pago_huerfano: bool
    motivo_de_cancelacion: str | None
    created_at: datetime


class DetalleSalida(CobroSalida):
    """PAN-COB-02: el cobro más sus recordatorios (HU-E6-02 RN-01) y sus reembolsos."""

    recordatorios: list[RecordatorioSalida]
    #: Del más viejo al más nuevo. Las correcciones son filas negativas visibles (RN-08).
    reembolsos: list[ReembolsoSalida]


class MetricasSalida(BaseModel):
    cobrado: Decimal
    pendiente: Decimal
    en_mora: Decimal
    tasa_de_cobro: Decimal


class ListadoSalida(BaseModel):
    cobros: list[CobroSalida]
    metricas: MetricasSalida


def a_salida(cobro: Cobro) -> CobroSalida:
    return CobroSalida(
        id=cobro.id,
        cliente_id=cobro.cliente_id,
        comprobante_id=cobro.comprobante_id,
        turno_id=cobro.turno_id,
        monto=cobro.monto,
        monto_reembolsado=cobro.monto_reembolsado,
        descripcion=cobro.descripcion,
        estado=cobro.estado.value,
        url_de_pago=cobro.link.url if cobro.link else None,
        tiene_link_activo=cobro.tiene_link_activo,
        vence_el=cobro.vence_el,
        fecha_pago=cobro.fecha_pago,
        fecha_pago_aproximada=cobro.fecha_pago_aproximada,
        medio_de_pago=cobro.medio_de_pago.value,
        numero_de_operacion=cobro.numero_de_operacion,
        reembolso_en_proceso=cobro.reembolso_en_proceso,
        reembolso_en_proceso_monto=cobro.reembolso_solicitado_monto,
        tiene_pago_huerfano=cobro.tiene_pago_huerfano,
        motivo_de_cancelacion=cobro.motivo_de_cancelacion,
        created_at=cobro.created_at,
    )


def _a_reembolsos(filas: list[Reembolso]) -> list[ReembolsoSalida]:
    corregidos = {fila.corrige_a for fila in filas if fila.corrige_a is not None}
    return [
        ReembolsoSalida(
            id=fila.id,
            monto=fila.monto,
            fecha_devolucion=fila.fecha_devolucion,
            origen=fila.origen.value,
            referencia=fila.referencia,
            motivo=fila.motivo,
            corrige_a=fila.corrige_a,
            corregido=fila.id in corregidos,
        )
        for fila in filas
    ]


def _a_recordatorio(uno: Recordatorio) -> RecordatorioSalida:
    return RecordatorioSalida(
        id=uno.id,
        paso=uno.paso,
        canal=uno.canal,
        enviado_en=uno.enviado_en,
        estado_entrega=uno.estado_entrega.value if uno.estado_entrega else None,
        intentos=uno.intentos,
        proximo_intento_en=uno.proximo_intento_en if uno.esperando_reintento else None,
        ultimo_error=uno.ultimo_error,
    )


def actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _filtros(desde: datetime | None, hasta: datetime | None, estado: str | None) -> FiltrosDeCobro:
    """Arma el filtro, ignorando un estado que no esté en el catálogo.

    Un valor desconocido se vuelve «sin filtro» en vez de un 422: el query string viene de una
    URL que alguien pudo editar o marcar como favorita, y la respuesta honesta a un filtro que
    no entendemos es el listado sin filtrar, no una página de error.
    """
    estados = (
        (EstadoCobro[estado],) if estado is not None and estado in EstadoCobro.__members__ else ()
    )
    return FiltrosDeCobro(desde=desde, hasta=hasta, estados=estados)


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["payments"])
    router.include_router(_rutas(recursos), prefix="/cobros")
    router.include_router(_rutas_de_gestion(recursos), prefix="/cobros")
    return router


def _rutas(recursos: Recursos) -> APIRouter:
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request,
        desde: Annotated[datetime | None, Query()] = None,
        hasta: Annotated[datetime | None, Query()] = None,
        estado: Annotated[str | None, Query()] = None,
    ) -> ListadoSalida:
        """PAN-COB-01: el listado y las métricas del período, juntos.

        En una sola respuesta y no en dos rutas: la pantalla las necesita a la vez para su
        primer render, y separarlas haría que el encabezado y la tabla pudieran mostrar dos
        instantes distintos del mismo período.
        """
        empresa_id, _, _ = actor(request)
        filtros = _filtros(desde, hasta, estado)
        salida = ListadoSalida(
            cobros=[],
            metricas=MetricasSalida(
                cobrado=Decimal("0.00"),
                pendiente=Decimal("0.00"),
                en_mora=Decimal("0.00"),
                tasa_de_cobro=Decimal("0.00"),
            ),
        )
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Cobros.armar(unidad)
            cobros = await ListarCobros(piezas.cobros).ejecutar(filtros)
            # Las métricas van sin el filtro de estado: son del período entero, y calcularlas
            # sobre el filtro haría que «en mora» valiera cero cada vez que alguien filtra por
            # pagados.
            metricas = await MetricasDelPeriodo(piezas.cobros).ejecutar(
                ahora=unidad.reloj.ahora(),
                filtros=FiltrosDeCobro(desde=filtros.desde, hasta=filtros.hasta),
            )
            salida = ListadoSalida(
                cobros=[a_salida(uno) for uno in cobros],
                metricas=MetricasSalida(
                    cobrado=metricas.cobrado,
                    pendiente=metricas.pendiente,
                    en_mora=metricas.en_mora,
                    tasa_de_cobro=metricas.tasa_de_cobro,
                ),
            )
        return salida

    @router.get("/{cobro_id}")
    async def ver(request: Request, cobro_id: UUID) -> DetalleSalida:
        """PAN-COB-02. Todos los roles leen (RN-04)."""
        empresa_id, _, _ = actor(request)
        salida: DetalleSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Cobros.armar(unidad)
            cobro = await VerCobro(piezas.cobros).ejecutar(cobro_id)
            recordatorios = await VerRecordatorios(piezas.recordatorios).ejecutar(cobro_id)
            reembolsos = await VerReembolsos(piezas.reembolsos).ejecutar(cobro_id)
            salida = DetalleSalida(
                **a_salida(cobro).model_dump(),
                recordatorios=[_a_recordatorio(uno) for uno in recordatorios],
                reembolsos=_a_reembolsos(reembolsos),
            )
        return exigir(salida)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def generar(
        request: Request,
        entrada: CobroEntrada,
        clave: Annotated[UUID, Depends(exigir_clave_de_pedido)],
    ) -> CobroSalida:
        """HU-E6-03. **201 y no 202**: el link existe cuando esto contesta.

        Distinto de la emisión de un comprobante, que es 202 porque ARCA todavía no contestó.
        Acá MercadoPago ya devolvió la preferencia — si no lo hubiera hecho, el cobro no se
        habría creado.

        **`X-Idempotency-Key` obligatoria** (ADR-0013): el mismo pedido repetido contesta 201
        con el cobro original, sin volver a MercadoPago.
        """
        empresa_id, usuario_id, rol = actor(request)
        salida: CobroSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Cobros.armar(unidad)
            cobro = await GenerarCobro(
                cobros=piezas.cobros,
                pasarela=armar_pasarela(unidad, recursos.settings),
                saldos=armar_saldos(unidad),
                clientes=armar_clientes(unidad),
                publicador=unidad.publicador,
                url_de_retorno=recursos.settings.mercadopago_url_de_retorno,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                clave_idempotencia=clave,
                cliente_id=entrada.cliente_id,
                monto=monto_desde(entrada.monto),
                descripcion=entrada.descripcion,
                ahora=unidad.reloj.ahora(),
                comprobante_id=entrada.comprobante_id,
            )
            salida = a_salida(cobro)
        return exigir(salida)

    return router


def _rutas_de_gestion(recursos: Recursos) -> APIRouter:
    """Las dos que cambian el estado de un cobro (los reembolsos viven en `reembolsos.py`).

    En su propio router por el techo de complejidad de `CLAUDE.md` §5, y porque es una
    división honesta: éstas son las que Solo Lectura no puede tocar y las que la bitácora
    registra con un motivo.
    """
    router = APIRouter()

    @router.post("/{cobro_id}/link")
    async def regenerar(request: Request, cobro_id: UUID) -> CobroSalida:
        """El último criterio de HU-E6-03: invalida el anterior y activa el nuevo."""
        empresa_id, usuario_id, rol = actor(request)
        salida: CobroSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Cobros.armar(unidad)
            cobro = await RegenerarLink(
                cobros=piezas.cobros,
                pasarela=armar_pasarela(unidad, recursos.settings),
                publicador=unidad.publicador,
                url_de_retorno=recursos.settings.mercadopago_url_de_retorno,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                cobro_id=cobro_id,
                ahora=unidad.reloj.ahora(),
            )
            salida = a_salida(cobro)
        return exigir(salida)

    @router.post("/{cobro_id}/cancelacion")
    async def cancelar(
        request: Request, cobro_id: UUID, entrada: CancelacionEntrada
    ) -> CobroSalida:
        """HU-E6-04. El motivo es obligatorio y lo valida el agregado.

        Lleva pasarela porque RN-03 pide invalidar el link, y eso pasa en MercadoPago: si no
        se puede confirmar que murió, esto contesta 422 con el motivo y el cobro queda como
        estaba.
        """
        empresa_id, usuario_id, rol = actor(request)
        salida: CobroSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Cobros.armar(unidad)
            cobro = await CancelarCobro(
                cobros=piezas.cobros,
                pasarela=armar_pasarela(unidad, recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                cobro_id=cobro_id,
                motivo=entrada.motivo,
                ahora=unidad.reloj.ahora(),
            )
            salida = a_salida(cobro)
        return exigir(salida)

    return router


_Salida = TypeVar("_Salida", CobroSalida, DetalleSalida)


def exigir(salida: _Salida | None) -> _Salida:
    if salida is None:  # pragma: no cover — la unidad de trabajo siempre rinde una vez
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida
