"""Los tres guardas anti-bucle de HU-E3-07, y la pausa por cambio de estructura.

Este archivo prueba, sobre todo, **que el sistema no se coma su propia cola**. Un
write-back que escribiera en la hoja que también lee ingeriría su propia salida en el
barrido siguiente, para siempre. Los tres guardas de ADR-007 se prueban de a uno porque
cada uno tiene que alcanzar por su cuenta: que dos estén bien no es excusa para que el
tercero esté flojo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import huella_de
from cheatsheet.contexts.spreadsheet_sync.application.ports import FilaParaEscribir
from cheatsheet.contexts.spreadsheet_sync.application.sincronizacion import (
    HOJA_DE_CHEATSHEET,
    MENSAJE_ESTRUCTURA_CAMBIO,
    DetectarCambioDeEstructura,
    EscribirDeVueltaEnPlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import EntradaDeMapeo, EstadoMapeo, Mapeo
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    DireccionSync,
    ProveedorPlanilla,
    ReferenciaDeArchivo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.escritura import EscrituraSimulada
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import EventoDeDominio

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
COLUMNAS = ("Cliente", "CUIT")


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


class MapeosFalsos:
    def __init__(self, mapeo: Mapeo) -> None:
        self.mapeo = mapeo

    async def agregar(self, mapeo: Mapeo) -> None: ...

    async def actualizar(self, mapeo: Mapeo) -> None:
        self.mapeo = mapeo

    async def buscar_por_id(self, mapeo_id: UUID) -> Mapeo | None:
        return self.mapeo if mapeo_id == self.mapeo.id else None

    async def buscar_por_huella(self, huella: str) -> Mapeo | None:
        return self.mapeo if huella == self.mapeo.huella_encabezado else None


class RegistrosFalsos:
    """Records what it was asked for, so a test can prove it was never asked."""

    def __init__(self, filas: tuple[FilaParaEscribir, ...] = ()) -> None:
        self.filas = filas
        self.consultas = 0

    async def pendientes_de_escritura(
        self, *, desde: datetime | None
    ) -> tuple[FilaParaEscribir, ...]:
        del desde
        self.consultas += 1
        return self.filas


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def _mapeo() -> Mapeo:
    mapeo = Mapeo(
        id=uuid4(),
        empresa_id=EMPRESA,
        huella_encabezado=huella_de(COLUMNAS),
        entradas=[
            EntradaDeMapeo(
                id=uuid4(),
                columna_origen="Cliente",
                atributo_destino="nombre",
                score=Decimal("0.97"),
            )
        ],
        created_at=AHORA,
        updated_at=AHORA,
    )
    mapeo.confirmar(obligatorios=frozenset({"nombre"}), ahora=AHORA)
    return mapeo


def _vinculo(
    *,
    proveedor: ProveedorPlanilla = ProveedorPlanilla.GOOGLE_SHEETS,
    direccion: DireccionSync = DireccionSync.LECTURA_Y_ESCRITURA,
    mapeo_id: UUID | None = None,
) -> VinculoDePlanilla:
    extra: dict[str, object] = {}
    if proveedor is ProveedorPlanilla.ARCHIVO:
        extra = {
            "archivo": ReferenciaDeArchivo(
                clave="k", nombre_original="clientes.xlsx", tamano_bytes=10
            ),
            "identificador_externo": None,
        }
    else:
        extra = {"identificador_externo": "1AbCdEf"}

    vinculo = VinculoDePlanilla(
        id=uuid4(),
        empresa_id=EMPRESA,
        proveedor=proveedor,
        direccion=direccion,
        hoja_empresa="Clientes",
        created_at=AHORA,
        updated_at=AHORA,
        **extra,  # type: ignore[arg-type]
    )
    if mapeo_id is not None:
        vinculo.asignar_mapeo(mapeo_id, ahora=AHORA)
    return vinculo


FILA = FilaParaEscribir(valores=("Panaderia Rosa", "30712345671", "", "", "PANEL"))


# --- Guarda 1: sólo LECTURA_Y_ESCRITURA -------------------------------------------


async def test_un_vinculo_de_solo_lectura_no_se_escribe_ni_se_consulta() -> None:
    """Guarda 1 (RN-01), y algo más: no se le pregunta a `master_data`.

    Consultar y después descartar sería una query que nadie necesitaba, por empresa y
    por corrida.
    """
    vinculos = VinculosFalsos(_vinculo(direccion=DireccionSync.SOLO_LECTURA))
    registros = RegistrosFalsos((FILA,))
    escritura = EscrituraSimulada()

    resultado = await EscribirDeVueltaEnPlanilla(
        vinculos=vinculos,
        registros=registros,
        escritura=escritura,
        publicador=PublicadorFalso(),
    ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculos.vinculo.id, ahora=AHORA)

    assert resultado.filas_escritas == 0
    assert escritura.escrituras == []
    assert registros.consultas == 0


async def test_un_vinculo_pausado_por_permisos_no_vuelve_a_escribir() -> None:
    vinculo = _vinculo()
    vinculo.pausar(motivo="Google ya no permite escribir", ahora=AHORA)
    escritura = EscrituraSimulada()
    registros = RegistrosFalsos((FILA,))

    resultado = await EscribirDeVueltaEnPlanilla(
        vinculos=VinculosFalsos(vinculo),
        registros=registros,
        escritura=escritura,
        publicador=PublicadorFalso(),
    ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculo.id, ahora=AHORA)

    assert resultado.filas_escritas == 0
    assert registros.consultas == 0
    assert escritura.escrituras == []


@pytest.mark.parametrize("proveedor", [ProveedorPlanilla.EXCEL_ONLINE, ProveedorPlanilla.ARCHIVO])
async def test_excel_online_y_un_archivo_nunca_se_escriben(
    proveedor: ProveedorPlanilla,
) -> None:
    """Cuarto criterio de HU-E3-07: sólo Google Sheets.

    El agregado ya impide construirlos con `LECTURA_Y_ESCRITURA`, así que llegan acá como
    `SOLO_LECTURA` y el caso de uso los descarta. Dos capas, una regla.
    """
    vinculos = VinculosFalsos(_vinculo(proveedor=proveedor, direccion=DireccionSync.SOLO_LECTURA))
    escritura = EscrituraSimulada()

    await EscribirDeVueltaEnPlanilla(
        vinculos=vinculos,
        registros=RegistrosFalsos((FILA,)),
        escritura=escritura,
        publicador=PublicadorFalso(),
    ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculos.vinculo.id, ahora=AHORA)

    assert escritura.escrituras == []


# --- Guarda 2: sólo la hoja propia ------------------------------------------------


async def test_se_escribe_en_la_hoja_de_cheatsheet_y_nunca_en_la_de_la_empresa() -> None:
    """Guarda 2 (RN-02), y el mecanismo anti-bucle de ADR-007.

    Es el guarda **estructural**: lo que escribimos cae en un lugar que nunca leemos, así
    que el bucle es imposible en lugar de improbable.
    """
    vinculos = VinculosFalsos(_vinculo())
    escritura = EscrituraSimulada()

    resultado = await EscribirDeVueltaEnPlanilla(
        vinculos=vinculos,
        registros=RegistrosFalsos((FILA,)),
        escritura=escritura,
        publicador=PublicadorFalso(),
    ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculos.vinculo.id, ahora=AHORA)

    assert resultado.filas_escritas == 1
    (_, hoja, _) = escritura.escrituras[0]
    assert hoja == f"{HOJA_DE_CHEATSHEET} {vinculos.vinculo.id.hex[:8]}"
    assert hoja != vinculos.vinculo.hoja_empresa
    # Y queda registrada en el vínculo, para que la próxima corrida use la misma.
    assert vinculos.vinculo.hoja_cheatsheet == hoja
    assert vinculos.vinculo.ultima_escritura == AHORA


async def test_la_hoja_ya_creada_se_reusa() -> None:
    vinculo = _vinculo()
    vinculo.hoja_cheatsheet = "CheatSheet (no editar)"
    vinculos = VinculosFalsos(vinculo)
    escritura = EscrituraSimulada()

    await EscribirDeVueltaEnPlanilla(
        vinculos=vinculos,
        registros=RegistrosFalsos((FILA,)),
        escritura=escritura,
        publicador=PublicadorFalso(),
    ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculo.id, ahora=AHORA)

    assert escritura.escrituras[0][1] == "CheatSheet (no editar)"


async def test_una_actualizacion_conserva_los_registros_ya_escritos() -> None:
    """Replacing A1 with only the changed rows would erase older panel records."""
    vinculo = _vinculo()
    vinculo.ultima_escritura = AHORA - timedelta(hours=1)
    vinculos = VinculosFalsos(vinculo)

    class RegistrosPorFecha(RegistrosFalsos):
        async def pendientes_de_escritura(
            self, *, desde: datetime | None
        ) -> tuple[FilaParaEscribir, ...]:
            self.consultas += 1
            if desde is None:
                return (FILA, FilaParaEscribir(valores=("New customer", "", "", "", "PANEL")))
            return (FilaParaEscribir(valores=("New customer", "", "", "", "PANEL")),)

    escritura = EscrituraSimulada()
    await EscribirDeVueltaEnPlanilla(
        vinculos=vinculos,
        registros=RegistrosPorFecha(),
        escritura=escritura,
        publicador=PublicadorFalso(),
    ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculo.id, ahora=AHORA)

    assert escritura.escrituras == [("1AbCdEf", f"{HOJA_DE_CHEATSHEET} {vinculo.id.hex[:8]}", 2)]


async def test_una_escritura_fallida_no_adelanta_la_marca() -> None:
    vinculos = VinculosFalsos(_vinculo())

    class EscrituraFallida:
        async def escribir(
            self, *, identificador: str, hoja: str, filas: tuple[FilaParaEscribir, ...]
        ) -> None:
            assert identificador == "1AbCdEf"
            assert hoja.startswith(HOJA_DE_CHEATSHEET)
            assert filas == (FILA,)
            raise RuntimeError("second batch failed")

    with pytest.raises(RuntimeError, match="second batch failed"):
        await EscribirDeVueltaEnPlanilla(
            vinculos=vinculos,
            registros=RegistrosFalsos((FILA,)),
            escritura=EscrituraFallida(),
            publicador=PublicadorFalso(),
        ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculos.vinculo.id, ahora=AHORA)

    assert vinculos.vinculo.ultima_escritura is None


async def test_sin_registros_pendientes_no_se_toca_la_planilla() -> None:
    """Una llamada a Google por empresa y por hora, para no escribir nada, es una llamada
    que no vale la pena hacer."""
    vinculos = VinculosFalsos(_vinculo())
    escritura = EscrituraSimulada()

    resultado = await EscribirDeVueltaEnPlanilla(
        vinculos=vinculos,
        registros=RegistrosFalsos(()),
        escritura=escritura,
        publicador=PublicadorFalso(),
    ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculos.vinculo.id, ahora=AHORA)

    assert escritura.escrituras == []
    assert not resultado.hubo_escritura
    assert vinculos.vinculo.ultima_escritura is None


async def test_la_escritura_queda_auditada() -> None:
    vinculos = VinculosFalsos(_vinculo())
    publicador = PublicadorFalso()

    await EscribirDeVueltaEnPlanilla(
        vinculos=vinculos,
        registros=RegistrosFalsos((FILA,)),
        escritura=EscrituraSimulada(),
        publicador=publicador,
    ).ejecutar(empresa_id=EMPRESA, vinculo_id=vinculos.vinculo.id, ahora=AHORA)

    assert len(publicador.eventos) == 1
    # El planificador escribió, no una persona.
    assert publicador.eventos[0].usuario_id is None  # type: ignore[attr-defined]


# --- HU-E3-04 RN-03: la estructura cambió -----------------------------------------


async def test_el_mismo_encabezado_no_pausa_nada() -> None:
    mapeo = _mapeo()
    vinculos = VinculosFalsos(_vinculo(mapeo_id=mapeo.id))

    pausado = await DetectarCambioDeEstructura(
        vinculos=vinculos, mapeos=MapeosFalsos(mapeo), publicador=PublicadorFalso()
    ).ejecutar(vinculo_id=vinculos.vinculo.id, columnas=COLUMNAS, ahora=AHORA)

    assert not pausado
    assert not vinculos.vinculo.pausado


async def test_una_columna_renombrada_pausa_la_sincronizacion_con_el_texto_de_la_historia() -> None:
    """RN-03. Pausar y no re-mapear solo: la empresa tiene que ver qué pasó.

    La alternativa es cuarenta mil filas cayendo en los campos equivocados, en un horario
    que nadie está mirando.
    """
    mapeo = _mapeo()
    vinculos = VinculosFalsos(_vinculo(mapeo_id=mapeo.id))
    mapeos = MapeosFalsos(mapeo)
    publicador = PublicadorFalso()

    pausado = await DetectarCambioDeEstructura(
        vinculos=vinculos, mapeos=mapeos, publicador=publicador
    ).ejecutar(vinculo_id=vinculos.vinculo.id, columnas=("Razon Social", "CUIT"), ahora=AHORA)

    assert pausado
    assert vinculos.vinculo.pausado
    assert vinculos.vinculo.motivo_de_pausa == MENSAJE_ESTRUCTURA_CAMBIO
    assert not vinculos.vinculo.admite_sincronizacion_incremental
    # El mapeo vuelve a borrador con sus entradas: rehacer cuarenta asignaciones por una
    # columna renombrada es cómo una pausa se convierte en un abandono.
    assert mapeos.mapeo.estado is EstadoMapeo.BORRADOR
    assert mapeos.mapeo.version == 2
    assert len(mapeos.mapeo.entradas) == 1
    # RN-02: el evento queda en la bitácora con estado de error.
    assert len(publicador.eventos) == 1


async def test_un_vinculo_sin_mapeo_no_se_pausa() -> None:
    """No hay nada que revisar todavía: el usuario ni siquiera confirmó el primer mapeo."""
    mapeo = _mapeo()
    vinculos = VinculosFalsos(_vinculo())

    pausado = await DetectarCambioDeEstructura(
        vinculos=vinculos, mapeos=MapeosFalsos(mapeo), publicador=PublicadorFalso()
    ).ejecutar(vinculo_id=vinculos.vinculo.id, columnas=("otra",), ahora=AHORA)

    assert not pausado


async def test_reordenar_las_columnas_tambien_pausa() -> None:
    """El orden es parte de la estructura: los datos caerían en otros campos."""
    mapeo = _mapeo()
    vinculos = VinculosFalsos(_vinculo(mapeo_id=mapeo.id))

    pausado = await DetectarCambioDeEstructura(
        vinculos=vinculos, mapeos=MapeosFalsos(mapeo), publicador=PublicadorFalso()
    ).ejecutar(vinculo_id=vinculos.vinculo.id, columnas=("CUIT", "Cliente"), ahora=AHORA)

    assert pausado


async def test_un_vinculo_pausado_deja_de_ser_candidato_al_barrido() -> None:
    """Lo que el índice parcial y la función `SECURITY DEFINER` filtran del lado del motor."""
    vinculo = _vinculo(mapeo_id=uuid4())
    assert vinculo.admite_sincronizacion_incremental

    vinculo.pausar(motivo=MENSAJE_ESTRUCTURA_CAMBIO, ahora=AHORA + timedelta(minutes=1))

    assert not vinculo.admite_sincronizacion_incremental
