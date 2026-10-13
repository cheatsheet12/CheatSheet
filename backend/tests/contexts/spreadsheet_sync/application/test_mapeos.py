"""Los casos de uso del mapeo, y sobre todo lo que pasa cuando el modelo no contesta.

Tres propiedades se prueban acá porque no viven en ningún otro lado:

1. **Al modelo se le mandan encabezados y nada más** (decisión D12). El doble registra lo
   que recibió, y el test afirma que no llegó un solo dato de una fila.
2. **Un modelo caído no bloquea la ingesta** (ADR-0007). Degrada a «todo Sin asignar».
3. **Un mapeo guardado se reutiliza sin llamar al modelo** (RN-02), que es el tercer
   criterio de aceptación de HU-E3-01 y además lo que evita pagar una llamada por día.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import (
    ConfirmarMapeo,
    CorregirMapeo,
    ProponerMapeo,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import Asignacion
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import Mapeo, NivelDeConfianza
from cheatsheet.contexts.spreadsheet_sync.domain.valores import DireccionSync, ProveedorPlanilla
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.modelo import ModeloDeLenguajeSimulado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada, OperacionNoPermitida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
COLUMNAS = ("Razon Social", "CUIT", "Celular")


class MapeosFalsos:
    def __init__(self) -> None:
        self.mapeos: dict[UUID, Mapeo] = {}

    async def agregar(self, mapeo: Mapeo) -> None:
        self.mapeos[mapeo.id] = mapeo

    async def actualizar(self, mapeo: Mapeo) -> None:
        self.mapeos[mapeo.id] = mapeo

    async def buscar_por_id(self, mapeo_id: UUID) -> Mapeo | None:
        return self.mapeos.get(mapeo_id)

    async def buscar_por_huella(self, huella: str) -> Mapeo | None:
        return next((m for m in self.mapeos.values() if m.huella_encabezado == huella), None)


class VinculosFalsos:
    def __init__(self, vinculo: VinculoDePlanilla) -> None:
        self.vinculo = vinculo

    async def agregar(self, vinculo: VinculoDePlanilla) -> None: ...

    async def actualizar(self, vinculo: VinculoDePlanilla) -> None:
        self.vinculo = vinculo

    async def buscar_por_id(self, vinculo_id: UUID) -> VinculoDePlanilla | None:
        return self.vinculo if vinculo_id == self.vinculo.id else None

    async def listar(self) -> list[VinculoDePlanilla]:
        return [self.vinculo]

    async def eliminar(self, vinculo_id: UUID) -> None: ...


class ModeloEspia:
    """Records what it was asked, so the test can assert what the model never saw."""

    def __init__(self, respuesta: tuple[Asignacion, ...] = ()) -> None:
        self.respuesta = respuesta
        self.llamadas: list[dict[str, tuple[str, ...]]] = []

    async def proponer_mapeo(
        self, *, columnas: tuple[str, ...], atributos: tuple[str, ...]
    ) -> tuple[Asignacion, ...]:
        self.llamadas.append({"columnas": columnas, "atributos": atributos})
        return self.respuesta


class ModeloCaido:
    """ADR-0007's degradation path: the port returns nothing rather than raising."""

    async def proponer_mapeo(
        self, *, columnas: tuple[str, ...], atributos: tuple[str, ...]
    ) -> tuple[Asignacion, ...]:
        del columnas, atributos
        return ()


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def _vinculo() -> VinculoDePlanilla:
    return VinculoDePlanilla(
        id=uuid4(),
        empresa_id=EMPRESA,
        proveedor=ProveedorPlanilla.GOOGLE_SHEETS,
        direccion=DireccionSync.SOLO_LECTURA,
        hoja_empresa="Clientes",
        identificador_externo="1AbCdEf",
        created_at=AHORA,
        updated_at=AHORA,
    )


@pytest.fixture
def mapeos() -> MapeosFalsos:
    return MapeosFalsos()


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


async def _proponer(
    mapeos: MapeosFalsos, publicador: PublicadorFalso, modelo: object, vinculos: VinculosFalsos
) -> object:
    return await ProponerMapeo(
        mapeos=mapeos,
        vinculos=vinculos,
        modelo=modelo,  # type: ignore[arg-type]
        publicador=publicador,
    ).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        vinculo_id=vinculos.vinculo.id,
        columnas=COLUMNAS,
        ejemplos={"CUIT": "30712345671", "Celular": "+5493511234567"},
        ahora=AHORA,
    )


async def test_al_modelo_solo_le_llegan_los_nombres_de_las_columnas(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """Decisión D12, y `CLAUDE.md` §3.6.

    Los ejemplos que se le pasan al caso de uso son un CUIT y un teléfono reales. Tienen
    que terminar en la pantalla y **no** en la llamada al modelo. Este test es la única
    cosa que lo garantiza: la regla es de una línea y se rompe sin que nada falle.
    """
    modelo = ModeloEspia()
    vinculos = VinculosFalsos(_vinculo())

    await _proponer(mapeos, publicador, modelo, vinculos)

    assert len(modelo.llamadas) == 1
    enviado = repr(modelo.llamadas[0])
    assert "30712345671" not in enviado
    assert "+5493511234567" not in enviado
    assert modelo.llamadas[0]["columnas"] == COLUMNAS


async def test_los_ejemplos_igual_llegan_a_la_pantalla(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """El otro lado de D12: el criterio de HU-E3-02 pide mostrar un ejemplo por columna."""
    vista = await _proponer(mapeos, publicador, ModeloEspia(), VinculosFalsos(_vinculo()))

    ejemplos = {e.columna_origen: e.ejemplo for e in vista.mapeo.entradas}  # type: ignore[attr-defined]
    assert ejemplos["CUIT"] == "30712345671"
    assert ejemplos["Razon Social"] is None


async def test_un_modelo_caido_deja_todo_sin_asignar_y_no_bloquea(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """ADR-0007. Una caída de un proveedor cuesta mapear a mano, no una ingesta detenida."""
    vista = await _proponer(mapeos, publicador, ModeloCaido(), VinculosFalsos(_vinculo()))

    assert not vista.propuesto_por_el_modelo  # type: ignore[attr-defined]
    assert all(not e.esta_asignada for e in vista.mapeo.entradas)  # type: ignore[attr-defined]
    assert all(
        e.confianza is NivelDeConfianza.BAJA
        for e in vista.mapeo.entradas  # type: ignore[attr-defined]
    )
    # Y sin embargo el mapeo existe y está guardado: la pantalla tiene sobre qué trabajar.
    assert len(mapeos.mapeos) == 1


async def test_una_confianza_baja_queda_sin_asignar_aunque_el_modelo_haya_propuesto(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """RN-03. El umbral se aplica en el caso de uso, no en quien lee el score."""
    modelo = ModeloEspia(
        (
            Asignacion(columna="Razon Social", atributo="nombre", score=Decimal("0.96")),
            Asignacion(columna="CUIT", atributo="cuit", score=Decimal("0.40")),
        )
    )

    vista = await _proponer(mapeos, publicador, modelo, VinculosFalsos(_vinculo()))

    por_columna = {e.columna_origen: e for e in vista.mapeo.entradas}  # type: ignore[attr-defined]
    assert por_columna["Razon Social"].atributo_destino == "nombre"
    assert por_columna["CUIT"].atributo_destino is None


async def test_un_mapeo_guardado_se_reutiliza_sin_llamar_al_modelo(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """Tercer criterio de HU-E3-01, y lo que evita pagar una llamada por sincronización."""
    modelo = ModeloEspia(
        (Asignacion(columna="Razon Social", atributo="nombre", score=Decimal("0.96")),)
    )
    vinculos = VinculosFalsos(_vinculo())

    primera = await _proponer(mapeos, publicador, modelo, vinculos)
    segunda = await _proponer(mapeos, publicador, modelo, vinculos)

    assert len(modelo.llamadas) == 1
    assert segunda.mapeo.id == primera.mapeo.id  # type: ignore[attr-defined]
    assert not segunda.propuesto_por_el_modelo  # type: ignore[attr-defined]


async def test_solo_lectura_no_corrige_ni_confirma(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """HU-E3-01 y HU-E3-02: «Administrador u Operador». Solo Lectura mira."""
    vista = await _proponer(mapeos, publicador, ModeloEspia(), VinculosFalsos(_vinculo()))
    mapeo_id = vista.mapeo.id  # type: ignore[attr-defined]

    with pytest.raises(OperacionNoPermitida):
        await CorregirMapeo(mapeos).ejecutar(
            mapeo_id=mapeo_id,
            rol=RolUsuario.SOLO_LECTURA,
            columna="CUIT",
            atributo="cuit",
            ahora=AHORA,
        )

    with pytest.raises(OperacionNoPermitida):
        await ConfirmarMapeo(mapeos=mapeos, publicador=publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.SOLO_LECTURA,
            mapeo_id=mapeo_id,
            ahora=AHORA,
        )


async def test_un_operador_corrige_y_confirma(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """Más ancho que HU-E2-04, y es de las historias: mapear es trabajo del día a día."""
    vista = await _proponer(mapeos, publicador, ModeloCaido(), VinculosFalsos(_vinculo()))
    mapeo_id = vista.mapeo.id  # type: ignore[attr-defined]

    corregido = await CorregirMapeo(mapeos).ejecutar(
        mapeo_id=mapeo_id,
        rol=RolUsuario.OPERADOR,
        columna="Razon Social",
        atributo="nombre",
        ahora=AHORA,
    )
    assert corregido.puede_confirmarse

    confirmado = await ConfirmarMapeo(mapeos=mapeos, publicador=publicador).ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=RolUsuario.OPERADOR,
        mapeo_id=mapeo_id,
        ahora=AHORA,
    )
    assert confirmado.esta_confirmado


async def test_no_se_confirma_con_una_obligatoria_sin_asignar(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """RN-02, de punta a punta: el modelo no supo, nadie corrigió, no se procesa."""
    vista = await _proponer(mapeos, publicador, ModeloCaido(), VinculosFalsos(_vinculo()))

    with pytest.raises(InvarianteViolada):
        await ConfirmarMapeo(mapeos=mapeos, publicador=publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            mapeo_id=vista.mapeo.id,  # type: ignore[attr-defined]
            ahora=AHORA,
        )


async def test_corregir_a_un_atributo_inexistente_es_rechazado(
    mapeos: MapeosFalsos, publicador: PublicadorFalso
) -> None:
    """El catálogo de destinos es cerrado: escribir en un campo que no existe no es un
    error del usuario que valga la pena propagar hasta el procesamiento."""
    vista = await _proponer(mapeos, publicador, ModeloEspia(), VinculosFalsos(_vinculo()))

    with pytest.raises(EntradaInvalida):
        await CorregirMapeo(mapeos).ejecutar(
            mapeo_id=vista.mapeo.id,  # type: ignore[attr-defined]
            rol=RolUsuario.OPERADOR,
            columna="CUIT",
            atributo="campo_inventado",
            ahora=AHORA,
        )


async def test_el_simulado_propone_algo_util_y_nunca_confianza_alta() -> None:
    """El adaptador que corre en una laptop: alcanza para recorrer el flujo, y se nota.

    El techo por debajo del umbral de «Alta» es a propósito — una corrida local muestra
    el mismo estado de revisión que muestra la pantalla real.
    """
    simulado = ModeloDeLenguajeSimulado()

    propuestas = await simulado.proponer_mapeo(
        columnas=("nombre", "cuit", "xyz"), atributos=("nombre", "cuit", "contacto_email")
    )

    por_columna = {p.columna: p for p in propuestas}
    assert por_columna["nombre"].atributo == "nombre"
    assert por_columna["cuit"].atributo == "cuit"
    assert all(p.score <= ModeloDeLenguajeSimulado.TECHO_DE_SIMILITUD for p in propuestas)
