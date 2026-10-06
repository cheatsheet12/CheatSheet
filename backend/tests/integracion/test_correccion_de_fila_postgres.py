"""Una fila corregida, contra el motor que guarda sus errores (unidad correccion-de-filas-con-error).

Lo que un doble no puede probar: que `corregida_en` **sobreviva a la ida y vuelta** por la columna
que la migración 0035 agregó, que corregir **no borre** el error (el procesamiento es el registro
de un import), y que una empresa no vea los errores de otra.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import huella_de
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import EntradaDeMapeo, Mapeo
from cheatsheet.contexts.spreadsheet_sync.domain.procesamiento import (
    ErrorDeFila,
    EstadoProcesamiento,
    ProcesamientoDePlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    DireccionSync,
    ProveedorPlanilla,
    ReferenciaDeArchivo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.repositories import (
    RepositorioMapeoPostgres,
    RepositorioProcesamientoPostgres,
    RepositorioVinculoPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
AHORA = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
CORREGIDA = datetime(2026, 10, 7, 9, 30, tzinfo=UTC)


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


async def _procesamiento_con_errores(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
) -> ProcesamientoDePlanilla:
    """Un vínculo, un mapeo y un procesamiento con dos filas en error, ya guardados."""
    vinculo = VinculoDePlanilla(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        proveedor=ProveedorPlanilla.ARCHIVO,
        direccion=DireccionSync.SOLO_LECTURA,
        hoja_empresa="clientes.xlsx",
        archivo=ReferenciaDeArchivo(
            clave="planillas/x/y.xlsx", nombre_original="clientes.xlsx", tamano_bytes=100
        ),
        created_at=AHORA,
        updated_at=AHORA,
    )
    mapeo = Mapeo(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        huella_encabezado=huella_de(("Cliente",)),
        entradas=[
            EntradaDeMapeo(
                id=uuid.uuid4(),
                columna_origen="Cliente",
                atributo_destino="nombre",
                score=Decimal("0.9"),
            )
        ],
        created_at=AHORA,
        updated_at=AHORA,
    )
    procesamiento = ProcesamientoDePlanilla(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        vinculo_id=vinculo.id,
        mapeo_id=mapeo.id,
        referencia_archivo="planillas/x/y.xlsx",
        created_at=AHORA,
    )
    procesamiento.contar_fila_ok()
    for numero in (5, 6):
        procesamiento.registrar_error(
            error=ErrorDeFila(id=uuid.uuid4(), numero_fila=numero, motivo="CUIT invalido")
        )
    procesamiento.cerrar(duracion_ms=10, ahora=AHORA)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioVinculoPostgres(sesion).agregar(vinculo)
        await RepositorioMapeoPostgres(sesion).agregar(mapeo)
        await RepositorioProcesamientoPostgres(sesion).agregar(procesamiento)
        await RepositorioProcesamientoPostgres(sesion).actualizar(procesamiento)
    return procesamiento


async def test_corregir_una_fila_persiste_sin_borrar_el_error(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    procesamiento = await _procesamiento_con_errores(sesiones, empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioProcesamientoPostgres(sesion)
        cargado = await repo.buscar_por_id(procesamiento.id)
        assert cargado is not None
        cargado.corregir_fila(numero_fila=5, ahora=CORREGIDA)
        await repo.actualizar(cargado)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        recuperado = await RepositorioProcesamientoPostgres(sesion).buscar_por_id(procesamiento.id)

    assert recuperado is not None
    # El error se conserva como historia: el procesamiento es el registro de un import.
    assert [e.numero_fila for e in recuperado.errores] == [5, 6]
    corregido, pendiente = recuperado.errores
    assert corregido.corregida_en == CORREGIDA
    assert pendiente.corregida_en is None
    assert [e.numero_fila for e in recuperado.errores_pendientes] == [6]
    assert (recuperado.filas_ok, recuperado.filas_error, recuperado.filas_totales) == (2, 1, 3)
    assert recuperado.filas_a_reprocesar == (6,)


async def test_corregir_la_ultima_fila_deja_la_carga_completada_en_la_base(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    procesamiento = await _procesamiento_con_errores(sesiones, empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioProcesamientoPostgres(sesion)
        cargado = await repo.buscar_por_id(procesamiento.id)
        assert cargado is not None
        cargado.corregir_fila(numero_fila=5, ahora=CORREGIDA)
        cargado.corregir_fila(numero_fila=6, ahora=CORREGIDA)
        await repo.actualizar(cargado)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        recuperado = await RepositorioProcesamientoPostgres(sesion).buscar_por_id(procesamiento.id)

    assert recuperado is not None
    assert recuperado.estado is EstadoProcesamiento.COMPLETADO
    assert recuperado.filas_error == 0
    assert recuperado.filas_a_reprocesar == ()


async def test_guardar_dos_veces_no_duplica_ni_pisa_los_errores(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`actualizar` inserta sólo los errores nuevos: repetirlo no los multiplica."""
    empresa_id = await _empresa(engine_dueno)
    procesamiento = await _procesamiento_con_errores(sesiones, empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioProcesamientoPostgres(sesion).actualizar(procesamiento)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        recuperado = await RepositorioProcesamientoPostgres(sesion).buscar_por_id(procesamiento.id)

    assert recuperado is not None
    assert [e.numero_fila for e in recuperado.errores] == [5, 6]


async def test_una_empresa_no_ve_los_errores_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La barrera es de PostgreSQL: un doble que filtra en Python probaría el doble."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    procesamiento = await _procesamiento_con_errores(sesiones, empresa_a)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        ajeno = await RepositorioProcesamientoPostgres(sesion).buscar_por_id(procesamiento.id)

    assert ajeno is None
