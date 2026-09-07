"""Los vínculos de planilla contra el motor que los hace cumplir (HU-E2-04).

Tres cosas de esta unidad no se pueden probar con un doble:

1. **El aislamiento entre empresas.** Es una política de PostgreSQL. Un doble que filtra
   por `empresa_id` en Python probaría el doble, no la barrera.
2. **El CHECK que dice que solo Google Sheets escribe.** El agregado ya lo impone, pero
   este es el que sigue en pie cuando alguien abre `psql` a las tres de la mañana.
3. **Que `DELETE` sí esté otorgado**, a diferencia de la bitácora y de `tarea_asincrona`.
   Desvincular es una operación legítima del Administrador.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    DireccionSync,
    ProveedorPlanilla,
    ReferenciaDeArchivo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.repositories import (
    RepositorioVinculoPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _vinculo(empresa_id: EmpresaId, **overrides: object) -> VinculoDePlanilla:
    ahora = datetime.now(UTC)
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "empresa_id": empresa_id,
        "proveedor": ProveedorPlanilla.GOOGLE_SHEETS,
        "direccion": DireccionSync.SOLO_LECTURA,
        "hoja_empresa": "Clientes",
        "identificador_externo": "1AbCdEf",
        "created_at": ahora,
        "updated_at": ahora,
    }
    base.update(overrides)
    return VinculoDePlanilla(**base)  # type: ignore[arg-type]


async def test_una_empresa_no_ve_los_vinculos_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 7 del plan. La barrera es de PostgreSQL, no de la aplicación."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    vinculo = _vinculo(empresa_a)
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        await RepositorioVinculoPostgres(sesion).agregar(vinculo)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        repo = RepositorioVinculoPostgres(sesion)
        assert await repo.buscar_por_id(vinculo.id) is None
        assert await repo.listar() == []

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        recuperado = await RepositorioVinculoPostgres(sesion).buscar_por_id(vinculo.id)
    assert recuperado is not None
    assert recuperado.proveedor is ProveedorPlanilla.GOOGLE_SHEETS


async def test_el_motor_tambien_rechaza_que_un_archivo_se_vincule_para_escribir(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El invariante del agregado, repetido en la base.

    Se escribe por SQL crudo a propósito: el agregado ya no dejaría construir esto, y lo
    que se está probando es la segunda línea de defensa, no la primera.
    """
    empresa_id = await _empresa(engine_dueno)

    with pytest.raises((IntegrityError, DBAPIError)):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text(
                    "INSERT INTO vinculo_de_planilla "
                    "(id, empresa_id, proveedor, direccion, hoja_empresa, archivo_clave,"
                    " created_at, updated_at) "
                    "VALUES (:id, :empresa, 'ARCHIVO', 'LECTURA_Y_ESCRITURA', 'Hoja1', 'k',"
                    " now(), now())"
                ),
                {"id": uuid.uuid4(), "empresa": empresa_id},
            )


async def test_un_vinculo_de_google_sin_identificador_es_rechazado_por_el_motor(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`ck_vinculo_origen_completo`: cada proveedor trae con qué encontrar su documento."""
    empresa_id = await _empresa(engine_dueno)

    with pytest.raises((IntegrityError, DBAPIError)):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text(
                    "INSERT INTO vinculo_de_planilla "
                    "(id, empresa_id, proveedor, direccion, hoja_empresa, created_at, updated_at) "
                    "VALUES (:id, :empresa, 'GOOGLE_SHEETS', 'SOLO_LECTURA', 'Hoja1',"
                    " now(), now())"
                ),
                {"id": uuid.uuid4(), "empresa": empresa_id},
            )


async def test_desvincular_borra_la_fila(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`DELETE` está otorgado acá, a diferencia de la bitácora y de `tarea_asincrona`.

    Desvincular no destruye nada que ADR-007 proteja: los `Cliente` y `Servicio` ya
    ingeridos siguen enteros. Lo que desaparece es la conexión, no la historia.
    """
    empresa_id = await _empresa(engine_dueno)
    vinculo = _vinculo(
        empresa_id,
        proveedor=ProveedorPlanilla.ARCHIVO,
        identificador_externo=None,
        archivo=ReferenciaDeArchivo(
            clave="planillas/x/y.xlsx", nombre_original="clientes.xlsx", tamano_bytes=10
        ),
    )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioVinculoPostgres(sesion).agregar(vinculo)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioVinculoPostgres(sesion).eliminar(vinculo.id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        assert await RepositorioVinculoPostgres(sesion).buscar_por_id(vinculo.id) is None


async def test_la_pausa_sobrevive_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-04. Una pausa que no se guarda termina en el próximo reinicio del worker."""
    empresa_id = await _empresa(engine_dueno)
    vinculo = _vinculo(empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioVinculoPostgres(sesion).agregar(vinculo)

    vinculo.pausar(motivo="La estructura de la planilla cambio", ahora=datetime.now(UTC))
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioVinculoPostgres(sesion).actualizar(vinculo)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        recuperado = await RepositorioVinculoPostgres(sesion).buscar_por_id(vinculo.id)

    assert recuperado is not None
    assert recuperado.pausado
    assert recuperado.motivo_de_pausa == "La estructura de la planilla cambio"
    assert not recuperado.admite_sincronizacion_incremental
