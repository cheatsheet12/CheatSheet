"""Categorías y clasificación contra el motor que las hace cumplir.

Cuatro cosas viven acá porque en un doble no significarían nada:

1. **El aislamiento**, en las tres tablas nuevas.
2. **Que no se pueda clasificar con una categoría de otra empresa.** Es el caso más
   interesante del archivo: la clave foránea **no** lo impide —se verifica con permisos del
   dueño y ve filas que la RLS esconde— y lo que lo impide es que el `SELECT` previo del
   caso de uso sí pasa por la política.
3. **El índice único funcional** sobre `lower(nombre)`: que «VIP» y «vip» choquen es una
   decisión de la base, no del Python.
4. **El `ON DELETE CASCADE`**, que es RN-03 hecho esquema, y el `GRANT` de `DELETE` que
   esta tabla tiene y las otras dos no.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from cheatsheet.contexts.master_data.domain.categoria import CategoriaEmpresa
from cheatsheet.contexts.master_data.domain.cliente import Cliente, FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.servicio import Servicio
from cheatsheet.contexts.master_data.domain.valores import (
    AlicuotaIVA,
    AmbitoDeCategoria,
    OrigenDato,
)
from cheatsheet.contexts.master_data.infrastructure.categorias import (
    ClasificacionesPostgres,
    RepositorioCategoriaPostgres,
)
from cheatsheet.contexts.master_data.infrastructure.repositories import (
    RepositorioClientePostgres,
    RepositorioServicioPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _categoria(
    empresa_id: EmpresaId,
    *,
    nombre: str = "VIP",
    aplica_a: AmbitoDeCategoria = AmbitoDeCategoria.AMBOS,
) -> CategoriaEmpresa:
    return CategoriaEmpresa.registrar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre=nombre,
        aplica_a=aplica_a,
        momento=datetime.now(UTC),
    )


def _cliente(empresa_id: EmpresaId, *, nombre: str = "Panaderia") -> Cliente:
    return Cliente.registrar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre=nombre,
        origen=OrigenDato.PANEL,
        momento=datetime.now(UTC),
    )


def _servicio(empresa_id: EmpresaId) -> Servicio:
    return Servicio.registrar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre="Corte de pelo",
        precio=Decimal("5000.00"),
        alicuota_iva=AlicuotaIVA.GENERAL,
        origen=OrigenDato.PANEL,
        momento=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_una_empresa_no_ve_las_categorias_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        await RepositorioCategoriaPostgres(sesion).agregar(_categoria(empresa_a, nombre="De la A"))
    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        await RepositorioCategoriaPostgres(sesion).agregar(_categoria(empresa_b, nombre="De la B"))

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        encontradas = await RepositorioCategoriaPostgres(sesion).listar(empresa_id=empresa_a)

    assert [c.nombre for c in encontradas] == ["De la A"]


@pytest.mark.asyncio
async def test_no_se_puede_clasificar_con_una_categoria_de_otra_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El caso que la clave foránea **no** impide.

    Una FK se verifica con los permisos del dueño de la tabla, así que ve la categoría de
    la empresa B aunque la RLS la esconda. Lo que lo impide es que el caso de uso la lee
    antes por el repositorio, y ese `SELECT` sí pasa por la política: desde la empresa A,
    la categoría ajena simplemente no existe.
    """
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    ajena = _categoria(empresa_b, nombre="De la B")
    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        await RepositorioCategoriaPostgres(sesion).agregar(ajena)

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        encontrada = await RepositorioCategoriaPostgres(sesion).buscar_por_id(ajena.id)

    assert encontrada is None


@pytest.mark.asyncio
async def test_el_enlace_de_otra_empresa_tampoco_se_puede_escribir(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Y si alguien saltara el caso de uso, la política `WITH CHECK` del enlace lo frena."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    cliente = _cliente(empresa_a)
    ajena = _categoria(empresa_b)
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        await RepositorioClientePostgres(sesion).agregar(cliente)
    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        await RepositorioCategoriaPostgres(sesion).agregar(ajena)

    with pytest.raises((ProgrammingError, IntegrityError)):
        async with sesion_de_empresa(sesiones, empresa_a) as sesion:
            await sesion.execute(
                text(
                    "INSERT INTO cliente_categoria (cliente_id, categoria_id, empresa_id) "
                    "VALUES (:cliente, :categoria, :empresa)"
                ),
                {"cliente": cliente.id, "categoria": ajena.id, "empresa": empresa_b},
            )


@pytest.mark.asyncio
async def test_el_indice_unico_ignora_mayusculas(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-02 en la base, y con `lower(nombre)` — que es lo que el repositorio también compara."""
    empresa_id = await _empresa(engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioCategoriaPostgres(sesion).agregar(_categoria(empresa_id, nombre="VIP"))

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioCategoriaPostgres(sesion).agregar(_categoria(empresa_id, nombre="vip"))


@pytest.mark.asyncio
async def test_el_mismo_nombre_en_otro_ambito_si_entra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repositorio = RepositorioCategoriaPostgres(sesion)
        await repositorio.agregar(
            _categoria(empresa_id, nombre="VIP", aplica_a=AmbitoDeCategoria.CLIENTE)
        )
        await repositorio.agregar(
            _categoria(empresa_id, nombre="VIP", aplica_a=AmbitoDeCategoria.SERVICIO)
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        assert len(await RepositorioCategoriaPostgres(sesion).listar(empresa_id=empresa_id)) == 2


@pytest.mark.asyncio
async def test_asignar_dos_veces_deja_una_sola_fila(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La clave primaria compuesta más `ON CONFLICT DO NOTHING`: idempotencia en la base."""
    empresa_id = await _empresa(engine_dueno)
    cliente = _cliente(empresa_id)
    categoria = _categoria(empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioClientePostgres(sesion).agregar(cliente)
        await RepositorioCategoriaPostgres(sesion).agregar(categoria)
        clasificaciones = ClasificacionesPostgres(sesion)
        for _ in range(2):
            await clasificaciones.asignar_a_cliente(
                cliente_id=cliente.id, categoria_id=categoria.id
            )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        filas = await sesion.scalar(text("SELECT count(*) FROM cliente_categoria"))

    assert filas == 1


@pytest.mark.asyncio
async def test_eliminar_una_categoria_desclasifica_y_no_toca_al_cliente(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-03 completa: el cliente pierde la etiqueta y conserva todo lo demás."""
    empresa_id = await _empresa(engine_dueno)
    cliente = _cliente(empresa_id, nombre="Panaderia Dona Rosa")
    categoria = _categoria(empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioClientePostgres(sesion).agregar(cliente)
        await RepositorioCategoriaPostgres(sesion).agregar(categoria)
        await ClasificacionesPostgres(sesion).asignar_a_cliente(
            cliente_id=cliente.id, categoria_id=categoria.id
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioCategoriaPostgres(sesion).eliminar(categoria.id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        vivo = await RepositorioClientePostgres(sesion).buscar_por_id(cliente.id)
        sin_categorias = await ClasificacionesPostgres(sesion).categorias_de_cliente(cliente.id)
        enlaces = await sesion.scalar(text("SELECT count(*) FROM cliente_categoria"))

    assert vivo is not None
    assert vivo.nombre == "Panaderia Dona Rosa"
    assert list(sin_categorias) == []
    assert enlaces == 0


@pytest.mark.asyncio
async def test_renombrar_alcanza_a_los_elementos_clasificados(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El tercer criterio de HU-E4-03, que sale gratis de normalizar."""
    empresa_id = await _empresa(engine_dueno)
    cliente = _cliente(empresa_id)
    categoria = _categoria(empresa_id, nombre="VIP")

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioClientePostgres(sesion).agregar(cliente)
        await RepositorioCategoriaPostgres(sesion).agregar(categoria)
        await ClasificacionesPostgres(sesion).asignar_a_cliente(
            cliente_id=cliente.id, categoria_id=categoria.id
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repositorio = RepositorioCategoriaPostgres(sesion)
        cargada = await repositorio.buscar_por_id(categoria.id)
        assert cargada is not None
        cargada.renombrar("Clientes preferenciales")
        await repositorio.guardar(cargada)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        del_cliente = await ClasificacionesPostgres(sesion).categorias_de_cliente(cliente.id)

    assert [c.nombre for c in del_cliente] == ["Clientes preferenciales"]


@pytest.mark.asyncio
async def test_los_dos_listados_filtran_por_categoria(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """«El cliente queda clasificado y es filtrable por esa categoria» (HU-E4-04)."""
    empresa_id = await _empresa(engine_dueno)
    con_etiqueta = _cliente(empresa_id, nombre="Con etiqueta")
    sin_etiqueta = _cliente(empresa_id, nombre="Sin etiqueta")
    categoria = _categoria(empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        clientes = RepositorioClientePostgres(sesion)
        await clientes.agregar(con_etiqueta)
        await clientes.agregar(sin_etiqueta)
        await RepositorioCategoriaPostgres(sesion).agregar(categoria)
        await ClasificacionesPostgres(sesion).asignar_a_cliente(
            cliente_id=con_etiqueta.id, categoria_id=categoria.id
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        encontrados, total = await RepositorioClientePostgres(sesion).listar(
            empresa_id=empresa_id,
            filtros=FiltrosDeCliente(categoria_id=categoria.id),
            pagina=Pagina(),
        )

    assert total == 1
    assert [c.nombre for c in encontrados] == ["Con etiqueta"]


@pytest.mark.asyncio
async def test_un_servicio_tambien_se_clasifica_y_se_filtra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    servicio = _servicio(empresa_id)
    categoria = _categoria(empresa_id, aplica_a=AmbitoDeCategoria.SERVICIO)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioServicioPostgres(sesion).agregar(servicio)
        await RepositorioCategoriaPostgres(sesion).agregar(categoria)
        await ClasificacionesPostgres(sesion).asignar_a_servicio(
            servicio_id=servicio.id, categoria_id=categoria.id
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        del_servicio = await ClasificacionesPostgres(sesion).categorias_de_servicio(servicio.id)

    assert [c.nombre for c in del_servicio] == ["Vip"]


@pytest.mark.asyncio
async def test_la_aplicacion_puede_borrar_categorias_y_sigue_sin_poder_borrar_clientes(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La asimetría de los `GRANT`, comprobada en el mismo test para que se lea junta."""
    empresa_id = await _empresa(engine_dueno)
    cliente = _cliente(empresa_id)
    categoria = _categoria(empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioClientePostgres(sesion).agregar(cliente)
        await RepositorioCategoriaPostgres(sesion).agregar(categoria)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await sesion.execute(text("DELETE FROM categoria_empresa"))

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(text("DELETE FROM cliente"))
