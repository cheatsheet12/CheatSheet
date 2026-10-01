"""La normalización de nombres contra el motor — HU-E4-05 y HU-E3-04 RN-04.

Dos cosas no se pueden probar con un doble:

1. **El índice único funcional de categoría** (`lower(nombre)`) sobre nombres que ya salen
   normalizados del agregado: «VIP» y «Vip» son el mismo nombre para la base, y dos empresas
   pueden tener «Vip» cada una (RLS). El índice **no cambia** en esta unidad.
2. **Que reingerir lo mismo no toque la fila**: `updated_at` queda igual en la base, que es
   lo que impide que el write-back vuelva a empujar un registro que no cambió.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cheatsheet.contexts.master_data.application.ingesta import (
    FilaDeCatalogo,
    IngerirClienteDesdePlanilla,
)
from cheatsheet.contexts.master_data.domain.categoria import CategoriaEmpresa
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.contexts.master_data.infrastructure.categorias import RepositorioCategoriaPostgres
from cheatsheet.contexts.master_data.infrastructure.repositories import RepositorioClientePostgres
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CUIT_VALIDO = "30712345671"
CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _categoria(empresa_id: EmpresaId, nombre: str) -> CategoriaEmpresa:
    return CategoriaEmpresa.registrar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre=nombre,
        aplica_a=AmbitoDeCategoria.CLIENTE,
        momento=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_vip_y_vip_chocan_en_el_indice_real(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioCategoriaPostgres(sesion).agregar(_categoria(empresa_id, "Vip"))

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioCategoriaPostgres(sesion).agregar(_categoria(empresa_id, "VIP"))


@pytest.mark.asyncio
async def test_dos_empresas_pueden_tener_vip_cada_una(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    for empresa_id in (empresa_a, empresa_b):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioCategoriaPostgres(sesion).agregar(_categoria(empresa_id, "VIP"))

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        propias = await RepositorioCategoriaPostgres(sesion).listar(empresa_id=empresa_a)
    assert [c.nombre for c in propias] == ["Vip"]


@pytest.mark.asyncio
async def test_reingerir_con_solo_diferencias_de_mayusculas_no_toca_la_fila(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    momento = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

    async def ingerir(nombre: str, ahora: datetime) -> None:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await IngerirClienteDesdePlanilla(RepositorioClientePostgres(sesion)).ejecutar(
                empresa_id=empresa_id,
                fila=FilaDeCatalogo(nombre=nombre, cuit=CUIT_VALIDO),
                ahora=ahora,
            )

    await ingerir("Maria Gomez", momento)
    await ingerir("MARIA GOMEZ", momento + timedelta(days=1))
    await ingerir("maria  gomez ", momento + timedelta(days=2))

    async with engine_dueno.connect() as conexion:
        fila = (
            await conexion.execute(
                text("SELECT nombre, updated_at FROM cliente WHERE empresa_id = :e"),
                {"e": empresa_id},
            )
        ).one()
    assert fila.nombre == "Maria Gomez"
    assert fila.updated_at == momento
