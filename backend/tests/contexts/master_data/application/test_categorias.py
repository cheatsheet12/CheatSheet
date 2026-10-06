"""Los casos de uso de categorías y clasificación — HU-E4-03 y HU-E4-04.

Dos cosas se prueban con más insistencia que el resto:

- **RN-02**, la unicidad por nombre y ámbito, incluida la parte que no está escrita en la
  historia y sí en el plan: que ignore mayúsculas, y que el mismo nombre en **otro** ámbito
  sí se pueda;
- **RN-01 de HU-E4-04**, el ámbito, que es lo único que impide clasificar mal.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.master_data.application.categorias import (
    ACCION_CLASIFICADO,
    ACCION_DESCLASIFICADO,
    ACCION_ELIMINADA,
    ACCION_REGISTRADA,
    ClasificarCliente,
    ClasificarServicio,
    EditarCategoria,
    EliminarCategoria,
    ListarCategorias,
    RegistrarCategoria,
)
from cheatsheet.contexts.master_data.application.errors import (
    CategoriaDuplicada,
    CategoriaNoEncontrada,
    ClienteNoEncontrado,
    PermisoDenegado,
    ServicioNoEncontrado,
)
from cheatsheet.contexts.master_data.domain.categoria import (
    MENSAJE_DUPLICADA,
    AmbitoIncompatible,
    CategoriaEmpresa,
)
from cheatsheet.contexts.master_data.domain.cliente import Cliente
from cheatsheet.contexts.master_data.domain.servicio import Servicio
from cheatsheet.contexts.master_data.domain.valores import (
    AlicuotaIVA,
    AmbitoDeCategoria,
    OrigenDato,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario

from tests.conftest import INSTANTE_FIJO
from tests.contexts.master_data.conftest import (
    ClasificacionesEnMemoria,
    PublicadorFalso,
    RepositorioCategoriaEnMemoria,
    RepositorioClienteEnMemoria,
    RepositorioServicioEnMemoria,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
RELOJ = RelojFijo(INSTANTE_FIJO)


async def _crear(
    categorias: RepositorioCategoriaEnMemoria,
    publicador: PublicadorFalso,
    *,
    nombre: str = "VIP",
    aplica_a: AmbitoDeCategoria = AmbitoDeCategoria.CLIENTE,
    rol: RolUsuario = RolUsuario.OPERADOR,
) -> CategoriaEmpresa:
    return await RegistrarCategoria(
        categorias=categorias, publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        nombre=nombre,
        aplica_a=aplica_a,
    )


async def _editar(
    categorias: RepositorioCategoriaEnMemoria,
    publicador: PublicadorFalso,
    categoria_id: UUID,
    *,
    nombre: str,
    aplica_a: AmbitoDeCategoria,
) -> CategoriaEmpresa:
    return await EditarCategoria(
        categorias=categorias, publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        categoria_id=categoria_id,
        nombre=nombre,
        aplica_a=aplica_a,
    )


async def _cliente(clientes: RepositorioClienteEnMemoria) -> Cliente:
    cliente = Cliente.registrar(
        id=uuid4(),
        empresa_id=EMPRESA,
        nombre="Panaderia Dona Rosa",
        origen=OrigenDato.PANEL,
        momento=INSTANTE_FIJO,
    )
    await clientes.agregar(cliente)
    return cliente


async def _servicio(servicios: RepositorioServicioEnMemoria) -> Servicio:
    servicio = Servicio.registrar(
        id=uuid4(),
        empresa_id=EMPRESA,
        nombre="Corte de pelo",
        precio=Decimal("5000.00"),
        alicuota_iva=AlicuotaIVA.GENERAL,
        origen=OrigenDato.PANEL,
        momento=INSTANTE_FIJO,
    )
    await servicios.agregar(servicio)
    return servicio


def _clasificar_cliente(
    clientes: RepositorioClienteEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> ClasificarCliente:
    return ClasificarCliente(
        clientes=clientes,
        categorias=categorias,
        clasificaciones=clasificaciones,
        publicador=publicador,
        reloj=RELOJ,
    )


def _clasificar_servicio(
    servicios: RepositorioServicioEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> ClasificarServicio:
    return ClasificarServicio(
        servicios=servicios,
        categorias=categorias,
        clasificaciones=clasificaciones,
        publicador=publicador,
        reloj=RELOJ,
    )


# --- RN-02: unicidad por nombre y ámbito ---------------------------------------------


async def test_nombre_duplicado_en_el_mismo_ambito_se_bloquea(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    await _crear(categorias, publicador, nombre="VIP")

    with pytest.raises(CategoriaDuplicada, match=MENSAJE_DUPLICADA):
        await _crear(categorias, publicador, nombre="VIP")


async def test_el_duplicado_ignora_mayusculas(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    """No está en la historia y sí en el plan: dos filas que se ven idénticas son un error."""
    await _crear(categorias, publicador, nombre="VIP")

    with pytest.raises(CategoriaDuplicada):
        await _crear(categorias, publicador, nombre="vip")


async def test_el_mismo_nombre_en_otro_ambito_si_se_puede(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    """RN-02 habla de nombre **y** ámbito, así que esto es correcto por regla.

    Es también la consecuencia que el plan declara y no corrige: las dos son asignables a
    un cliente, así que el combo va a mostrar «VIP» dos veces.
    """
    await _crear(categorias, publicador, nombre="VIP", aplica_a=AmbitoDeCategoria.CLIENTE)
    await _crear(categorias, publicador, nombre="VIP", aplica_a=AmbitoDeCategoria.SERVICIO)

    assert len(categorias.categorias) == 2


async def test_renombrar_a_un_nombre_ocupado_se_bloquea(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    await _crear(categorias, publicador, nombre="VIP")
    otra = await _crear(categorias, publicador, nombre="Mayorista")

    with pytest.raises(CategoriaDuplicada):
        await _editar(
            categorias, publicador, otra.id, nombre="VIP", aplica_a=AmbitoDeCategoria.CLIENTE
        )


async def test_renombrar_a_su_propio_nombre_no_es_un_duplicado(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    """Guardar sin cambiar el nombre tiene que funcionar: el `excepto` del chequeo."""
    categoria = await _crear(categorias, publicador, nombre="VIP")

    editada = await _editar(
        categorias, publicador, categoria.id, nombre="VIP", aplica_a=AmbitoDeCategoria.AMBOS
    )

    assert editada.aplica_a is AmbitoDeCategoria.AMBOS


async def test_editar_una_categoria_que_no_existe(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    with pytest.raises(CategoriaNoEncontrada):
        await _editar(
            categorias, publicador, uuid4(), nombre="VIP", aplica_a=AmbitoDeCategoria.CLIENTE
        )


# --- Listado: filtra por utilidad, no por igualdad ------------------------------------


async def test_listar_para_clientes_incluye_las_de_ambos(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    """Lo que necesita el combo del formulario de cliente, sin que el combo sepa la regla."""
    await _crear(categorias, publicador, nombre="Solo clientes", aplica_a=AmbitoDeCategoria.CLIENTE)
    await _crear(categorias, publicador, nombre="Las dos", aplica_a=AmbitoDeCategoria.AMBOS)
    await _crear(
        categorias, publicador, nombre="Solo servicios", aplica_a=AmbitoDeCategoria.SERVICIO
    )

    para_clientes = await ListarCategorias(categorias=categorias).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.OPERADOR, aplica_a=AmbitoDeCategoria.CLIENTE
    )

    assert [c.nombre for c in para_clientes] == ["Las dos", "Solo clientes"]


async def test_listar_sin_filtro_las_trae_todas(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    await _crear(categorias, publicador, nombre="A")
    await _crear(categorias, publicador, nombre="B", aplica_a=AmbitoDeCategoria.SERVICIO)

    todas = await ListarCategorias(categorias=categorias).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.SOLO_LECTURA
    )

    assert len(todas) == 2


async def test_el_listado_no_cruza_empresas(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    await _crear(categorias, publicador)

    ajenas = await ListarCategorias(categorias=categorias).ejecutar(
        empresa_id=EmpresaId(uuid4()), rol=RolUsuario.OPERADOR
    )

    assert list(ajenas) == []


# --- HU-E4-04: el ámbito manda --------------------------------------------------------


async def test_una_categoria_de_servicios_no_se_asigna_a_un_cliente(
    clientes: RepositorioClienteEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    """RN-01. El caso de uso no repite la regla: se la pide al agregado."""
    cliente = await _cliente(clientes)
    categoria = await _crear(
        categorias, publicador, nombre="Recurrente", aplica_a=AmbitoDeCategoria.SERVICIO
    )

    with pytest.raises(AmbitoIncompatible):
        await _clasificar_cliente(clientes, categorias, clasificaciones, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=cliente.id,
            categoria_id=categoria.id,
            asignar=True,
        )

    assert clasificaciones.de_cliente == {}


async def test_ambos_se_asigna_a_cliente_y_a_servicio(
    clientes: RepositorioClienteEnMemoria,
    servicios: RepositorioServicioEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    cliente = await _cliente(clientes)
    servicio = await _servicio(servicios)
    categoria = await _crear(
        categorias, publicador, nombre="Premium", aplica_a=AmbitoDeCategoria.AMBOS
    )

    del_cliente = await _clasificar_cliente(
        clientes, categorias, clasificaciones, publicador
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente.id,
        categoria_id=categoria.id,
        asignar=True,
    )
    del_servicio = await _clasificar_servicio(
        servicios, categorias, clasificaciones, publicador
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        servicio_id=servicio.id,
        categoria_id=categoria.id,
        asignar=True,
    )

    assert [c.nombre for c in del_cliente] == ["Premium"]
    assert [c.nombre for c in del_servicio] == ["Premium"]


async def test_un_elemento_admite_varias_categorias(
    clientes: RepositorioClienteEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    """RN-02 de HU-E4-04, que es la razón de ser de la decisión D8."""
    cliente = await _cliente(clientes)
    una = await _crear(categorias, publicador, nombre="VIP")
    otra = await _crear(categorias, publicador, nombre="Mayorista")
    clasificar = _clasificar_cliente(clientes, categorias, clasificaciones, publicador)

    await clasificar.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente.id,
        categoria_id=una.id,
        asignar=True,
    )
    resultado = await clasificar.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente.id,
        categoria_id=otra.id,
        asignar=True,
    )

    assert [c.nombre for c in resultado] == ["Mayorista", "Vip"]


async def test_asignar_dos_veces_deja_una_sola(
    clientes: RepositorioClienteEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    """Un click repetido no es un error de negocio (RN-03 de HU-E4-04)."""
    cliente = await _cliente(clientes)
    categoria = await _crear(categorias, publicador)
    clasificar = _clasificar_cliente(clientes, categorias, clasificaciones, publicador)

    for _ in range(2):
        resultado = await clasificar.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=cliente.id,
            categoria_id=categoria.id,
            asignar=True,
        )

    assert len(resultado) == 1


async def test_desasignar_algo_que_no_estaba_no_es_un_error(
    clientes: RepositorioClienteEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    cliente = await _cliente(clientes)
    categoria = await _crear(categorias, publicador)

    resultado = await _clasificar_cliente(
        clientes, categorias, clasificaciones, publicador
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente.id,
        categoria_id=categoria.id,
        asignar=False,
    )

    assert list(resultado) == []


async def test_desasignar_no_revalida_el_ambito(
    clientes: RepositorioClienteEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    """Una clasificación que existe tiene que poder sacarse aunque el ámbito se haya achicado."""
    cliente = await _cliente(clientes)
    categoria = await _crear(
        categorias, publicador, nombre="Premium", aplica_a=AmbitoDeCategoria.AMBOS
    )
    clasificar = _clasificar_cliente(clientes, categorias, clasificaciones, publicador)
    await clasificar.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente.id,
        categoria_id=categoria.id,
        asignar=True,
    )
    await _editar(
        categorias, publicador, categoria.id, nombre="Premium", aplica_a=AmbitoDeCategoria.SERVICIO
    )

    resultado = await clasificar.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente.id,
        categoria_id=categoria.id,
        asignar=False,
    )

    assert list(resultado) == []


async def test_clasificar_un_elemento_que_no_existe(
    clientes: RepositorioClienteEnMemoria,
    servicios: RepositorioServicioEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    categoria = await _crear(categorias, publicador, aplica_a=AmbitoDeCategoria.AMBOS)

    with pytest.raises(ClienteNoEncontrado):
        await _clasificar_cliente(clientes, categorias, clasificaciones, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=uuid4(),
            categoria_id=categoria.id,
            asignar=True,
        )

    with pytest.raises(ServicioNoEncontrado):
        await _clasificar_servicio(servicios, categorias, clasificaciones, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            servicio_id=uuid4(),
            categoria_id=categoria.id,
            asignar=True,
        )


async def test_clasificar_con_una_categoria_que_no_existe(
    clientes: RepositorioClienteEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    """Es también el camino por el que se rechaza una categoría de otra empresa.

    La barrera de verdad es la RLS y se prueba contra PostgreSQL; acá se comprueba que el
    caso de uso levante el error correcto cuando el repositorio no la encuentra.
    """
    cliente = await _cliente(clientes)

    with pytest.raises(CategoriaNoEncontrada):
        await _clasificar_cliente(clientes, categorias, clasificaciones, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=cliente.id,
            categoria_id=uuid4(),
            asignar=True,
        )


# --- Eliminar -------------------------------------------------------------------------


async def test_eliminar_una_categoria(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    categoria = await _crear(categorias, publicador)

    await EliminarCategoria(categorias=categorias, publicador=publicador, reloj=RELOJ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        categoria_id=categoria.id,
    )

    assert categorias.categorias == {}


async def test_eliminar_una_que_no_existe(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    with pytest.raises(CategoriaNoEncontrada):
        await EliminarCategoria(categorias=categorias, publicador=publicador, reloj=RELOJ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            categoria_id=uuid4(),
        )


# --- Roles y bitácora -----------------------------------------------------------------


async def test_solo_lectura_lista_y_no_escribe(
    categorias: RepositorioCategoriaEnMemoria, publicador: PublicadorFalso
) -> None:
    await ListarCategorias(categorias=categorias).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.SOLO_LECTURA
    )

    with pytest.raises(PermisoDenegado):
        await _crear(categorias, publicador, rol=RolUsuario.SOLO_LECTURA)


async def test_cada_escritura_deja_bitacora(
    clientes: RepositorioClienteEnMemoria,
    categorias: RepositorioCategoriaEnMemoria,
    clasificaciones: ClasificacionesEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    cliente = await _cliente(clientes)
    categoria = await _crear(categorias, publicador, aplica_a=AmbitoDeCategoria.AMBOS)
    clasificar = _clasificar_cliente(clientes, categorias, clasificaciones, publicador)

    for asignar in (True, False):
        await clasificar.ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=cliente.id,
            categoria_id=categoria.id,
            asignar=asignar,
        )
    await EliminarCategoria(categorias=categorias, publicador=publicador, reloj=RELOJ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        categoria_id=categoria.id,
    )

    eventos = [e for e in publicador.eventos if isinstance(e, EventoAuditable)]
    assert [e.accion for e in eventos] == [
        ACCION_REGISTRADA,
        ACCION_CLASIFICADO,
        ACCION_DESCLASIFICADO,
        ACCION_ELIMINADA,
    ]
    assert {e.modulo for e in eventos} == {Modulo.MASTER_DATA}
