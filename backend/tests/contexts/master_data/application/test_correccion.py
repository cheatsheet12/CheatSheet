"""Los casos de uso de la corrección de datos existentes — HU-E4-05 RN-09.

Tres cosas se prueban con más insistencia que el resto:

- que el **informe no escriba nada** (es un dry-run);
- que la **bitácora lleve solo conteos**: un nombre de cliente en `detalle` quedaría guardado
  para siempre en una tabla que nadie puede modificar;
- que **solo el Administrador** pueda usar los casos de uso.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.master_data.application.correccion import (
    ACCION_APLICADA,
    ACCION_RESTAURADA,
    EJEMPLOS_POR_ENTIDAD,
    AplicarCorreccion,
    InformarCorreccion,
    ListarCorridas,
    RestaurarCorreccion,
)
from cheatsheet.contexts.master_data.application.errors import (
    CorreccionEnCurso,
    CorridaNoEncontrada,
    PermisoDenegado,
)
from cheatsheet.contexts.master_data.application.ports import ResumenDeCorrida
from cheatsheet.contexts.master_data.domain.correccion import (
    Cambio,
    EntidadCorregible,
    MotivoDeOmision,
    NombreRegistrado,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario

from tests.conftest import INSTANTE_FIJO
from tests.contexts.master_data.conftest import PublicadorFalso

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
RELOJ = RelojFijo(INSTANTE_FIJO)
NOMBRE_DE_PRUEBA = "JUAN PEREZ"
OTRO_NOMBRE_DE_PRUEBA = "FERRETERIA LOPEZ"


class CorreccionEnMemoria:
    """Implementa `PortCorreccionDeNombres`. Cuenta lo que se escribe, que es lo que importa."""

    def __init__(self, registros: Sequence[NombreRegistrado] = (), *, turno: bool = True) -> None:
        self.registros = list(registros)
        self.turno = turno
        self.aplicaciones: list[Sequence[Cambio]] = []
        self.corridas: set[UUID] = set()
        self.restauradas: list[UUID] = []
        self.resultado_de_restauracion = (0, 0)
        self.descartar = 0

    async def tomar_turno(self) -> bool:
        return self.turno

    async def leer_nombres(self) -> Sequence[NombreRegistrado]:
        return self.registros

    async def aplicar(
        self, corrida_id: UUID, cambios: Sequence[Cambio], momento: datetime
    ) -> Sequence[Cambio]:
        del momento
        self.aplicaciones.append(cambios)
        self.corridas.add(corrida_id)
        return list(cambios)[self.descartar :]

    async def restaurar(self, corrida_id: UUID) -> tuple[int, int]:
        self.restauradas.append(corrida_id)
        return self.resultado_de_restauracion

    async def existe_corrida(self, corrida_id: UUID) -> bool:
        return corrida_id in self.corridas

    async def listar_corridas(self) -> Sequence[ResumenDeCorrida]:
        return [
            ResumenDeCorrida(corrida_id=c, creada_en=INSTANTE_FIJO, cantidad=1)
            for c in self.corridas
        ]


def _cliente(nombre: str) -> NombreRegistrado:
    return NombreRegistrado(entidad=EntidadCorregible.CLIENTE, id=uuid4(), nombre=nombre)


async def _aplicar(
    correccion: CorreccionEnMemoria,
    publicador: PublicadorFalso,
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
) -> UUID:
    resultado = await AplicarCorreccion(
        correccion=correccion, publicador=publicador, reloj=RELOJ
    ).ejecutar(empresa_id=EMPRESA, usuario_id=USUARIO, rol=rol, direccion_ip=None)
    return resultado.corrida_id


async def _restaurar(
    correccion: CorreccionEnMemoria,
    publicador: PublicadorFalso,
    corrida_id: UUID,
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
) -> tuple[int, int]:
    resultado = await RestaurarCorreccion(
        correccion=correccion, publicador=publicador, reloj=RELOJ
    ).ejecutar(
        empresa_id=EMPRESA, usuario_id=USUARIO, rol=rol, corrida_id=corrida_id, direccion_ip=None
    )
    return (resultado.restaurados, resultado.conservados)


async def test_el_informe_da_conteos_y_a_lo_sumo_cinco_ejemplos_y_no_escribe() -> None:
    registros = [_cliente(f"CLIENTE NUMERO {n}") for n in range(8)]
    registros.append(NombreRegistrado(entidad=EntidadCorregible.CATEGORIA, id=uuid4(), nombre="​"))
    correccion = CorreccionEnMemoria(registros)

    informe = await InformarCorreccion(correccion=correccion).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.ADMINISTRADOR
    )

    assert informe.a_corregir[EntidadCorregible.CLIENTE] == 8
    assert informe.a_corregir[EntidadCorregible.SERVICIO] == 0
    assert informe.omitidos[MotivoDeOmision.NOMBRE_INVALIDO] == 1
    ejemplos = informe.ejemplos[EntidadCorregible.CLIENTE]
    assert len(ejemplos) == EJEMPLOS_POR_ENTIDAD == 5
    assert (ejemplos[0].antes, ejemplos[0].despues) == ("CLIENTE NUMERO 0", "Cliente Numero 0")
    assert correccion.aplicaciones == []
    assert correccion.corridas == set()


@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
async def test_solo_el_administrador_puede_usar_los_casos_de_uso(rol: RolUsuario) -> None:
    correccion = CorreccionEnMemoria([_cliente(NOMBRE_DE_PRUEBA)])
    publicador = PublicadorFalso()

    with pytest.raises(PermisoDenegado):
        await InformarCorreccion(correccion=correccion).ejecutar(empresa_id=EMPRESA, rol=rol)
    with pytest.raises(PermisoDenegado):
        await _aplicar(correccion, publicador, rol)
    with pytest.raises(PermisoDenegado):
        await _restaurar(correccion, publicador, uuid4(), rol)
    with pytest.raises(PermisoDenegado):
        await ListarCorridas(correccion=correccion).ejecutar(empresa_id=EMPRESA, rol=rol)

    assert correccion.aplicaciones == []
    assert correccion.restauradas == []
    assert publicador.eventos == []


async def test_aplicar_publica_conteos_y_ningun_nombre() -> None:
    correccion = CorreccionEnMemoria(
        [
            _cliente(NOMBRE_DE_PRUEBA),
            _cliente(OTRO_NOMBRE_DE_PRUEBA),
            NombreRegistrado(entidad=EntidadCorregible.SERVICIO, id=uuid4(), nombre="CORTE PELO"),
        ]
    )
    publicador = PublicadorFalso()

    corrida_id = await _aplicar(correccion, publicador)

    (evento,) = publicador.eventos
    assert isinstance(evento, EventoAuditable)
    assert evento.modulo is Modulo.MASTER_DATA
    assert evento.accion == ACCION_APLICADA == "correccion_de_datos_aplicada"
    assert evento.entidad_afectada == f"correccion:{corrida_id}"
    assert evento.usuario_id == USUARIO
    assert evento.detalle is not None
    assert evento.detalle["clientes"] == "2"
    assert evento.detalle["servicios"] == "1"
    assert evento.detalle["categorias"] == "0"
    assert {"omitidos_colision", "omitidos_nombre_invalido", "omitidos_duracion"} <= set(
        evento.detalle
    )
    texto = " ".join([evento.entidad_afectada, *evento.detalle, *evento.detalle.values()]).lower()
    for fragmento in ("juan", "perez", "ferreteria", "lopez", "corte", "pelo"):
        assert fragmento not in texto


async def test_aplicar_cuenta_lo_que_se_escribio_y_no_lo_que_se_planeo() -> None:
    correccion = CorreccionEnMemoria([_cliente(NOMBRE_DE_PRUEBA), _cliente(OTRO_NOMBRE_DE_PRUEBA)])
    correccion.descartar = 1
    publicador = PublicadorFalso()

    await _aplicar(correccion, publicador)

    (evento,) = publicador.eventos
    assert isinstance(evento, EventoAuditable)
    assert evento.detalle is not None
    assert evento.detalle["clientes"] == "1"
    assert evento.detalle["no_aplicados"] == "1"


async def test_sin_turno_no_se_escribe_nada() -> None:
    correccion = CorreccionEnMemoria([_cliente(NOMBRE_DE_PRUEBA)], turno=False)
    publicador = PublicadorFalso()

    with pytest.raises(CorreccionEnCurso):
        await _aplicar(correccion, publicador)
    with pytest.raises(CorreccionEnCurso):
        await _restaurar(correccion, publicador, uuid4())

    assert correccion.aplicaciones == []
    assert correccion.restauradas == []
    assert publicador.eventos == []


async def test_restaurar_una_corrida_inexistente_levanta_corrida_no_encontrada() -> None:
    correccion = CorreccionEnMemoria()
    publicador = PublicadorFalso()

    with pytest.raises(CorridaNoEncontrada):
        await _restaurar(correccion, publicador, uuid4())

    assert correccion.restauradas == []
    assert publicador.eventos == []


async def test_restaurar_publica_conteos() -> None:
    corrida = uuid4()
    correccion = CorreccionEnMemoria()
    correccion.corridas.add(corrida)
    correccion.resultado_de_restauracion = (3, 1)
    publicador = PublicadorFalso()

    resultado = await _restaurar(correccion, publicador, corrida)

    assert resultado == (3, 1)
    (evento,) = publicador.eventos
    assert isinstance(evento, EventoAuditable)
    assert evento.accion == ACCION_RESTAURADA == "correccion_de_datos_restaurada"
    assert evento.entidad_afectada == f"correccion:{corrida}"
    assert evento.detalle == {"restaurados": "3", "conservados": "1"}


async def test_el_administrador_lista_las_corridas() -> None:
    corrida = uuid4()
    correccion = CorreccionEnMemoria()
    correccion.corridas.add(corrida)

    corridas = await ListarCorridas(correccion=correccion).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.ADMINISTRADOR
    )

    assert [c.corrida_id for c in corridas] == [corrida]
