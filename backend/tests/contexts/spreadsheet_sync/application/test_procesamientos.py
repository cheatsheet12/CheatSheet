"""El procesamiento de una planilla, y la regla que define la unidad entera.

HU-E3-03 RN-02: **una fila inválida se marca y no aborta el resto**. Cuarenta mil filas y
un CUIT mal formado tienen que dar 39.999 clientes y una línea que dice cuál falló. Eso es
lo que prueban los tres primeros tests; todo lo demás de este archivo existe para que esa
garantía no se rompa sin que nadie se entere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import huella_de
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    FilaLeida,
    FilaParaIngerir,
    PlanillaLeida,
)
from cheatsheet.contexts.spreadsheet_sync.application.procesamientos import (
    ConsultarProcesamiento,
    ListarProcesamientos,
    PrepararReproceso,
    ProcesarPlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import EntradaDeMapeo, Mapeo
from cheatsheet.contexts.spreadsheet_sync.domain.procesamiento import (
    EstadoProcesamiento,
    ProcesamientoDePlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    DireccionSync,
    ProveedorPlanilla,
    ReferenciaDeArchivo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import (
    EntradaInvalida,
    ErrorDeDominio,
    InvarianteViolada,
    OperacionNoPermitida,
)
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
COLUMNAS = ("Cliente", "CUIT")


class ProcesamientosFalsos:
    def __init__(self) -> None:
        self.guardados: dict[UUID, ProcesamientoDePlanilla] = {}

    async def agregar(self, procesamiento: ProcesamientoDePlanilla) -> None:
        self.guardados[procesamiento.id] = procesamiento

    async def actualizar(self, procesamiento: ProcesamientoDePlanilla) -> None:
        self.guardados[procesamiento.id] = procesamiento

    async def buscar_por_id(self, procesamiento_id: UUID) -> ProcesamientoDePlanilla | None:
        return self.guardados.get(procesamiento_id)

    async def listar(self, *, vinculo_id: UUID | None = None) -> list[ProcesamientoDePlanilla]:
        todos = list(self.guardados.values())
        if vinculo_id is None:
            return todos
        return [p for p in todos if p.vinculo_id == vinculo_id]


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

    async def actualizar(self, mapeo: Mapeo) -> None: ...

    async def buscar_por_id(self, mapeo_id: UUID) -> Mapeo | None:
        return self.mapeo if mapeo_id == self.mapeo.id else None

    async def buscar_por_huella(self, huella: str) -> Mapeo | None:
        return self.mapeo if huella == self.mapeo.huella_encabezado else None


class LectorFalso:
    def __init__(self, planilla: PlanillaLeida | None = None, error: str | None = None) -> None:
        self.planilla = planilla
        self.error = error

    def leer(self, *, contenido: bytes, nombre: str) -> PlanillaLeida:
        del contenido, nombre
        if self.error is not None:
            raise EntradaInvalida(self.error)
        assert self.planilla is not None
        return self.planilla


class CatalogoFalso:
    """Fails on the rows whose CUIT is in `rechaza`, like the real ingestion would."""

    def __init__(self, rechaza: frozenset[str] = frozenset()) -> None:
        self.rechaza = rechaza
        self.ingeridas: list[dict[str, str]] = []

    async def ingerir(
        self, *, empresa_id: EmpresaId, fila: FilaParaIngerir, ahora: datetime
    ) -> None:
        del empresa_id, ahora
        if fila.valores.get("cuit") in self.rechaza:
            raise ErrorDeDominio(f"CUIT invalido: {fila.valores.get('cuit')}")
        self.ingeridas.append(fila.valores)


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def _mapeo_confirmado() -> Mapeo:
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
            ),
            EntradaDeMapeo(
                id=uuid4(), columna_origen="CUIT", atributo_destino="cuit", score=Decimal("0.99")
            ),
        ],
        created_at=AHORA,
        updated_at=AHORA,
    )
    mapeo.confirmar(obligatorios=frozenset({"nombre"}), ahora=AHORA)
    return mapeo


def _vinculo(mapeo_id: UUID) -> VinculoDePlanilla:
    vinculo = VinculoDePlanilla(
        id=uuid4(),
        empresa_id=EMPRESA,
        proveedor=ProveedorPlanilla.ARCHIVO,
        direccion=DireccionSync.SOLO_LECTURA,
        hoja_empresa="clientes.xlsx",
        archivo=ReferenciaDeArchivo(
            clave="planillas/x/y.xlsx", nombre_original="clientes.xlsx", tamano_bytes=100
        ),
        created_at=AHORA,
        updated_at=AHORA,
    )
    vinculo.asignar_mapeo(mapeo_id, ahora=AHORA)
    return vinculo


def _planilla(*filas: tuple[int, str, str]) -> PlanillaLeida:
    return PlanillaLeida(
        columnas=COLUMNAS,
        filas=tuple(
            FilaLeida(numero=numero, celdas={"Cliente": nombre, "CUIT": cuit})
            for numero, nombre, cuit in filas
        ),
    )


async def _correr(
    *,
    planilla: PlanillaLeida | None = None,
    error_de_lectura: str | None = None,
    rechaza: frozenset[str] = frozenset(),
    solo_filas: tuple[int, ...] | None = None,
) -> tuple[ProcesamientoDePlanilla, CatalogoFalso, ProcesamientosFalsos]:
    mapeo = _mapeo_confirmado()
    vinculos = VinculosFalsos(_vinculo(mapeo.id))
    procesamientos = ProcesamientosFalsos()
    catalogo = CatalogoFalso(rechaza)

    resumen = await ProcesarPlanilla(
        procesamientos=procesamientos,
        vinculos=vinculos,
        mapeos=MapeosFalsos(mapeo),
        lector=LectorFalso(planilla, error_de_lectura),
        catalogo=catalogo,
        publicador=PublicadorFalso(),
    ).ejecutar(
        empresa_id=EMPRESA,
        vinculo_id=vinculos.vinculo.id,
        contenido=b"x",
        nombre_de_archivo="clientes.xlsx",
        ahora=AHORA,
        solo_filas=solo_filas,
    )
    return resumen.procesamiento, catalogo, procesamientos


async def test_una_fila_invalida_no_aborta_el_resto() -> None:
    """RN-02, y la razón de ser de la unidad.

    Tres filas, la del medio con un CUIT que la ingesta rechaza. Tienen que entrar dos
    clientes y quedar registrada una línea con **el número de fila del archivo original**.
    """
    procesamiento, catalogo, _ = await _correr(
        planilla=_planilla(
            (2, "Panaderia Rosa", "30712345671"),
            (3, "Kiosco Luis", "roto"),
            (4, "Bar Central", "20123456786"),
        ),
        rechaza=frozenset({"roto"}),
    )

    assert len(catalogo.ingeridas) == 2
    assert procesamiento.filas_totales == 3
    assert procesamiento.filas_ok == 2
    assert procesamiento.filas_error == 1
    assert procesamiento.estado is EstadoProcesamiento.CON_ERRORES
    # El número que el usuario va a buscar en su propia planilla.
    assert procesamiento.errores[0].numero_fila == 3


async def test_sin_errores_el_estado_es_completado() -> None:
    procesamiento, catalogo, _ = await _correr(
        planilla=_planilla((2, "Panaderia Rosa", "30712345671"))
    )

    assert procesamiento.estado is EstadoProcesamiento.COMPLETADO
    assert procesamiento.filas_ok == 1
    assert len(catalogo.ingeridas) == 1


async def test_muchas_filas_rotas_no_frenan_las_buenas() -> None:
    """La versión grande del caso 1: la mitad falla y la otra mitad entra igual."""
    filas = tuple(
        (numero, f"Cliente {numero}", "roto" if numero % 2 else "30712345671")
        for numero in range(2, 22)
    )
    procesamiento, catalogo, _ = await _correr(
        planilla=_planilla(*filas), rechaza=frozenset({"roto"})
    )

    assert procesamiento.filas_totales == 20
    assert procesamiento.filas_ok == 10
    assert procesamiento.filas_error == 10
    assert len(catalogo.ingeridas) == 10


async def test_un_archivo_ilegible_es_fallido_y_no_con_errores() -> None:
    """Son finales distintos: acá no se ingirió nada y no hay filas que corregir."""
    procesamiento, catalogo, _ = await _correr(error_de_lectura="El archivo esta corrupto")

    assert procesamiento.estado is EstadoProcesamiento.FALLIDO
    assert catalogo.ingeridas == []
    assert procesamiento.filas_ok == 0


async def test_no_se_procesa_sin_un_mapeo_confirmado() -> None:
    """Precondición de RN-01. Procesar sobre un borrador escribiría cuarenta mil filas
    con asignaciones que nadie aprobó."""
    mapeo = Mapeo(
        id=uuid4(),
        empresa_id=EMPRESA,
        huella_encabezado="abc",
        entradas=[],
        created_at=AHORA,
        updated_at=AHORA,
    )
    vinculos = VinculosFalsos(_vinculo(mapeo.id))

    with pytest.raises(InvarianteViolada):
        await ProcesarPlanilla(
            procesamientos=ProcesamientosFalsos(),
            vinculos=vinculos,
            mapeos=MapeosFalsos(mapeo),
            lector=LectorFalso(_planilla((2, "x", "y"))),
            catalogo=CatalogoFalso(),
            publicador=PublicadorFalso(),
        ).ejecutar(
            empresa_id=EMPRESA,
            vinculo_id=vinculos.vinculo.id,
            contenido=b"x",
            nombre_de_archivo="clientes.xlsx",
            ahora=AHORA,
        )


async def test_las_columnas_sin_asignar_no_llegan_al_catalogo() -> None:
    """`Sin asignar` significa que el usuario decidió que esa columna no va a ningún lado."""
    mapeo = _mapeo_confirmado()
    mapeo.estado = mapeo.estado  # ya confirmado
    # La entrada de CUIT se desasigna a mano, como haría el usuario en PAN-ING-02.
    mapeo.entradas[1].atributo_destino = None

    vinculos = VinculosFalsos(_vinculo(mapeo.id))
    catalogo = CatalogoFalso()
    await ProcesarPlanilla(
        procesamientos=ProcesamientosFalsos(),
        vinculos=vinculos,
        mapeos=MapeosFalsos(mapeo),
        lector=LectorFalso(_planilla((2, "Panaderia Rosa", "30712345671"))),
        catalogo=catalogo,
        publicador=PublicadorFalso(),
    ).ejecutar(
        empresa_id=EMPRESA,
        vinculo_id=vinculos.vinculo.id,
        contenido=b"x",
        nombre_de_archivo="clientes.xlsx",
        ahora=AHORA,
    )

    assert catalogo.ingeridas == [{"nombre": "Panaderia Rosa"}]


async def test_un_reproceso_solo_lee_las_filas_indicadas() -> None:
    """HU-E3-06 RN-02: no duplica lo ya procesado bien."""
    _, catalogo, _ = await _correr(
        planilla=_planilla(
            (2, "Panaderia Rosa", "30712345671"),
            (3, "Kiosco Luis", "20123456786"),
            (4, "Bar Central", "27123456784"),
        ),
        solo_filas=(3,),
    )

    assert len(catalogo.ingeridas) == 1
    assert catalogo.ingeridas[0]["nombre"] == "Kiosco Luis"


async def test_preparar_el_reproceso_devuelve_las_filas_que_fallaron() -> None:
    procesamiento, _, procesamientos = await _correr(
        planilla=_planilla(
            (2, "Panaderia Rosa", "30712345671"),
            (3, "Kiosco Luis", "roto"),
            (5, "Bar Central", "roto"),
        ),
        rechaza=frozenset({"roto"}),
    )

    original, filas = await PrepararReproceso(procesamientos).ejecutar(
        procesamiento_id=procesamiento.id, rol=RolUsuario.OPERADOR
    )

    assert original.id == procesamiento.id
    assert filas == (3, 5)


async def test_no_se_reprocesa_lo_que_no_dejo_errores() -> None:
    """Empezar una corrida que no va a ingerir nada es peor que decir que no hay nada."""
    procesamiento, _, procesamientos = await _correr(
        planilla=_planilla((2, "Panaderia Rosa", "30712345671"))
    )

    with pytest.raises(EntradaInvalida):
        await PrepararReproceso(procesamientos).ejecutar(
            procesamiento_id=procesamiento.id, rol=RolUsuario.OPERADOR
        )


async def test_solo_lectura_no_reprocesa() -> None:
    """HU-E3-05 RN-04: ve el resultado «sin la opción de reprocesar»."""
    procesamiento, _, procesamientos = await _correr(
        planilla=_planilla((2, "Kiosco Luis", "roto")), rechaza=frozenset({"roto"})
    )

    with pytest.raises(OperacionNoPermitida):
        await PrepararReproceso(procesamientos).ejecutar(
            procesamiento_id=procesamiento.id, rol=RolUsuario.SOLO_LECTURA
        )


async def test_consultar_y_listar_devuelven_lo_guardado() -> None:
    procesamiento, _, procesamientos = await _correr(
        planilla=_planilla((2, "Kiosco Luis", "roto")), rechaza=frozenset({"roto"})
    )

    resumen = await ConsultarProcesamiento(procesamientos).ejecutar(
        procesamiento_id=procesamiento.id
    )
    assert resumen.hubo_errores
    assert resumen.procesamiento.errores[0].motivo.startswith("CUIT invalido")

    listado = await ListarProcesamientos(procesamientos).ejecutar()
    assert len(listado) == 1


async def test_consultar_uno_que_no_existe_falla() -> None:
    with pytest.raises(EntradaInvalida):
        await ConsultarProcesamiento(ProcesamientosFalsos()).ejecutar(procesamiento_id=uuid4())
