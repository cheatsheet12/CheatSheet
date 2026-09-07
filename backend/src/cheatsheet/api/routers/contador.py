"""La única superficie del sistema que contesta sin sesión a datos de una empresa (HU-E10-06).

Está en su propio archivo y no junto a `reporteria.py` a propósito: son dos rutas públicas
entre casi cien que exigen sesión, y mezclarlas es cómo alguien termina agregando una tercera
sin notar en qué grupo la puso.

**Cómo se resuelve la empresa.** El contador no tiene JWT, así que el enlace es lo único que
dice de qué empresa es. El camino es el mismo que el login del épico 1 —y por el mismo motivo,
documentado en `identity/infrastructure/resolucion.py`—:

1. Se hashea el valor del enlace. El valor en claro no se guarda ni se registra en ningún lado.
2. Se resuelve la empresa en una sesión **sin empresa**, que no puede escribir nada, contra una
   función `SECURITY DEFINER` que devuelve un id y nada más.
3. Recién entonces se abre la unidad de trabajo real, ya acotada por RLS a esa empresa, y se
   valida el token adentro — donde `revocado` y `vencimiento` viven.

Hacer el paso 3 con una empresa inventada es el bug que el épico 1 documenta: las escrituras
—acá, el contador de accesos— caen contra una política que no las deja pasar, o peor, no fallan
y no hacen nada.

**Qué se puede ver desde acá** (RN-02): los paquetes y el tablero del período. Ni clientes, ni
comprobantes, ni cobros, ni configuración. No es una lista de permisos: es que estas dos rutas
son todo lo que hay, y ninguna de las dos sabe pedir otra cosa.
"""

from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.reporteria import (
    armar_agenda_leida,
    armar_bitacora,
    armar_cobranzas,
    armar_facturacion,
)
from cheatsheet.api.routers.reporteria import (
    ListadoDePaquetes,
    TableroSalida,
    descarga,
    paquete_salida,
    tablero_salida,
)
from cheatsheet.contexts.reporting.application.errors import AccesoNoDisponible
from cheatsheet.contexts.reporting.application.paquete import (
    AccederComoContador,
    DescargarPaquete,
)
from cheatsheet.contexts.reporting.application.tablero import VerTablero, periodo_por_defecto
from cheatsheet.contexts.reporting.domain.paquete import MENSAJE_ACCESO_NO_DISPONIBLE
from cheatsheet.contexts.reporting.domain.reporte import Periodo
from cheatsheet.contexts.reporting.infrastructure.acceso import EnlaceContableAleatorio
from cheatsheet.contexts.reporting.infrastructure.ensamblado import Reporteria
from cheatsheet.contexts.reporting.infrastructure.repositories import empresa_de_token_contable
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.shared.empresa import EmpresaId
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

_T = TypeVar("_T")


def _exigir(salida: _T | None) -> _T:
    if salida is None:  # pragma: no cover - la unidad de trabajo siempre entrega una vuelta
        raise RuntimeError("La unidad de trabajo no produjo una respuesta")
    return salida


class AccesoSalida(BaseModel):
    """Lo que ve el contador. **Sin nombres de clientes y sin comprobantes.**"""

    vence: str
    tablero: TableroSalida
    paquetes: ListadoDePaquetes


async def _empresa_del_enlace(recursos: Recursos, valor: str) -> EmpresaId:
    """De qué empresa es el enlace. Levanta el texto de la historia si no lo es de ninguna.

    Un enlace inexistente y uno revocado dan **el mismo error**: distinguirlos le diría a quien
    probó un enlace ajeno si ese enlace existió alguna vez.
    """
    valor_hash = EnlaceContableAleatorio().hashear(valor)
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresa_id = await empresa_de_token_contable(sesion, valor_hash)
    if empresa_id is None:
        raise AccesoNoDisponible(MENSAJE_ACCESO_NO_DISPONIBLE)
    return empresa_id


def crear_router(recursos: Recursos) -> APIRouter:
    """Las dos rutas del contador externo. **Públicas**: ver el docstring del módulo."""
    router = APIRouter(prefix="/contador", tags=["reporting"])

    @router.get("/{valor}")
    async def acceder(request: Request, valor: str) -> AccesoSalida:
        """HU-E10-06. Valida, cuenta el acceso y devuelve el tablero y los paquetes."""
        del request  # La firma la pide FastAPI para el manejo de errores; no se lee nada.
        empresa_id = await _empresa_del_enlace(recursos, valor)
        salida: AccesoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            ahora = unidad.reloj.ahora()
            acceso = await AccederComoContador(
                tokens=piezas.tokens,
                paquetes=piezas.paquetes,
                generador=piezas.enlaces,
                publicador=unidad.publicador,
            ).ejecutar(valor=valor, ahora=ahora)

            # El tablero del último paquete, o el del mes en curso si todavía no hay ninguno:
            # es el período del que el contador vino a hablar, y pedirle que lo elija en una
            # pantalla sin sesión sería pedirle que adivine cuál cerró su cliente.
            periodo = (
                Periodo.del_mes(acceso.paquetes[0].periodo_anio, acceso.paquetes[0].periodo_mes)
                if acceso.paquetes
                else periodo_por_defecto(ahora.date())
            )
            tablero = await VerTablero(
                facturacion=armar_facturacion(unidad),
                cobranzas=armar_cobranzas(unidad),
                agenda=armar_agenda_leida(unidad),
                bitacora=armar_bitacora(unidad),
            ).ejecutar(periodo)

            salida = AccesoSalida(
                vence=acceso.vence.isoformat(),
                tablero=tablero_salida(tablero),
                paquetes=ListadoDePaquetes(
                    paquetes=[paquete_salida(uno) for uno in acceso.paquetes]
                ),
            )
        return _exigir(salida)

    @router.get("/{valor}/paquetes/{paquete_id}")
    async def descargar(valor: str, paquete_id: UUID) -> Response:
        """El ZIP. **Revalida el enlace en cada descarga**, no sólo al entrar.

        Sin eso, una pestaña abierta seguiría bajando documentación fiscal después de que el
        administrador apretó «revocar», que es exactamente lo que RN-04 dice que no pasa. Y por
        eso cuenta el acceso también: bajar el paquete es acceder.
        """
        empresa_id = await _empresa_del_enlace(recursos, valor)
        salida: Response | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Reporteria.armar(unidad, recursos.settings)
            await AccederComoContador(
                tokens=piezas.tokens,
                paquetes=piezas.paquetes,
                generador=piezas.enlaces,
                publicador=unidad.publicador,
            ).ejecutar(valor=valor, ahora=unidad.reloj.ahora())
            contenido, tipo, nombre = await DescargarPaquete(
                paquetes=piezas.paquetes, archivos=piezas.archivos
            ).ejecutar(paquete_id)
            salida = descarga(contenido, tipo, nombre)
        return _exigir(salida)

    return router


__all__ = ["AccesoSalida", "crear_router"]
