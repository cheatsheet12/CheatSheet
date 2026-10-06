"""El catálogo de clientes contra el motor que lo hace cumplir.

Tres cosas de esta unidad no se pueden probar con un doble, y son justamente las tres que
importan si algún día salen mal:

1. **El aislamiento entre empresas.** Es una política de PostgreSQL. Un doble que filtra
   por `empresa_id` en Python probaría el doble, no la barrera.
2. **El índice único parcial.** Que dos clientes sin CUIT convivan y dos con el mismo CUIT
   no, es una decisión del índice — y `WHERE cuit IS NOT NULL` es el detalle que la hace
   cierta.
3. **Que no haya `DELETE`.** El `GRANT` de la migración 0008 no lo incluye, a propósito.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.master_data.application.errors import ClienteDuplicado
from cheatsheet.contexts.master_data.domain.cliente import Cliente, FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.valores import OrigenDato
from cheatsheet.contexts.master_data.infrastructure.repositories import (
    RepositorioClientePostgres,
)
from cheatsheet.contexts.payments.infrastructure.clientes import ClienteViaMasterData
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.contacto import Email, Telefono
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CUIT, CondicionIVA
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CUIT_VALIDO = "30712345671"
OTRO_CUIT = "20123456786"

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    """La fila de `empresa` que exige la FK, creada con el rol dueño.

    El alta real de una empresa es de `identity` y pasa por su propio caso de uso; acá
    sólo hace falta que la clave foránea tenga a dónde apuntar.
    """
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _cliente(empresa_id: EmpresaId, *, nombre: str, cuit: str | None = None) -> Cliente:
    ahora = datetime.now(UTC)
    return Cliente.registrar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre=nombre,
        origen=OrigenDato.PANEL,
        momento=ahora,
        cuit=CUIT(cuit) if cuit else None,
    )


async def _guardar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, cliente: Cliente
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioClientePostgres(sesion).agregar(cliente)


@pytest.mark.asyncio
async def test_una_empresa_no_ve_los_clientes_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La garantía que las otras once tablas con `empresa_id` van a heredar."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    await _guardar(sesiones, empresa_a, _cliente(empresa_a, nombre="De la A"))
    await _guardar(sesiones, empresa_b, _cliente(empresa_b, nombre="De la B"))

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        encontrados, total = await RepositorioClientePostgres(sesion).listar(
            empresa_id=empresa_a, filtros=FiltrosDeCliente(), pagina=Pagina()
        )

    assert total == 1
    assert [c.nombre for c in encontrados] == ["De la A"]


@pytest.mark.asyncio
async def test_no_se_puede_leer_un_cliente_ajeno_ni_por_id(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Conocer el id no alcanza: la política filtra también el `SELECT` puntual."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    ajeno = _cliente(empresa_b, nombre="De la B")
    await _guardar(sesiones, empresa_b, ajeno)

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        encontrado = await RepositorioClientePostgres(sesion).buscar_por_id(ajeno.id)

    assert encontrado is None


@pytest.mark.asyncio
async def test_sin_empresa_declarada_no_se_ve_nada(
    sesiones: async_sessionmaker[AsyncSession],
    engine_dueno: AsyncEngine,
    engine_aplicacion: AsyncEngine,
) -> None:
    """La falla es cerrada: olvidarse de declarar la empresa esconde filas, no las expone."""
    empresa_id = await _empresa(engine_dueno)
    await _guardar(sesiones, empresa_id, _cliente(empresa_id, nombre="Invisible"))

    async with engine_aplicacion.connect() as conexion:
        filas = (await conexion.execute(text("SELECT * FROM cliente"))).all()

    assert filas == []


@pytest.mark.asyncio
async def test_no_se_puede_escribir_un_cliente_de_otra_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`WITH CHECK`: anunciar una empresa y escribir la fila de otra se rechaza."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    with pytest.raises(ProgrammingError):
        await _guardar(sesiones, empresa_a, _cliente(empresa_b, nombre="Intento cruzado"))


@pytest.mark.asyncio
async def test_el_mismo_cuit_en_dos_empresas_distintas_es_valido(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-03 es por empresa: dos negocios pueden facturarle al mismo cliente."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    await _guardar(sesiones, empresa_a, _cliente(empresa_a, nombre="Rosa", cuit=CUIT_VALIDO))
    await _guardar(sesiones, empresa_b, _cliente(empresa_b, nombre="Rosa", cuit=CUIT_VALIDO))

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        _, total = await RepositorioClientePostgres(sesion).listar(
            empresa_id=empresa_b, filtros=FiltrosDeCliente(), pagina=Pagina()
        )
    assert total == 1


@pytest.mark.asyncio
async def test_el_mismo_cuit_en_la_misma_empresa_nombra_al_existente(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    primero = _cliente(empresa_id, nombre="Rosa", cuit=CUIT_VALIDO)
    await _guardar(sesiones, empresa_id, primero)

    with pytest.raises(ClienteDuplicado) as error:
        await _guardar(
            sesiones, empresa_id, _cliente(empresa_id, nombre="Rosa 2", cuit=CUIT_VALIDO)
        )

    assert error.value.cliente_existente_id == primero.id


@pytest.mark.asyncio
async def test_varios_clientes_sin_cuit_conviven(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El `WHERE cuit IS NOT NULL` del índice, que es la razón de que sea parcial."""
    empresa_id = await _empresa(engine_dueno)

    for nombre in ("Uno", "Otro", "Un tercero"):
        await _guardar(sesiones, empresa_id, _cliente(empresa_id, nombre=nombre))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        _, total = await RepositorioClientePostgres(sesion).listar(
            empresa_id=empresa_id, filtros=FiltrosDeCliente(), pagina=Pagina()
        )
    assert total == 3


@pytest.mark.asyncio
async def test_la_aplicacion_no_tiene_permiso_para_borrar_clientes(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La migración 0008 concede SELECT, INSERT y UPDATE. `DELETE` no está, a propósito."""
    empresa_id = await _empresa(engine_dueno)
    await _guardar(sesiones, empresa_id, _cliente(empresa_id, nombre="Rosa"))

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(text("DELETE FROM cliente"))


@pytest.mark.asyncio
async def test_ida_y_vuelta_de_todos_los_campos(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Que los value objects sobrevivan al viaje: un mapeo mal hecho se ve acá."""
    empresa_id = await _empresa(engine_dueno)
    ahora = datetime.now(UTC)
    cliente = Cliente.registrar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre="Panaderia Dona Rosa",
        origen=OrigenDato.PANEL,
        momento=ahora,
        cuit=CUIT(OTRO_CUIT),
        condicion_iva=CondicionIVA.MONOTRIBUTO,
        contacto_whatsapp=Telefono("+54 9 11 1234-5678"),
        contacto_email=Email("rosa@panaderia.com"),
    )
    await _guardar(sesiones, empresa_id, cliente)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioClientePostgres(sesion).buscar_por_id(cliente.id)

    assert leido is not None
    assert leido.nombre == "Panaderia Dona Rosa"
    assert leido.cuit == CUIT(OTRO_CUIT)
    assert leido.condicion_iva is CondicionIVA.MONOTRIBUTO
    assert leido.contacto_whatsapp == Telefono("5491112345678")
    assert leido.contacto_email == Email("rosa@panaderia.com")
    assert leido.origen is OrigenDato.PANEL
    assert leido.presente_en_planilla is False
    assert leido.activo is True


@pytest.mark.asyncio
async def test_desactivar_persiste_y_no_borra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente = _cliente(empresa_id, nombre="Rosa")
    await _guardar(sesiones, empresa_id, cliente)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repositorio = RepositorioClientePostgres(sesion)
        cargado = await repositorio.buscar_por_id(cliente.id)
        assert cargado is not None
        cargado.desactivar(datetime.now(UTC))
        await repositorio.guardar(cargado)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repositorio = RepositorioClientePostgres(sesion)
        leido = await repositorio.buscar_por_id(cliente.id)
        _, activos = await repositorio.listar(
            empresa_id=empresa_id, filtros=FiltrosDeCliente(solo_activos=True), pagina=Pagina()
        )

    assert leido is not None
    assert leido.activo is False
    assert activos == 0


@pytest.mark.asyncio
async def test_un_cliente_de_otra_empresa_no_es_valido_para_un_cobro(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """D92 con RLS de verdad: el ACL de `payments` ve `False`, no el id de un cliente ajeno."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    propio = _cliente(empresa_a, nombre="De la A")
    ajeno = _cliente(empresa_b, nombre="De la B")
    await _guardar(sesiones, empresa_a, propio)
    await _guardar(sesiones, empresa_b, ajeno)

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        acl = ClienteViaMasterData(RepositorioClientePostgres(sesion))
        propio_activo = await acl.esta_activo(propio.id)
        ajeno_activo = await acl.esta_activo(ajeno.id)

    assert propio_activo is True
    assert ajeno_activo is False


@pytest.mark.asyncio
async def test_el_cuit_formateado_de_la_pantalla_encuentra_al_cliente(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """H3: la columna guarda `30712345671` y la API muestra `30-71234567-1`. Quien copia el
    CUIT de la pantalla y lo pega en el buscador tiene que encontrarlo."""
    empresa = await _empresa(engine_dueno)
    await _guardar(sesiones, empresa, _cliente(empresa, nombre="Panaderia", cuit=CUIT_VALIDO))
    await _guardar(sesiones, empresa, _cliente(empresa, nombre="Ferreteria", cuit=OTRO_CUIT))

    async with sesion_de_empresa(sesiones, empresa) as sesion:
        repositorio = RepositorioClientePostgres(sesion)
        formateado, _ = await repositorio.listar(
            empresa_id=empresa, filtros=FiltrosDeCliente(texto="30-71234567-1"), pagina=Pagina()
        )
        parcial, _ = await repositorio.listar(
            empresa_id=empresa, filtros=FiltrosDeCliente(texto="30-7123"), pagina=Pagina()
        )
        por_nombre, _ = await repositorio.listar(
            empresa_id=empresa, filtros=FiltrosDeCliente(texto="ferre"), pagina=Pagina()
        )

    assert [c.nombre for c in formateado] == ["Panaderia"]
    assert [c.nombre for c in parcial] == ["Panaderia"]
    assert [c.nombre for c in por_nombre] == ["Ferreteria"]
