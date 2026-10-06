"""La numeración fiscal contra el motor, que es lo único que la hace única.

**El test que importa es el de concurrencia.** Decisión D14: dos emisiones simultáneas
sobre el mismo punto y el mismo tipo no pueden sacar el mismo número. ARCA rechaza la
segunda —o, peor, autoriza las dos, y dos comprobantes autorizados con el mismo número se
arreglan con la AFIP y no con un `UPDATE`.

Eso **no se puede probar con un doble**: lo que serializa es `SELECT … FOR UPDATE`, y un
doble sin motor devolvería el mismo contador a los dos y el test pasaría igual probando
nada. Es el mismo argumento con el que el épico 1 probó el invariante del último
Administrador, y acá hay más en juego.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.billing.application.errors import PuntoDeVentaDuplicado
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.contexts.billing.infrastructure.repositories import (
    RepositorioPuntoDeVentaPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
FACTURA_B = TipoComprobante.FACTURA_B


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _punto(empresa_id: EmpresaId, numero: int = 1) -> PuntoDeVenta:
    return PuntoDeVenta(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        numero=numero,
        descripcion="Casa central",
        created_at=AHORA,
    )


async def _guardar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, punto: PuntoDeVenta
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioPuntoDeVentaPostgres(sesion).agregar(punto)


async def test_dos_emisiones_simultaneas_no_sacan_el_mismo_numero(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Decisión D14, probada contra el motor con dos transacciones de verdad.

    Las dos corrutinas toman el punto con `FOR UPDATE` y piden el siguiente número al mismo
    tiempo. Si el candado no estuviera, las dos leerían `0` y las dos escribirían `1`.
    """
    empresa_id = await _empresa(engine_dueno)
    punto = _punto(empresa_id)
    await _guardar(sesiones, empresa_id, punto)

    async def emitir() -> int:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            repo = RepositorioPuntoDeVentaPostgres(sesion)
            tomado = await repo.tomar_para_emitir(punto.id)
            assert tomado is not None
            numero = tomado.siguiente_numero(FACTURA_B)
            # Un respiro dentro de la transacción: sin candado, las dos leerían el mismo
            # contador justo acá. Con candado, la segunda todavía está esperando.
            await asyncio.sleep(0.05)
            await repo.guardar(tomado)
            return numero

    primero, segundo = await asyncio.gather(emitir(), emitir())

    assert {primero, segundo} == {1, 2}

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        final = await RepositorioPuntoDeVentaPostgres(sesion).buscar_por_id(punto.id)
    assert final is not None
    assert final.ultimo_numero(FACTURA_B) == 2


async def test_diez_emisiones_concurrentes_dan_diez_numeros_distintos(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La versión que se parece a un día ocupado."""
    empresa_id = await _empresa(engine_dueno)
    punto = _punto(empresa_id, numero=2)
    await _guardar(sesiones, empresa_id, punto)

    async def emitir() -> int:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            repo = RepositorioPuntoDeVentaPostgres(sesion)
            tomado = await repo.tomar_para_emitir(punto.id)
            assert tomado is not None
            numero = tomado.siguiente_numero(FACTURA_B)
            await repo.guardar(tomado)
            return numero

    numeros = await asyncio.gather(*[emitir() for _ in range(10)])

    assert sorted(numeros) == list(range(1, 11))


async def test_dos_puntos_con_el_mismo_numero_en_una_empresa_son_rechazados(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """HU-E5-05: «Ya existe un punto de venta con ese numero.», por el índice único.

    Es una garantía distinta de la de arriba: esta impide dos **puntos** con el mismo
    número; aquella impide dos **comprobantes**.
    """
    empresa_id = await _empresa(engine_dueno)
    await _guardar(sesiones, empresa_id, _punto(empresa_id, numero=3))

    with pytest.raises(PuntoDeVentaDuplicado) as exc:
        await _guardar(sesiones, empresa_id, _punto(empresa_id, numero=3))

    # El mensaje de la historia, para que llegue a la pantalla: es un `EntradaInvalida` y
    # responde 422, que es el status con el que el BFF reenvía el detalle.
    assert "Ya existe un punto de venta con ese número." in str(exc.value)


async def test_el_mismo_numero_en_dos_empresas_convive(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El punto de venta 1 de una empresa no tiene nada que ver con el de otra."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    await _guardar(sesiones, empresa_a, _punto(empresa_a, numero=1))
    await _guardar(sesiones, empresa_b, _punto(empresa_b, numero=1))

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        de_a = await RepositorioPuntoDeVentaPostgres(sesion).listar()
    assert len(de_a) == 1


async def test_una_empresa_no_ve_los_puntos_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    punto = _punto(empresa_a, numero=4)
    await _guardar(sesiones, empresa_a, punto)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        repo = RepositorioPuntoDeVentaPostgres(sesion)
        assert await repo.buscar_por_id(punto.id) is None
        assert await repo.listar() == []
        # Y tampoco lo puede tomar para emitir, que es el camino que importa.
        assert await repo.tomar_para_emitir(punto.id) is None


async def test_el_numerador_sobrevive_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Un JSONB mutado en el lugar no se persiste: SQLAlchemy no rastrea eso.

    El repositorio lo reasigna a propósito, y este test es lo que lo mantiene así — un
    contador que falla en guardarse es un número de comprobante reusado en el próximo
    request.
    """
    empresa_id = await _empresa(engine_dueno)
    punto = _punto(empresa_id, numero=5)
    await _guardar(sesiones, empresa_id, punto)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioPuntoDeVentaPostgres(sesion)
        tomado = await repo.tomar_para_emitir(punto.id)
        assert tomado is not None
        tomado.siguiente_numero(TipoComprobante.FACTURA_A)
        tomado.siguiente_numero(TipoComprobante.FACTURA_B)
        tomado.siguiente_numero(TipoComprobante.FACTURA_B)
        await repo.guardar(tomado)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        final = await RepositorioPuntoDeVentaPostgres(sesion).buscar_por_id(punto.id)

    assert final is not None
    assert final.ultimo_numero(TipoComprobante.FACTURA_A) == 1
    assert final.ultimo_numero(TipoComprobante.FACTURA_B) == 2


async def test_no_se_puede_borrar_un_punto_de_venta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El rol de la aplicación no tiene `DELETE`: los comprobantes emitidos quedarían
    huérfanos, y llevan un CAE."""
    empresa_id = await _empresa(engine_dueno)
    punto = _punto(empresa_id, numero=6)
    await _guardar(sesiones, empresa_id, punto)

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("DELETE FROM punto_de_venta WHERE id = :id"), {"id": punto.id}
            )
