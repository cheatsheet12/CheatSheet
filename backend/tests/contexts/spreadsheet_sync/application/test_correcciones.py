"""Corregir en el sistema una fila que falló al importar.

Lo que importa de la unidad, en orden: la fila se lee **del archivo** con el mapeo de la carga;
la corrección pasa por la misma ingesta que el procesamiento y, si se rechaza, **no deja nada
escrito**; una fila no se corrige dos veces; Solo Lectura mira pero no corrige; y la bitácora
nunca lleva los valores.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.correcciones import (
    MOTIVO_SIN_ARCHIVO,
    MOTIVO_SIN_PERMISO,
    CorregirFila,
    LeerFilaConError,
)
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import huella_de
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    FilaLeida,
    FilaParaIngerir,
    PlanillaLeida,
)
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import EntradaDeMapeo, Mapeo
from cheatsheet.contexts.spreadsheet_sync.domain.procesamiento import (
    ErrorDeFila,
    EstadoProcesamiento,
    ProcesamientoDePlanilla,
)
from cheatsheet.platform.almacenamiento import ArchivoGuardado
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, ErrorDeDominio, OperacionNoPermitida
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.roles import RolUsuario

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 9, 30, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
CLAVE = "planillas/x/y.xlsx"
COLUMNAS = ("Cliente", "CUIT/CUIL", "Domicilio fiscal")


class ProcesamientosFalsos:
    def __init__(self, procesamiento: ProcesamientoDePlanilla) -> None:
        self.guardado = procesamiento
        self.actualizaciones = 0

    async def agregar(self, procesamiento: ProcesamientoDePlanilla) -> None: ...

    async def actualizar(self, procesamiento: ProcesamientoDePlanilla) -> None:
        self.guardado = procesamiento
        self.actualizaciones += 1

    async def buscar_por_id(self, procesamiento_id: UUID) -> ProcesamientoDePlanilla | None:
        return self.guardado if procesamiento_id == self.guardado.id else None

    async def listar(self, *, vinculo_id: UUID | None = None) -> list[ProcesamientoDePlanilla]:
        del vinculo_id
        return [self.guardado]


class MapeosFalsos:
    def __init__(self, mapeo: Mapeo | None) -> None:
        self.mapeo = mapeo

    async def agregar(self, mapeo: Mapeo) -> None: ...

    async def actualizar(self, mapeo: Mapeo) -> None: ...

    async def buscar_por_id(self, mapeo_id: UUID) -> Mapeo | None:
        del mapeo_id
        return self.mapeo

    async def buscar_por_huella(self, huella: str) -> Mapeo | None:
        del huella
        return self.mapeo


class AlmacenamientoFalso:
    def __init__(self) -> None:
        self.leidas: list[str] = []

    async def guardar(
        self, *, clave: str, contenido: bytes, tipo_de_contenido: str
    ) -> ArchivoGuardado:
        raise NotImplementedError("Estas pruebas sólo leen")

    async def leer(self, clave: str) -> bytes:
        self.leidas.append(clave)
        return b"contenido"

    async def eliminar(self, clave: str) -> None: ...


class LectorFalso:
    def __init__(self, planilla: PlanillaLeida) -> None:
        self.planilla = planilla
        self.nombres: list[str] = []

    def leer(self, *, contenido: bytes, nombre: str) -> PlanillaLeida:
        del contenido
        self.nombres.append(nombre)
        return self.planilla


class CatalogoFalso:
    """Rechaza los CUIT de `rechaza`, como la ingesta real."""

    def __init__(self, rechaza: frozenset[str] = frozenset()) -> None:
        self.rechaza = rechaza
        self.ingeridas: list[dict[str, str]] = []

    async def ingerir(
        self, *, empresa_id: EmpresaId, fila: FilaParaIngerir, ahora: datetime
    ) -> None:
        del empresa_id, ahora
        if fila.valores.get("cuit") in self.rechaza:
            raise ErrorDeDominio("El digito verificador del CUIT no es correcto")
        self.ingeridas.append(fila.valores)


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def _mapeo() -> Mapeo:
    """«Domicilio fiscal» queda sin asignar a propósito: el usuario decidió que no va."""
    return Mapeo(
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
                id=uuid4(),
                columna_origen="CUIT/CUIL",
                atributo_destino="cuit",
                score=Decimal("0.99"),
            ),
            EntradaDeMapeo(
                id=uuid4(),
                columna_origen="Domicilio fiscal",
                atributo_destino=None,
                score=Decimal("0.2"),
            ),
        ],
        created_at=AHORA,
        updated_at=AHORA,
    )


def _procesamiento(*, con_archivo: bool = True) -> ProcesamientoDePlanilla:
    procesamiento = ProcesamientoDePlanilla(
        id=uuid4(),
        empresa_id=EMPRESA,
        vinculo_id=uuid4(),
        mapeo_id=uuid4(),
        referencia_archivo=CLAVE if con_archivo else None,
        created_at=AHORA,
    )
    procesamiento.contar_fila_ok()
    procesamiento.registrar_error(
        error=ErrorDeFila(id=uuid4(), numero_fila=5, motivo="El digito verificador no es correcto")
    )
    procesamiento.registrar_error(
        error=ErrorDeFila(id=uuid4(), numero_fila=6, motivo="Un CUIT tiene 11 digitos, no 9")
    )
    procesamiento.cerrar(duracion_ms=10, ahora=AHORA)
    return procesamiento


def _planilla() -> PlanillaLeida:
    return PlanillaLeida(
        columnas=COLUMNAS,
        filas=(
            FilaLeida(
                numero=5,
                celdas={
                    "Cliente": "Heladería Polo Norte",
                    "CUIT/CUIL": "20-11111111-1",
                    "Domicilio fiscal": "Ayacucho 440",
                },
            ),
            FilaLeida(
                numero=6,
                celdas={"Cliente": " Vivero Las Rosas ", "CUIT/CUIL": "27-9988776"},
            ),
        ),
    )


def _lector_de_fila(procesamiento: ProcesamientoDePlanilla) -> tuple[LeerFilaConError, LectorFalso]:
    lector = LectorFalso(_planilla())
    return (
        LeerFilaConError(
            procesamientos=ProcesamientosFalsos(procesamiento),
            mapeos=MapeosFalsos(_mapeo()),
            almacenamiento=AlmacenamientoFalso(),
            lector=lector,
        ),
        lector,
    )


def _corrector(
    procesamiento: ProcesamientoDePlanilla, rechaza: frozenset[str] = frozenset()
) -> tuple[CorregirFila, ProcesamientosFalsos, CatalogoFalso, PublicadorFalso]:
    procesamientos = ProcesamientosFalsos(procesamiento)
    catalogo = CatalogoFalso(rechaza)
    publicador = PublicadorFalso()
    return (
        CorregirFila(procesamientos=procesamientos, catalogo=catalogo, publicador=publicador),
        procesamientos,
        catalogo,
        publicador,
    )


async def _corregir(
    corrector: CorregirFila,
    procesamiento: ProcesamientoDePlanilla,
    *,
    valores: dict[str, str],
    numero_fila: int = 5,
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
) -> ProcesamientoDePlanilla:
    return await corrector.ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        procesamiento_id=procesamiento.id,
        numero_fila=numero_fila,
        valores=valores,
        ahora=AHORA,
    )


# ── Leer la fila ─────────────────────────────────────────────────────────────


async def test_la_fila_se_lee_del_archivo_con_el_mapeo_de_la_carga() -> None:
    procesamiento = _procesamiento()
    lectura, lector = _lector_de_fila(procesamiento)

    vista = await lectura.ejecutar(procesamiento_id=procesamiento.id, numero_fila=5)

    assert vista.numero_fila == 5
    assert vista.motivo == "El digito verificador no es correcto"
    # Campos del sistema y no columnas crudas, y sin la columna «Sin asignar».
    assert [(c.atributo, c.valor) for c in vista.campos] == [
        ("nombre", "Heladería Polo Norte"),
        ("cuit", "20-11111111-1"),
    ]
    # El lector decide el formato por la extensión, y la clave la conserva.
    assert lector.nombres == [CLAVE]


async def test_los_valores_se_muestran_sin_espacios_sobrantes() -> None:
    procesamiento = _procesamiento()
    lectura, _ = _lector_de_fila(procesamiento)

    vista = await lectura.ejecutar(procesamiento_id=procesamiento.id, numero_fila=6)

    assert vista.campos[0].valor == "Vivero Las Rosas"


async def test_una_celda_faltante_llega_como_campo_vacio_para_poder_completarla() -> None:
    procesamiento = _procesamiento()
    lectura, _ = _lector_de_fila(procesamiento)
    vista = await lectura.ejecutar(procesamiento_id=procesamiento.id, numero_fila=6)

    assert [c.atributo for c in vista.campos] == ["nombre", "cuit"]


async def test_una_carga_sin_archivo_no_se_puede_corregir_aca() -> None:
    """Una planilla de Google se lee por su proveedor, no desde el almacenamiento."""
    procesamiento = _procesamiento(con_archivo=False)
    lectura, _ = _lector_de_fila(procesamiento)

    with pytest.raises(EntradaInvalida, match="no se leyó de un archivo"):
        await lectura.ejecutar(procesamiento_id=procesamiento.id, numero_fila=5)
    assert "archivo subido" in MOTIVO_SIN_ARCHIVO


async def test_no_se_lee_una_fila_que_no_fallo() -> None:
    procesamiento = _procesamiento()
    lectura, _ = _lector_de_fila(procesamiento)

    with pytest.raises(EntradaInvalida, match="no tiene un error pendiente"):
        await lectura.ejecutar(procesamiento_id=procesamiento.id, numero_fila=2)


async def test_un_procesamiento_inexistente_se_dice() -> None:
    procesamiento = _procesamiento()
    lectura, _ = _lector_de_fila(procesamiento)

    with pytest.raises(EntradaInvalida, match="no existe"):
        await lectura.ejecutar(procesamiento_id=uuid4(), numero_fila=5)


# ── Corregir la fila ─────────────────────────────────────────────────────────


async def test_una_correccion_valida_se_importa_y_cierra_el_error() -> None:
    procesamiento = _procesamiento()
    corrector, procesamientos, catalogo, _ = _corrector(procesamiento)

    resultado = await _corregir(
        corrector, procesamiento, valores={"nombre": "Heladería Polo Norte", "cuit": "20123456786"}
    )

    assert catalogo.ingeridas == [{"nombre": "Heladería Polo Norte", "cuit": "20123456786"}]
    assert resultado.filas_error == 1
    assert resultado.filas_ok == 2
    assert [e.numero_fila for e in resultado.errores_pendientes] == [6]
    assert procesamientos.actualizaciones == 1


async def test_corregir_la_ultima_fila_deja_la_carga_completada() -> None:
    procesamiento = _procesamiento()
    corrector, _, _, _ = _corrector(procesamiento)
    await _corregir(corrector, procesamiento, valores={"nombre": "A", "cuit": "20123456786"})

    resultado = await _corregir(
        corrector, procesamiento, valores={"nombre": "B", "cuit": "27123456780"}, numero_fila=6
    )

    assert resultado.estado is EstadoProcesamiento.COMPLETADO
    assert resultado.filas_error == 0


async def test_una_correccion_rechazada_no_deja_nada_escrito() -> None:
    """El motivo sube tal cual, y ni el catálogo ni el procesamiento cambian."""
    procesamiento = _procesamiento()
    corrector, procesamientos, catalogo, publicador = _corrector(
        procesamiento, rechaza=frozenset({"20111111111"})
    )

    with pytest.raises(ErrorDeDominio, match="digito verificador"):
        await _corregir(corrector, procesamiento, valores={"nombre": "X", "cuit": "20111111111"})

    assert catalogo.ingeridas == []
    assert procesamientos.actualizaciones == 0
    assert procesamiento.filas_error == 2
    assert procesamiento.errores_pendientes[0].numero_fila == 5
    assert publicador.eventos == []


async def test_una_fila_no_se_corrige_dos_veces() -> None:
    """La segunda la importaría otra vez."""
    procesamiento = _procesamiento()
    corrector, _, catalogo, _ = _corrector(procesamiento)
    await _corregir(corrector, procesamiento, valores={"nombre": "A", "cuit": "20123456786"})

    with pytest.raises(EntradaInvalida, match="no tiene un error pendiente"):
        await _corregir(corrector, procesamiento, valores={"nombre": "A", "cuit": "20123456786"})

    assert len(catalogo.ingeridas) == 1


async def test_no_se_ingiere_una_fila_que_nunca_fallo() -> None:
    procesamiento = _procesamiento()
    corrector, _, catalogo, _ = _corrector(procesamiento)

    with pytest.raises(EntradaInvalida, match="no tiene un error pendiente"):
        await _corregir(corrector, procesamiento, valores={"nombre": "A"}, numero_fila=2)

    assert catalogo.ingeridas == []


async def test_solo_lectura_mira_pero_no_corrige() -> None:
    procesamiento = _procesamiento()
    corrector, _, catalogo, _ = _corrector(procesamiento)

    with pytest.raises(OperacionNoPermitida, match=MOTIVO_SIN_PERMISO):
        await _corregir(
            corrector, procesamiento, valores={"nombre": "A"}, rol=RolUsuario.SOLO_LECTURA
        )

    assert catalogo.ingeridas == []


async def test_el_operador_si_corrige() -> None:
    procesamiento = _procesamiento()
    corrector, _, catalogo, _ = _corrector(procesamiento)

    await _corregir(
        corrector,
        procesamiento,
        valores={"nombre": "A", "cuit": "20123456786"},
        rol=RolUsuario.OPERADOR,
    )

    assert len(catalogo.ingeridas) == 1


async def test_un_campo_desconocido_se_rechaza() -> None:
    """Sin esto el panel podría escribir en cualquier campo de `master_data`."""
    procesamiento = _procesamiento()
    corrector, _, catalogo, _ = _corrector(procesamiento)

    with pytest.raises(EntradaInvalida, match="no se reconoce"):
        await _corregir(corrector, procesamiento, valores={"nombre": "A", "is_admin": "1"})

    assert catalogo.ingeridas == []


async def test_los_campos_vacios_no_se_mandan_y_sin_ningun_dato_se_rechaza() -> None:
    procesamiento = _procesamiento()
    corrector, _, catalogo, _ = _corrector(procesamiento)

    with pytest.raises(EntradaInvalida, match="ningún dato"):
        await _corregir(corrector, procesamiento, valores={"nombre": "  ", "cuit": ""})

    await _corregir(corrector, procesamiento, valores={"nombre": " A ", "cuit": ""})
    # Sin espacios y sin el campo vacío: «vacío» es «no hay dato», no una cadena vacía.
    assert catalogo.ingeridas == [{"nombre": "A"}]


async def test_la_bitacora_dice_que_carga_y_nunca_los_valores() -> None:
    procesamiento = _procesamiento()
    corrector, _, _, publicador = _corrector(procesamiento)

    await _corregir(
        corrector, procesamiento, valores={"nombre": "Secreta SRL", "cuit": "20123456786"}
    )

    (evento,) = publicador.eventos
    assert isinstance(evento, EventoAuditable)
    assert evento.accion == "corregir_fila_de_carga"
    assert evento.entidad_afectada == f"ProcesamientoDePlanilla:{procesamiento.id}"
    assert evento.usuario_id == USUARIO
    # Los valores son CUIT y teléfonos: nada de eso puede estar en lo que se audita.
    assert "Secreta" not in repr(evento)
    assert "20123456786" not in repr(evento)
