"""Los casos de uso del catálogo de clientes — HU-E4-01.

La regla que cruza casi todo el archivo es la misma que gobierna el padrón en `identity`,
y acá vuelve a ser la que importa: **no encontrar y no poder preguntar son cosas
distintas**. La primera bloquea el guardado (RN-02); la segunda no puede, porque la
situación normal de una empresa que sólo quiere su lista de clientes es justamente que
ARCA nunca se conectó.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.master_data.application.clientes import (
    ACCION_DESACTIVADO,
    ACCION_EDITADO,
    ACCION_REGISTRADO,
    CambiarEstadoDeCliente,
    DatosDeCliente,
    EditarCliente,
    ListarClientes,
    RegistrarCliente,
    VerCliente,
    VistaDeCliente,
)
from cheatsheet.contexts.master_data.application.errors import (
    ClienteDuplicado,
    ClienteNoEncontrado,
    CuitInexistente,
    PermisoDenegado,
)
from cheatsheet.contexts.master_data.application.padron import (
    MENSAJE_LARGO_INVALIDO,
    EstadoDeConsulta,
)
from cheatsheet.contexts.master_data.domain.cliente import FiltrosDeCliente, ListadoDeClientes
from cheatsheet.contexts.master_data.domain.valores import OrigenDato
from cheatsheet.shared.auditoria import EventoAuditable, Modulo
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CondicionIVA
from cheatsheet.shared.roles import RolUsuario

from tests.conftest import INSTANTE_FIJO
from tests.contexts.master_data.conftest import (
    CUIT_DIGITO_MALO,
    CUIT_VALIDO,
    OTRO_CUIT_VALIDO,
    PadronFalso,
    PublicadorFalso,
    RepositorioClienteEnMemoria,
    padron_sin_conectar,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
RELOJ = RelojFijo(INSTANTE_FIJO)


async def _alta(
    clientes: RepositorioClienteEnMemoria,
    padron: PadronFalso,
    publicador: PublicadorFalso,
    datos: DatosDeCliente,
    rol: RolUsuario = RolUsuario.OPERADOR,
) -> VistaDeCliente:
    return await RegistrarCliente(
        clientes=clientes, padron=padron, publicador=publicador, reloj=RELOJ
    ).ejecutar(empresa_id=EMPRESA, usuario_id=USUARIO, rol=rol, datos=datos)


async def _edicion(
    clientes: RepositorioClienteEnMemoria,
    padron: PadronFalso,
    publicador: PublicadorFalso,
    cliente_id: UUID,
    datos: DatosDeCliente,
) -> VistaDeCliente:
    return await EditarCliente(
        clientes=clientes, padron=padron, publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente_id,
        datos=datos,
    )


async def _estado(
    clientes: RepositorioClienteEnMemoria,
    publicador: PublicadorFalso,
    cliente_id: UUID,
    activo: bool,
) -> VistaDeCliente:
    return await CambiarEstadoDeCliente(
        clientes=clientes, publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        cliente_id=cliente_id,
        activo=activo,
    )


async def _listado(
    clientes: RepositorioClienteEnMemoria,
    *,
    rol: RolUsuario = RolUsuario.OPERADOR,
    empresa: EmpresaId = EMPRESA,
    filtros: FiltrosDeCliente | None = None,
) -> ListadoDeClientes:
    return await ListarClientes(clientes=clientes).ejecutar(
        empresa_id=empresa, rol=rol, filtros=filtros
    )


# --- Validación estructural: bloquea siempre, con o sin ARCA -------------------------


@pytest.mark.parametrize("cuit", ["3071234567", "123", "307123456712"])
async def test_un_cuit_que_no_tiene_once_digitos_no_guarda_ni_pregunta(
    clientes: RepositorioClienteEnMemoria,
    padron: PadronFalso,
    publicador: PublicadorFalso,
    cuit: str,
) -> None:
    """El mensaje es el que pide el criterio de aceptación, y ARCA no se toca."""
    with pytest.raises(EntradaInvalida, match=MENSAJE_LARGO_INVALIDO):
        await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa", cuit=cuit))

    assert padron.llamadas == 0
    assert clientes.clientes == {}


async def test_un_digito_verificador_incorrecto_no_llega_a_arca(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    datos = DatosDeCliente(nombre="Rosa", cuit=CUIT_DIGITO_MALO)

    with pytest.raises(EntradaInvalida, match="digito verificador"):
        await _alta(clientes, padron, publicador, datos)

    assert padron.llamadas == 0


# --- Las tres respuestas del padrón --------------------------------------------------


async def test_alta_con_cuit_conocido_completa_razon_social_y_condicion_iva(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """Segundo criterio de aceptación, incluido el «guarda con origen PANEL»."""
    vista = await _alta(clientes, padron, publicador, DatosDeCliente(cuit=CUIT_VALIDO))

    # HU-E4-05 RN-03: un CUIT 30 es razón social. Las palabras de hasta 4 letras en
    # mayúsculas se conservan por suponerse siglas (el falso positivo que la historia acepta).
    assert vista.cliente.nombre == "Panaderia DONA ROSA SRL"
    assert vista.cliente.condicion_iva is CondicionIVA.RESPONSABLE_INSCRIPTO
    assert vista.cliente.origen is OrigenDato.PANEL
    assert vista.validacion is not None
    assert vista.validacion.estado is EstadoDeConsulta.ENCONTRADO


async def test_lo_que_escribio_el_usuario_le_gana_al_padron(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """El autocompletado llena lo que quedó vacío; no corrige a nadie."""
    vista = await _alta(
        clientes,
        padron,
        publicador,
        DatosDeCliente(
            nombre="Panaderia de la esquina",
            cuit=CUIT_VALIDO,
            condicion_iva=CondicionIVA.MONOTRIBUTO,
        ),
    )

    assert vista.cliente.nombre == "Panaderia de la Esquina"
    assert vista.cliente.condicion_iva is CondicionIVA.MONOTRIBUTO


async def test_un_cuit_que_arca_no_conoce_bloquea_el_guardado(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    """RN-02: «Un CUIT inválido bloquea el guardado»."""
    padron = PadronFalso(datos=None)

    with pytest.raises(CuitInexistente):
        await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa", cuit=CUIT_VALIDO))

    assert clientes.clientes == {}


async def test_con_arca_sin_conectar_el_cliente_se_guarda_igual(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    """La decisión de este Gate 1, y el caso más frecuente del sistema real."""
    padron = padron_sin_conectar()

    vista = await _alta(
        clientes, padron, publicador, DatosDeCliente(nombre="Rosa", cuit=CUIT_VALIDO)
    )

    assert vista.cliente.cuit is not None
    assert vista.cliente.cuit.valor == CUIT_VALIDO
    assert len(clientes.clientes) == 1


async def test_el_padron_caido_se_reporta_y_no_se_confunde_con_inexistente(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    """La distinción entera de la unidad, en dos asserts."""
    padron = padron_sin_conectar()

    vista = await _alta(
        clientes, padron, publicador, DatosDeCliente(nombre="Rosa", cuit=CUIT_VALIDO)
    )

    assert vista.validacion is not None
    assert vista.validacion.estado is EstadoDeConsulta.NO_DISPONIBLE
    assert vista.validacion.motivo == "La empresa no tiene ARCA conectada"


async def test_sin_cuit_no_se_consulta_el_padron(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    vista = await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Cliente de WhatsApp"))

    assert padron.llamadas == 0
    assert vista.validacion is None
    assert vista.cliente.cuit is None


async def test_sin_nombre_ni_razon_social_no_hay_cliente(
    clientes: RepositorioClienteEnMemoria, publicador: PublicadorFalso
) -> None:
    """Si el padrón no contesta y nadie escribió un nombre, no queda de dónde sacarlo."""
    padron = padron_sin_conectar()

    with pytest.raises(EntradaInvalida, match="nombre"):
        await _alta(clientes, padron, publicador, DatosDeCliente(cuit=CUIT_VALIDO))


# --- RN-03: un CUIT por empresa ------------------------------------------------------


async def test_el_segundo_cliente_con_el_mismo_cuit_nombra_al_primero(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """«Ya existe un cliente con ese CUIT.» y, además, cuál — para poder ofrecer verlo."""
    primero = await _alta(
        clientes, padron, publicador, DatosDeCliente(nombre="Rosa", cuit=CUIT_VALIDO)
    )

    with pytest.raises(ClienteDuplicado) as error:
        await _alta(
            clientes, padron, publicador, DatosDeCliente(nombre="Rosa otra vez", cuit=CUIT_VALIDO)
        )

    assert str(error.value) == "Ya existe un cliente con ese CUIT."
    assert error.value.cliente_existente_id == primero.cliente.id


async def test_dos_clientes_sin_cuit_conviven(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """No tener CUIT no los hace duplicados entre sí."""
    await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Uno"))
    await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Otro"))

    assert len(clientes.clientes) == 2


# --- Edición -------------------------------------------------------------------------


async def test_editar_sin_tocar_el_cuit_no_vuelve_a_preguntarle_a_arca(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """Corregir un teléfono no gasta una consulta al padrón, ni falla si ARCA está caída."""
    creado = await _alta(
        clientes, padron, publicador, DatosDeCliente(nombre="Rosa", cuit=CUIT_VALIDO)
    )
    llamadas_del_alta = padron.llamadas

    await _edicion(
        clientes,
        padron,
        publicador,
        creado.cliente.id,
        DatosDeCliente(nombre="Rosa", cuit=CUIT_VALIDO, contacto_whatsapp="1112345678"),
    )

    assert padron.llamadas == llamadas_del_alta


async def test_editar_cambiando_el_cuit_si_consulta(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    creado = await _alta(
        clientes, padron, publicador, DatosDeCliente(nombre="Rosa", cuit=CUIT_VALIDO)
    )
    llamadas_del_alta = padron.llamadas

    await _edicion(
        clientes,
        padron,
        publicador,
        creado.cliente.id,
        DatosDeCliente(nombre="Rosa", cuit=OTRO_CUIT_VALIDO),
    )

    assert padron.llamadas == llamadas_del_alta + 1
    assert padron.ultimo_cuit == OTRO_CUIT_VALIDO


async def test_editar_no_cambia_el_origen(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """RN-01, del lado de la edición: no hay campo que lo lleve."""
    creado = await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa"))

    vista = await _edicion(
        clientes, padron, publicador, creado.cliente.id, DatosDeCliente(nombre="Rosa Diaz")
    )

    assert vista.cliente.origen is OrigenDato.PANEL
    assert vista.cliente.nombre == "Rosa Diaz"


async def test_editar_un_cliente_que_no_existe(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    with pytest.raises(ClienteNoEncontrado):
        await _edicion(clientes, padron, publicador, uuid4(), DatosDeCliente(nombre="Fantasma"))


# --- Estado y listado ----------------------------------------------------------------


async def test_desactivar_lo_saca_del_catalogo_activo_sin_borrarlo(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    creado = await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa"))

    await _estado(clientes, publicador, creado.cliente.id, activo=False)

    activos = await _listado(clientes, filtros=FiltrosDeCliente(solo_activos=True))
    todos = await _listado(clientes)

    assert activos.total == 0
    assert todos.total == 1


async def test_reactivar_lo_devuelve_al_catalogo(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    creado = await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa"))
    await _estado(clientes, publicador, creado.cliente.id, activo=False)

    await _estado(clientes, publicador, creado.cliente.id, activo=True)

    activos = await _listado(clientes, filtros=FiltrosDeCliente(solo_activos=True))
    assert activos.total == 1


async def test_el_listado_no_cruza_empresas(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """El doble filtra por empresa; la barrera de verdad se prueba contra PostgreSQL."""
    await _alta(clientes, padron, publicador, DatosDeCliente(nombre="De la empresa A"))

    listado = await _listado(clientes, empresa=EmpresaId(uuid4()))

    assert listado.total == 0


async def test_el_buscador_encuentra_por_nombre_y_por_cuit(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Panaderia", cuit=CUIT_VALIDO))
    await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Ferreteria"))

    por_nombre = await _listado(clientes, filtros=FiltrosDeCliente(texto="ferre"))
    por_cuit = await _listado(clientes, filtros=FiltrosDeCliente(texto="7123456"))

    assert por_nombre.total == 1
    assert por_cuit.total == 1
    assert por_cuit.clientes[0].nombre == "Panaderia"


# --- Roles ---------------------------------------------------------------------------


async def test_solo_lectura_puede_listar_y_no_escribir(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """Matriz de acceso del mapa de navegación §5: Datos Maestros es RO para ese rol."""
    listado = await _listado(clientes, rol=RolUsuario.SOLO_LECTURA)
    assert listado.total == 0

    with pytest.raises(PermisoDenegado):
        await _alta(
            clientes,
            padron,
            publicador,
            DatosDeCliente(nombre="Rosa"),
            rol=RolUsuario.SOLO_LECTURA,
        )


async def test_el_operador_puede_escribir(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """HU-E4-01 nombra a los dos actores: no es una pantalla sólo de Administrador."""
    await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa"))

    assert len(clientes.clientes) == 1


# --- Ver uno por id (PAN-COB-03 muestra el cliente preseleccionado) ------------------


@pytest.mark.parametrize(
    "rol", [RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA]
)
async def test_ver_un_cliente_lo_devuelve_para_todos_los_roles_que_leen(
    clientes: RepositorioClienteEnMemoria,
    padron: PadronFalso,
    publicador: PublicadorFalso,
    rol: RolUsuario,
) -> None:
    creado = await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa"))

    visto = await VerCliente(clientes=clientes).ejecutar(rol=rol, cliente_id=creado.cliente.id)

    assert visto.id == creado.cliente.id
    assert visto.nombre == "Rosa"


async def test_ver_un_cliente_inactivo_lo_devuelve_igual(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """Decidir que un inactivo no sirve para cobrar es de quien llama, no de la lectura."""
    creado = await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa"))
    await _estado(clientes, publicador, creado.cliente.id, activo=False)

    visto = await VerCliente(clientes=clientes).ejecutar(
        rol=RolUsuario.OPERADOR, cliente_id=creado.cliente.id
    )

    assert visto.activo is False


async def test_ver_un_cliente_que_no_existe(clientes: RepositorioClienteEnMemoria) -> None:
    with pytest.raises(ClienteNoEncontrado):
        await VerCliente(clientes=clientes).ejecutar(rol=RolUsuario.OPERADOR, cliente_id=uuid4())


# --- Bitácora ------------------------------------------------------------------------


async def test_cada_escritura_deja_un_evento_auditable(
    clientes: RepositorioClienteEnMemoria, padron: PadronFalso, publicador: PublicadorFalso
) -> None:
    """HS-T5 llega hasta acá: el sumidero existe desde el épico 1 y este módulo lo usa."""
    creado = await _alta(clientes, padron, publicador, DatosDeCliente(nombre="Rosa"))
    cliente_id = creado.cliente.id

    await _edicion(clientes, padron, publicador, cliente_id, DatosDeCliente(nombre="Rosa Diaz"))
    await _estado(clientes, publicador, cliente_id, activo=False)

    eventos = [e for e in publicador.eventos if isinstance(e, EventoAuditable)]
    assert [e.accion for e in eventos] == [
        ACCION_REGISTRADO,
        ACCION_EDITADO,
        ACCION_DESACTIVADO,
    ]
    assert {e.modulo for e in eventos} == {Modulo.MASTER_DATA}
    assert {e.entidad_afectada for e in eventos} == {f"cliente:{cliente_id}"}
