"""Los casos de uso del catálogo de servicios — HU-E4-02.

El dominio ya prueba los invariantes; lo que se prueba acá es que los casos de uso los
respeten sin repetirlos, que `origen` no se pueda mover, que el par
agendable/duración se maneje en una sola operación, y que cada escritura deje bitácora.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.master_data.application.errors import PermisoDenegado, ServicioNoEncontrado
from cheatsheet.contexts.master_data.application.servicios import (
    ACCION_DESACTIVADO,
    ACCION_EDITADO,
    ACCION_REGISTRADO,
    CambiarEstadoDeServicio,
    DatosDeServicio,
    EditarServicio,
    ListarServicios,
    RegistrarServicio,
)
from cheatsheet.contexts.master_data.domain.servicio import (
    MENSAJE_DURACION,
    MENSAJE_PRECIO,
    FiltrosDeServicio,
    ListadoDeServicios,
    Servicio,
)
from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.shared.auditoria import EventoAuditable, Modulo
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario

from tests.conftest import INSTANTE_FIJO
from tests.contexts.master_data.conftest import PublicadorFalso, RepositorioServicioEnMemoria

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
RELOJ = RelojFijo(INSTANTE_FIJO)


def _datos(
    *,
    nombre: str = "Corte de pelo",
    precio: str = "5000.00",
    alicuota: AlicuotaIVA = AlicuotaIVA.GENERAL,
    agendable: bool = False,
    duracion: int | None = None,
) -> DatosDeServicio:
    return DatosDeServicio(
        nombre=nombre,
        precio=Decimal(precio),
        alicuota_iva=alicuota,
        agendable=agendable,
        duracion_estandar_min=duracion,
    )


async def _alta(
    servicios: RepositorioServicioEnMemoria,
    publicador: PublicadorFalso,
    datos: DatosDeServicio | None = None,
    rol: RolUsuario = RolUsuario.OPERADOR,
) -> Servicio:
    return await RegistrarServicio(
        servicios=servicios, publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        datos=datos or _datos(),
    )


async def _edicion(
    servicios: RepositorioServicioEnMemoria,
    publicador: PublicadorFalso,
    servicio_id: UUID,
    datos: DatosDeServicio,
) -> Servicio:
    return await EditarServicio(servicios=servicios, publicador=publicador, reloj=RELOJ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        servicio_id=servicio_id,
        datos=datos,
    )


async def _estado(
    servicios: RepositorioServicioEnMemoria,
    publicador: PublicadorFalso,
    servicio_id: UUID,
    activo: bool,
) -> Servicio:
    return await CambiarEstadoDeServicio(
        servicios=servicios, publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        servicio_id=servicio_id,
        activo=activo,
    )


async def _listado(
    servicios: RepositorioServicioEnMemoria,
    *,
    rol: RolUsuario = RolUsuario.OPERADOR,
    empresa: EmpresaId = EMPRESA,
    filtros: FiltrosDeServicio | None = None,
) -> ListadoDeServicios:
    return await ListarServicios(servicios=servicios).ejecutar(
        empresa_id=empresa, rol=rol, filtros=filtros
    )


# --- Alta ----------------------------------------------------------------------------


async def test_alta_con_datos_validos(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    """«El servicio queda disponible para el agente y para nuevos comprobantes.»"""
    servicio = await _alta(servicios, publicador)

    assert servicio.origen is OrigenDato.PANEL
    assert servicio.activo is True
    assert servicio.precio == Decimal("5000.00")
    assert len(servicios.servicios) == 1


async def test_el_precio_llega_cuantizado_al_repositorio(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    """Lo que se guarda es lo que el dominio devolvió, no lo que mandó el formulario."""
    await _alta(servicios, publicador, _datos(precio="1234.567"))

    guardado = next(iter(servicios.servicios.values()))
    assert guardado.precio == Decimal("1234.57")


async def test_un_precio_invalido_no_guarda(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    with pytest.raises(EntradaInvalida, match=MENSAJE_PRECIO):
        await _alta(servicios, publicador, _datos(precio="0"))

    assert servicios.servicios == {}


async def test_un_agendable_sin_duracion_no_guarda(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    with pytest.raises(EntradaInvalida, match=MENSAJE_DURACION):
        await _alta(servicios, publicador, _datos(agendable=True))

    assert servicios.servicios == {}


# --- Edición -------------------------------------------------------------------------


async def test_editar_no_cambia_el_origen(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    creado = await _alta(servicios, publicador)

    editado = await _edicion(
        servicios, publicador, creado.id, _datos(nombre="Corte y barba", precio="7000")
    )

    assert editado.origen is OrigenDato.PANEL
    assert editado.nombre == "Corte y barba"
    assert editado.precio == Decimal("7000.00")


async def test_editar_para_volverlo_agendable(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    creado = await _alta(servicios, publicador)

    editado = await _edicion(servicios, publicador, creado.id, _datos(agendable=True, duracion=45))

    assert editado.agendable is True
    assert editado.duracion_estandar_min == 45


async def test_editar_para_dejar_de_ser_agendable_borra_la_duracion(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    creado = await _alta(servicios, publicador, _datos(agendable=True, duracion=45))

    editado = await _edicion(servicios, publicador, creado.id, _datos(agendable=False))

    assert editado.agendable is False
    assert editado.duracion_estandar_min is None


async def test_editar_a_agendable_sin_duracion_da_el_mensaje_de_la_regla(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    """El caso de uso no inventa un mensaje propio: deja que el agregado hable."""
    creado = await _alta(servicios, publicador)

    with pytest.raises(EntradaInvalida, match=MENSAJE_DURACION):
        await _edicion(servicios, publicador, creado.id, _datos(agendable=True))


async def test_editar_un_servicio_que_no_existe(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    with pytest.raises(ServicioNoEncontrado):
        await _edicion(servicios, publicador, uuid4(), _datos())


async def test_cambiar_la_alicuota(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    creado = await _alta(servicios, publicador)

    editado = await _edicion(
        servicios, publicador, creado.id, _datos(alicuota=AlicuotaIVA.REDUCIDA)
    )

    assert editado.alicuota_iva is AlicuotaIVA.REDUCIDA
    assert editado.alicuota_iva.tasa == Decimal("0.105")


# --- Estado y listado ----------------------------------------------------------------


async def test_desactivar_lo_saca_del_catalogo_activo_sin_borrarlo(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    """RN-04."""
    creado = await _alta(servicios, publicador)

    await _estado(servicios, publicador, creado.id, activo=False)

    activos = await _listado(servicios, filtros=FiltrosDeServicio(solo_activos=True))
    todos = await _listado(servicios)

    assert activos.total == 0
    assert todos.total == 1


async def test_reactivar_lo_devuelve(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    creado = await _alta(servicios, publicador)
    await _estado(servicios, publicador, creado.id, activo=False)

    await _estado(servicios, publicador, creado.id, activo=True)

    activos = await _listado(servicios, filtros=FiltrosDeServicio(solo_activos=True))
    assert activos.total == 1


async def test_cambiar_el_estado_de_uno_que_no_existe(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    with pytest.raises(ServicioNoEncontrado):
        await _estado(servicios, publicador, uuid4(), activo=False)


async def test_el_listado_no_cruza_empresas(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    await _alta(servicios, publicador)

    listado = await _listado(servicios, empresa=EmpresaId(uuid4()))

    assert listado.total == 0


async def test_el_filtro_de_agendable_separa_los_dos_grupos(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    await _alta(servicios, publicador, _datos(nombre="Corte", agendable=True, duracion=30))
    await _alta(servicios, publicador, _datos(nombre="Shampoo"))

    agendables = await _listado(servicios, filtros=FiltrosDeServicio(agendable=True))
    resto = await _listado(servicios, filtros=FiltrosDeServicio(agendable=False))

    assert [s.nombre for s in agendables.servicios] == ["Corte"]
    assert [s.nombre for s in resto.servicios] == ["Shampoo"]


async def test_el_buscador_encuentra_por_nombre(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    await _alta(servicios, publicador, _datos(nombre="Corte de pelo"))
    await _alta(servicios, publicador, _datos(nombre="Coloracion"))

    encontrados = await _listado(servicios, filtros=FiltrosDeServicio(texto="corte"))

    assert encontrados.total == 1


# --- Roles ---------------------------------------------------------------------------


async def test_solo_lectura_lista_y_no_escribe(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    listado = await _listado(servicios, rol=RolUsuario.SOLO_LECTURA)
    assert listado.total == 0

    with pytest.raises(PermisoDenegado):
        await _alta(servicios, publicador, rol=RolUsuario.SOLO_LECTURA)


# --- Bitácora ------------------------------------------------------------------------


async def test_cada_escritura_deja_un_evento_auditable(
    servicios: RepositorioServicioEnMemoria, publicador: PublicadorFalso
) -> None:
    creado = await _alta(servicios, publicador)

    await _edicion(servicios, publicador, creado.id, _datos(nombre="Corte y barba"))
    await _estado(servicios, publicador, creado.id, activo=False)

    eventos = [e for e in publicador.eventos if isinstance(e, EventoAuditable)]
    assert [e.accion for e in eventos] == [
        ACCION_REGISTRADO,
        ACCION_EDITADO,
        ACCION_DESACTIVADO,
    ]
    assert {e.modulo for e in eventos} == {Modulo.MASTER_DATA}
    assert {e.entidad_afectada for e in eventos} == {f"servicio:{creado.id}"}
