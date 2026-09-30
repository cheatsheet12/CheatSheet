"""Superficie HTTP de los reembolsos (HU-E6-05), montada bajo `/cobros`.

**Sólo el Administrador** (RN-05): el guarda vive en los casos de uso, no acá.

**El reembolso por API son dos unidades de trabajo** y esa es la razón de ser de este módulo.
`unidad_de_trabajo` confirma **sólo si el cuerpo termina sin levantar**: una excepción dentro del
`async for` descarta todo lo escrito antes. Por eso:

1. La primera unidad (`SolicitarReembolso`) escribe la marca de «en proceso», el monto y la clave
   de idempotencia, y se confirma **antes** de hablar con MercadoPago.
2. La segunda (`EnviarReembolso`) llama a MercadoPago con esa clave y registra lo que contestó.
   Un rechazo **no se levanta adentro**: el caso de uso lo devuelve, la unidad se confirma con el
   rechazo y su evento `ERROR`, y **recién después del ciclo** se levanta para que la pantalla
   muestre el motivo. El patrón es el de `_rotar_refresh` en `routers/auth.py`.

Los montos entran como texto y la fecha como `YYYY-MM-DD` (un día, no un instante).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mercadopago import armar_pasarela, armar_saldos
from cheatsheet.api.routers.cobros import CobroSalida, a_salida, actor, exigir
from cheatsheet.contexts.payments.application.cobros import monto_desde
from cheatsheet.contexts.payments.application.errors import ReembolsoRechazado
from cheatsheet.contexts.payments.application.reembolsos import (
    ActualizarReembolso,
    EnviarReembolso,
    SolicitarReembolso,
)
from cheatsheet.contexts.payments.application.reembolsos_manuales import (
    CorregirReembolso,
    RegistrarReembolsoManual,
)
from cheatsheet.contexts.payments.infrastructure.ensamblado import Cobros
from fastapi import APIRouter, Request
from pydantic import BaseModel


class ReembolsoEntrada(BaseModel):
    #: Texto, nunca un número: un JSON numérico llega como `float` (`CLAUDE.md` §3.5).
    monto: str


class ReembolsoManualEntrada(BaseModel):
    monto: str
    #: El día en que se devolvió el dinero (no un instante): se guarda a las 12:00 de Argentina.
    fecha: date
    referencia: str | None = None
    motivo: str


class CorreccionEntrada(BaseModel):
    motivo: str


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["payments"])
    router.include_router(_rutas_de_api(recursos), prefix="/cobros")
    router.include_router(_rutas_manuales(recursos), prefix="/cobros")
    return router


async def _solicitar(recursos: Recursos, request: Request, cobro_id: UUID, monto: str) -> None:
    """T1: la marca de «en proceso» y la clave, **confirmadas** antes de hablar con MercadoPago."""
    empresa_id, usuario_id, rol = actor(request)
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        await SolicitarReembolso(
            cobros=Cobros.armar(unidad).cobros, publicador=unidad.publicador
        ).ejecutar(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            rol=rol,
            cobro_id=cobro_id,
            monto=monto_desde(monto),
            ahora=unidad.reloj.ahora(),
        )


async def _resolver(
    recursos: Recursos, request: Request, cobro_id: UUID, *, actualizar: bool
) -> CobroSalida:
    """T2: llama a MercadoPago con la clave guardada y registra lo que contestó.

    El rechazo se **guarda dentro** de la unidad y se **levanta después** del ciclo: levantarlo
    adentro descartaría el estado y el evento `ERROR` que el administrador necesita (H1).
    """
    empresa_id, usuario_id, rol = actor(request)
    salida: CobroSalida | None = None
    rechazo: str | None = None
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Cobros.armar(unidad)
        caso = (ActualizarReembolso if actualizar else EnviarReembolso)(
            cobros=piezas.cobros,
            reembolsos=piezas.reembolsos,
            pasarela=armar_pasarela(unidad, recursos.settings),
            saldos=armar_saldos(unidad),
            publicador=unidad.publicador,
        )
        resultado = await caso.ejecutar(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            rol=rol,
            cobro_id=cobro_id,
            ahora=unidad.reloj.ahora(),
        )
        salida = a_salida(resultado.cobro)
        rechazo = resultado.rechazo
    if rechazo is not None:
        raise ReembolsoRechazado(
            f"MercadoPago rechazo el reembolso: {rechazo}. El cobro sigue figurando como pagado."
        )
    return exigir(salida)


def _rutas_de_api(recursos: Recursos) -> APIRouter:
    """Por MercadoPago: pedir el reembolso y «Actualizar estado»."""
    router = APIRouter()

    @router.post("/{cobro_id}/reembolso")
    async def reembolsar(
        request: Request, cobro_id: UUID, entrada: ReembolsoEntrada
    ) -> CobroSalida:
        """HU-E6-05. 200 con el cobro (confirmado o «en proceso»); 422 con el motivo de
        MercadoPago **después** de escribir el rechazo; 409 si ya hay uno en vuelo."""
        await _solicitar(recursos, request, cobro_id, entrada.monto)
        return await _resolver(recursos, request, cobro_id, actualizar=False)

    @router.post("/{cobro_id}/reembolso/actualizacion")
    async def actualizar(request: Request, cobro_id: UUID) -> CobroSalida:
        """«Actualizar estado»: destraba un reembolso en proceso. Sin nada en vuelo no hace
        nada, así que apretarlo dos veces es inofensivo."""
        return await _resolver(recursos, request, cobro_id, actualizar=True)

    return router


async def _registrar(
    recursos: Recursos, request: Request, cobro_id: UUID, entrada: ReembolsoManualEntrada
) -> CobroSalida:
    empresa_id, usuario_id, rol = actor(request)
    salida: CobroSalida | None = None
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Cobros.armar(unidad)
        cobro = await RegistrarReembolsoManual(
            cobros=piezas.cobros,
            reembolsos=piezas.reembolsos,
            saldos=armar_saldos(unidad),
            publicador=unidad.publicador,
        ).ejecutar(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            rol=rol,
            cobro_id=cobro_id,
            monto=monto_desde(entrada.monto),
            dia=entrada.fecha,
            referencia=entrada.referencia,
            motivo=entrada.motivo,
            ahora=unidad.reloj.ahora(),
        )
        salida = a_salida(cobro)
    return exigir(salida)


async def _corregir(
    recursos: Recursos,
    request: Request,
    cobro_id: UUID,
    reembolso_id: UUID,
    entrada: CorreccionEntrada,
) -> CobroSalida:
    empresa_id, usuario_id, rol = actor(request)
    salida: CobroSalida | None = None
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Cobros.armar(unidad)
        cobro = await CorregirReembolso(
            cobros=piezas.cobros,
            reembolsos=piezas.reembolsos,
            saldos=armar_saldos(unidad),
            publicador=unidad.publicador,
        ).ejecutar(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            rol=rol,
            cobro_id=cobro_id,
            reembolso_id=reembolso_id,
            motivo=entrada.motivo,
            ahora=unidad.reloj.ahora(),
        )
        salida = a_salida(cobro)
    return exigir(salida)


def _rutas_manuales(recursos: Recursos) -> APIRouter:
    """Sin MercadoPago: el registro manual de una transferencia y la corrección de una fila."""
    router = APIRouter()

    @router.post("/{cobro_id}/reembolsos")
    async def registrar(
        request: Request, cobro_id: UUID, entrada: ReembolsoManualEntrada
    ) -> CobroSalida:
        """HU-E6-05 RN-07: la devolución de una transferencia, declarada a mano."""
        return await _registrar(recursos, request, cobro_id, entrada)

    @router.post("/{cobro_id}/reembolsos/{reembolso_id}/correccion")
    async def corregir(
        request: Request, cobro_id: UUID, reembolso_id: UUID, entrada: CorreccionEntrada
    ) -> CobroSalida:
        """HU-E6-05 RN-08: una fila negativa visible que anula la fila entera."""
        return await _corregir(recursos, request, cobro_id, reembolso_id, entrada)

    return router
