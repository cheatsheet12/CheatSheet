"""El catálogo de servicios contra el motor que lo hace cumplir.

Tres cosas que un doble no puede probar, y una de ellas es nueva en el sistema:

1. **El aislamiento entre empresas**, que es una política de PostgreSQL.
2. **Que la aplicación no tenga `DELETE`**, que es un `GRANT` de la migración 0009.
3. **Que `0.105` sobreviva el viaje**, que es la escala de la columna. Con
   `NUMERIC(5, 2)` la base la redondearía a `0.11` sin decir nada, y el IVA reducido del
   épico 5 saldría mal en cada línea. Es el test que justifica la escala 4.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from cheatsheet.contexts.master_data.domain.cliente import Pagina
from cheatsheet.contexts.master_data.domain.servicio import FiltrosDeServicio, Servicio
from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.contexts.master_data.infrastructure.repositories import (
    RepositorioServicioPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _servicio(
    empresa_id: EmpresaId,
    *,
    nombre: str = "Corte de pelo",
    precio: str = "5000.00",
    alicuota: AlicuotaIVA = AlicuotaIVA.GENERAL,
    agendable: bool = False,
    duracion: int | None = None,
) -> Servicio:
    return Servicio.registrar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre=nombre,
        precio=Decimal(precio),
        alicuota_iva=alicuota,
        origen=OrigenDato.PANEL,
        momento=datetime.now(UTC),
        agendable=agendable,
        duracion_estandar_min=duracion,
    )


async def _guardar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, servicio: Servicio
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioServicioPostgres(sesion).agregar(servicio)


@pytest.mark.asyncio
async def test_una_empresa_no_ve_los_servicios_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    await _guardar(sesiones, empresa_a, _servicio(empresa_a, nombre="De la A"))
    await _guardar(sesiones, empresa_b, _servicio(empresa_b, nombre="De la B"))

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        encontrados, total = await RepositorioServicioPostgres(sesion).listar(
            empresa_id=empresa_a, filtros=FiltrosDeServicio(), pagina=Pagina()
        )

    assert total == 1
    assert [s.nombre for s in encontrados] == ["De la A"]


@pytest.mark.asyncio
async def test_no_se_puede_leer_un_servicio_ajeno_ni_por_id(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    ajeno = _servicio(empresa_b, nombre="De la B")
    await _guardar(sesiones, empresa_b, ajeno)

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        encontrado = await RepositorioServicioPostgres(sesion).buscar_por_id(ajeno.id)

    assert encontrado is None


@pytest.mark.asyncio
async def test_no_se_puede_escribir_un_servicio_de_otra_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`WITH CHECK`, igual que en `cliente`."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    with pytest.raises(ProgrammingError):
        await _guardar(sesiones, empresa_a, _servicio(empresa_b, nombre="Intento cruzado"))


@pytest.mark.asyncio
async def test_la_aplicacion_no_tiene_permiso_para_borrar_servicios(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-04 en el `GRANT`: desactivar no es borrar, y borrar no está disponible."""
    empresa_id = await _empresa(engine_dueno)
    await _guardar(sesiones, empresa_id, _servicio(empresa_id))

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(text("DELETE FROM servicio"))


@pytest.mark.asyncio
async def test_la_alicuota_reducida_sobrevive_el_viaje(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El test que justifica `NUMERIC(5, 4)`.

    Con escala 2 la base guardaría `0.11` sin avisar, y todas las líneas de IVA reducido
    del épico 5 saldrían mal. Se comprueba también contra la columna cruda, porque el
    agregado podría estar tapando el error al reconstruir el enum.
    """
    empresa_id = await _empresa(engine_dueno)
    servicio = _servicio(empresa_id, alicuota=AlicuotaIVA.REDUCIDA)
    await _guardar(sesiones, empresa_id, servicio)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioServicioPostgres(sesion).buscar_por_id(servicio.id)
        crudo = await sesion.scalar(
            text("SELECT alicuota_iva FROM servicio WHERE id = :id"), {"id": servicio.id}
        )

    assert leido is not None
    assert leido.alicuota_iva is AlicuotaIVA.REDUCIDA
    assert crudo == Decimal("0.105")


@pytest.mark.asyncio
async def test_el_precio_se_guarda_con_dos_decimales_exactos(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`NUMERIC`, no `FLOAT`: el número que vuelve es el mismo que se guardó."""
    empresa_id = await _empresa(engine_dueno)
    servicio = _servicio(empresa_id, precio="19999.99")
    await _guardar(sesiones, empresa_id, servicio)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioServicioPostgres(sesion).buscar_por_id(servicio.id)

    assert leido is not None
    assert leido.precio == Decimal("19999.99")
    assert isinstance(leido.precio, Decimal)


@pytest.mark.asyncio
async def test_ida_y_vuelta_de_todos_los_campos(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    servicio = _servicio(
        empresa_id,
        nombre="Coloracion completa",
        precio="12500.50",
        alicuota=AlicuotaIVA.CERO,
        agendable=True,
        duracion=90,
    )
    await _guardar(sesiones, empresa_id, servicio)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioServicioPostgres(sesion).buscar_por_id(servicio.id)

    assert leido is not None
    assert leido.nombre == "Coloracion completa"
    assert leido.precio == Decimal("12500.50")
    assert leido.alicuota_iva is AlicuotaIVA.CERO
    assert leido.agendable is True
    assert leido.duracion_estandar_min == 90
    assert leido.origen is OrigenDato.PANEL
    assert leido.presente_en_planilla is False
    assert leido.activo is True


@pytest.mark.asyncio
async def test_desactivar_persiste_y_no_borra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    servicio = _servicio(empresa_id)
    await _guardar(sesiones, empresa_id, servicio)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repositorio = RepositorioServicioPostgres(sesion)
        cargado = await repositorio.buscar_por_id(servicio.id)
        assert cargado is not None
        cargado.desactivar(datetime.now(UTC))
        await repositorio.guardar(cargado)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repositorio = RepositorioServicioPostgres(sesion)
        leido = await repositorio.buscar_por_id(servicio.id)
        _, activos = await repositorio.listar(
            empresa_id=empresa_id, filtros=FiltrosDeServicio(solo_activos=True), pagina=Pagina()
        )

    assert leido is not None
    assert leido.activo is False
    assert activos == 0


@pytest.mark.asyncio
async def test_dos_servicios_con_el_mismo_nombre_conviven(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """No hay unicidad de nombre, y no es un olvido: dos sucursales venden el mismo corte."""
    empresa_id = await _empresa(engine_dueno)

    await _guardar(sesiones, empresa_id, _servicio(empresa_id, nombre="Corte"))
    await _guardar(sesiones, empresa_id, _servicio(empresa_id, nombre="Corte", precio="6000"))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        _, total = await RepositorioServicioPostgres(sesion).listar(
            empresa_id=empresa_id, filtros=FiltrosDeServicio(), pagina=Pagina()
        )
    assert total == 2
