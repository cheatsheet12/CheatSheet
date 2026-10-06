"""Los casos de uso de HU-E2-04 — las tres vías por las que entra una planilla.

El proveedor simulado hace de doble: es el mismo adaptador que corre en una laptop, así
que estos tests ejercitan el ACL real y no una imitación suya. El almacenamiento en
memoria hace lo mismo con R2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    PermisosDePlanillaInsuficientes,
    VinculoInexistente,
)
from cheatsheet.contexts.spreadsheet_sync.application.vinculos import (
    ConfirmarVinculacionConGoogle,
    DesvincularPlanilla,
    IniciarVinculacionConGoogle,
    ListarVinculos,
    SubirPlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    LIMITE_TAMANO_BYTES,
    MENSAJE_ARCHIVO_DEMASIADO_GRANDE,
    MENSAJE_FORMATO_NO_ACEPTADO,
    MENSAJE_SIN_PERMISOS,
    DireccionSync,
    ProveedorPlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.google_sheets import (
    ProveedorDePlanillaSimulado,
)
from cheatsheet.platform.almacenamiento import (
    AlmacenamientoEnMemoria,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
CODIGO = "simulado:planilla-de-prueba"


class RepositorioFalso:
    def __init__(self) -> None:
        self.vinculos: dict[UUID, VinculoDePlanilla] = {}

    async def agregar(self, vinculo: VinculoDePlanilla) -> None:
        self.vinculos[vinculo.id] = vinculo

    async def actualizar(self, vinculo: VinculoDePlanilla) -> None:
        self.vinculos[vinculo.id] = vinculo

    async def buscar_por_id(self, vinculo_id: UUID) -> VinculoDePlanilla | None:
        return self.vinculos.get(vinculo_id)

    async def listar(self) -> list[VinculoDePlanilla]:
        return list(self.vinculos.values())

    async def eliminar(self, vinculo_id: UUID) -> None:
        self.vinculos.pop(vinculo_id, None)


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


@pytest.fixture
def vinculos() -> RepositorioFalso:
    return RepositorioFalso()


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


@pytest.fixture
def almacenamiento() -> AlmacenamientoEnMemoria:
    return AlmacenamientoEnMemoria()


@pytest.fixture
def proveedor() -> ProveedorDePlanillaSimulado:
    return ProveedorDePlanillaSimulado()


async def test_vincular_google_guarda_el_vinculo_y_lo_audita(
    vinculos: RepositorioFalso,
    proveedor: ProveedorDePlanillaSimulado,
    publicador: PublicadorFalso,
) -> None:
    vinculo = await ConfirmarVinculacionConGoogle(
        vinculos=vinculos, proveedor=proveedor, publicador=publicador
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        codigo=CODIGO,
        identificador_documento="1AbCdEf",
        direccion=DireccionSync.SOLO_LECTURA,
        ahora=AHORA,
    )

    assert vinculo.proveedor is ProveedorPlanilla.GOOGLE_SHEETS
    assert vinculo.identificador_externo == "1AbCdEf"
    assert vinculo.hoja_empresa == "Clientes"
    assert len(publicador.eventos) == 1
    assert vinculos.vinculos[vinculo.id] is vinculo


async def test_sin_permisos_no_se_crea_el_vinculo(
    vinculos: RepositorioFalso,
    proveedor: ProveedorDePlanillaSimulado,
    publicador: PublicadorFalso,
) -> None:
    """Caso 3 del plan.

    El criterio de aceptación dice dos cosas y las dos importan: el mensaje exacto, **y**
    que no quede un vínculo a medias. Por eso el canje va antes de cualquier escritura.
    """
    with pytest.raises(PermisosDePlanillaInsuficientes) as exc:
        await ConfirmarVinculacionConGoogle(
            vinculos=vinculos, proveedor=proveedor, publicador=publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            codigo="el-usuario-nego-el-permiso",
            identificador_documento="1AbCdEf",
            direccion=DireccionSync.SOLO_LECTURA,
            ahora=AHORA,
        )

    assert str(exc.value) == MENSAJE_SIN_PERMISOS
    assert vinculos.vinculos == {}
    assert publicador.eventos == []


async def test_subir_una_planilla_guarda_los_bytes_y_crea_el_vinculo(
    vinculos: RepositorioFalso,
    almacenamiento: AlmacenamientoEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    vinculo = await SubirPlanilla(
        vinculos=vinculos, almacenamiento=almacenamiento, publicador=publicador
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        nombre_de_archivo="clientes.xlsx",
        contenido=b"contenido-de-la-planilla",
        ahora=AHORA,
    )

    assert vinculo.proveedor is ProveedorPlanilla.ARCHIVO
    assert vinculo.direccion is DireccionSync.SOLO_LECTURA
    assert vinculo.archivo is not None
    assert almacenamiento.archivos[vinculo.archivo.clave] == b"contenido-de-la-planilla"
    # La clave lleva empresa y vínculo, nunca el nombre que puso la empresa: dos clientes
    # subiendo `clientes.xlsx` no pueden pisarse.
    assert str(EMPRESA) in vinculo.archivo.clave
    assert vinculo.archivo.nombre_original == "clientes.xlsx"


@pytest.mark.parametrize(
    ("nombre", "mensaje"),
    [("clientes.pdf", MENSAJE_FORMATO_NO_ACEPTADO), ("notas.txt", MENSAJE_FORMATO_NO_ACEPTADO)],
)
async def test_un_formato_no_soportado_no_llega_al_almacenamiento(
    vinculos: RepositorioFalso,
    almacenamiento: AlmacenamientoEnMemoria,
    publicador: PublicadorFalso,
    nombre: str,
    mensaje: str,
) -> None:
    """Caso 4 del plan. Validar después de guardar dejaría basura en el bucket."""
    with pytest.raises(EntradaInvalida) as exc:
        await SubirPlanilla(
            vinculos=vinculos, almacenamiento=almacenamiento, publicador=publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            nombre_de_archivo=nombre,
            contenido=b"x",
            ahora=AHORA,
        )

    assert str(exc.value) == mensaje
    assert almacenamiento.archivos == {}
    assert vinculos.vinculos == {}


async def test_un_archivo_demasiado_grande_no_llega_al_almacenamiento(
    vinculos: RepositorioFalso,
    almacenamiento: AlmacenamientoEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    """Caso 5 del plan. Un objeto de 30 MB por cada rechazo, y nada que lo borre."""
    with pytest.raises(EntradaInvalida) as exc:
        await SubirPlanilla(
            vinculos=vinculos, almacenamiento=almacenamiento, publicador=publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            nombre_de_archivo="grande.xlsx",
            contenido=b"x" * (LIMITE_TAMANO_BYTES + 1),
            ahora=AHORA,
        )

    assert str(exc.value) == MENSAJE_ARCHIVO_DEMASIADO_GRANDE
    assert almacenamiento.archivos == {}


@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
async def test_solo_un_administrador_vincula_o_sube(
    vinculos: RepositorioFalso,
    almacenamiento: AlmacenamientoEnMemoria,
    proveedor: ProveedorDePlanillaSimulado,
    publicador: PublicadorFalso,
    rol: RolUsuario,
) -> None:
    """Caso 6 del plan. La precondición de HU-E2-04, con la lección de PRU-09 aplicada:
    la regla viaja con la operación y no vive sólo en el router."""
    with pytest.raises(EntradaInvalida):
        IniciarVinculacionConGoogle(proveedor).ejecutar(rol=rol)

    with pytest.raises(EntradaInvalida):
        await SubirPlanilla(
            vinculos=vinculos, almacenamiento=almacenamiento, publicador=publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=rol,
            nombre_de_archivo="clientes.xlsx",
            contenido=b"x",
            ahora=AHORA,
        )

    assert vinculos.vinculos == {}


async def test_cualquier_rol_puede_listar(vinculos: RepositorioFalso) -> None:
    """HU-E3-05 RN-04: Solo Lectura mira sin poder actuar."""
    assert await ListarVinculos(vinculos).ejecutar() == []


async def test_desvincular_borra_el_archivo_y_el_vinculo(
    vinculos: RepositorioFalso,
    almacenamiento: AlmacenamientoEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    """Los bytes se van con el vínculo: son una copia que la empresa puede volver a subir,
    y guardar datos personales que nadie puede alcanzar desde el panel no es conservar."""
    vinculo = await SubirPlanilla(
        vinculos=vinculos, almacenamiento=almacenamiento, publicador=publicador
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        nombre_de_archivo="clientes.xlsx",
        contenido=b"x",
        ahora=AHORA,
    )

    await DesvincularPlanilla(
        vinculos=vinculos, almacenamiento=almacenamiento, publicador=publicador
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.ADMINISTRADOR,
        vinculo_id=vinculo.id,
        ahora=AHORA,
    )

    assert vinculos.vinculos == {}
    assert almacenamiento.archivos == {}


async def test_desvincular_algo_que_no_existe_falla_con_su_propio_error(
    vinculos: RepositorioFalso,
    almacenamiento: AlmacenamientoEnMemoria,
    publicador: PublicadorFalso,
) -> None:
    with pytest.raises(VinculoInexistente):
        await DesvincularPlanilla(
            vinculos=vinculos, almacenamiento=almacenamiento, publicador=publicador
        ).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            vinculo_id=uuid4(),
            ahora=AHORA,
        )


async def test_la_url_de_autorizacion_lleva_el_estado_generado(
    proveedor: ProveedorDePlanillaSimulado,
) -> None:
    """El `state` es lo que impide que alguien enganche su planilla a la empresa ajena."""
    pendiente = IniciarVinculacionConGoogle(proveedor).ejecutar(rol=RolUsuario.ADMINISTRADOR)

    assert pendiente.estado
    assert pendiente.estado in pendiente.url
