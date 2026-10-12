"""El mapeo y sus entradas contra el motor que las relaciona (HU-E3-01, HU-E3-02).

Una sola cosa vive acá, y es la que un doble no puede probar: **que las entradas se
escriban después del mapeo del que cuelgan**.

`entrada_de_mapeo.mapeo_id` es una clave foránea, pero las dos clases ORM no declaran un
`relationship()` entre sí. Sin esa declaración, la unidad de trabajo de SQLAlchemy no
conoce la dependencia y ordena los `INSERT` por mapper: con un solo `flush` las entradas
salían primero y PostgreSQL rechazaba el lote entero. En un repositorio falso —un `dict` en
memoria— el orden no significa nada y el defecto no existe.

El defecto era real y llegó a producirse: `POST /planillas/mapeos` devolvía 500 con
`ForeignKeyViolationError`. No lo agarró nadie antes porque **ninguna pantalla llamaba a
ese endpoint** — la revisión de mapeo estaba escrita pero no tenía ruta que la montara.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import EntradaDeMapeo, Mapeo
from cheatsheet.contexts.spreadsheet_sync.infrastructure.repositories import (
    RepositorioMapeoPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _mapeo(empresa_id: EmpresaId, columnas: tuple[str, ...]) -> Mapeo:
    ahora = datetime.now(UTC)
    return Mapeo(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        huella_encabezado=uuid.uuid4().hex,
        entradas=[
            EntradaDeMapeo(
                id=uuid.uuid4(),
                columna_origen=columna,
                atributo_destino=None,
                score=Decimal("0.4"),
                ejemplo="Ferretería Ñandú SRL",
            )
            for columna in columnas
        ],
        created_at=ahora,
        updated_at=ahora,
    )


async def test_un_mapeo_nuevo_guarda_sus_entradas_sin_violar_la_clave_foranea(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El caso que rompía: seis columnas insertadas en el mismo `agregar`.

    Se prueba con varias columnas a propósito. El `INSERT` de las entradas es un
    `executemany`, y con una sola fila un motor podría ordenarlas por casualidad.
    """
    empresa_id = await _empresa(engine_dueno)
    mapeo = _mapeo(empresa_id, ("Razon Soc.", "N° de CUIT", "Mail", "Cel", "Cond. IVA"))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioMapeoPostgres(sesion).agregar(mapeo)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        recuperado = await RepositorioMapeoPostgres(sesion).buscar_por_id(mapeo.id)

    assert recuperado is not None
    assert [e.columna_origen for e in recuperado.entradas] == [
        "Cel",
        "Cond. IVA",
        "Mail",
        "N° de CUIT",
        "Razon Soc.",
    ]
    # El ejemplo viaja a la pantalla y nunca al modelo (D12); que sobreviva a la ida y
    # vuelta es lo que hace que la revisión pueda mostrarlo.
    assert all(e.ejemplo == "Ferretería Ñandú SRL" for e in recuperado.entradas)


async def test_corregir_una_columna_de_un_mapeo_ya_guardado_no_duplica_la_clave(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El defecto era real: `actualizar` borraba las entradas con un `delete()` de Core,
    que no sincroniza de forma confiable los objetos que la sesión ya tenía cargados —
    `buscar_por_id` siempre corre antes y los carga. Al recrearlas con el mismo `id`,
    PostgreSQL rechazaba el lote con `UniqueViolationError` sobre `entrada_de_mapeo_pkey`.
    Un repositorio falso no lo atrapa: el mapa de identidad es cosa de SQLAlchemy.
    """
    empresa_id = await _empresa(engine_dueno)
    mapeo = _mapeo(empresa_id, ("N° de CUIT", "Razon Soc."))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioMapeoPostgres(sesion).agregar(mapeo)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioMapeoPostgres(sesion)
        recuperado = await repo.buscar_por_id(mapeo.id)
        assert recuperado is not None
        recuperado.entrada_de("N° de CUIT").asignar("cuit")
        await repo.actualizar(recuperado)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioMapeoPostgres(sesion)
        recuperado = await repo.buscar_por_id(mapeo.id)
        assert recuperado is not None
        recuperado.entrada_de("Razon Soc.").asignar("nombre")
        await repo.actualizar(recuperado)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        final = await RepositorioMapeoPostgres(sesion).buscar_por_id(mapeo.id)

    assert final is not None
    assert final.entrada_de("N° de CUIT").atributo_destino == "cuit"
    assert final.entrada_de("Razon Soc.").atributo_destino == "nombre"


async def test_una_empresa_no_ve_el_mapeo_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La barrera es de PostgreSQL. Un doble que filtra en Python probaría el doble."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    mapeo = _mapeo(empresa_a, ("Razon Soc.",))

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        await RepositorioMapeoPostgres(sesion).agregar(mapeo)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        repo = RepositorioMapeoPostgres(sesion)
        assert await repo.buscar_por_id(mapeo.id) is None
        assert await repo.buscar_por_huella(mapeo.huella_encabezado) is None
