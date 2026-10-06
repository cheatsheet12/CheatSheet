"""`Reporte` — un pedido de exportar datos, y su ciclo de vida (HU-E10-02, HU-E10-03).

Este contexto es el único que **sólo lee**: no emite comprobantes, no mueve plata, no reserva
nada. Lo que produce es una foto de lo que hicieron los demás. Eso decide casi todo lo de acá:

- **Un reporte es una entidad y no una descarga.** El DER le da tabla, con su tipo, formato,
  filtros y estado. Es lo que hace posible el último criterio de HU-E10-03 —«consulto reportes
  generados antes»— y lo que convierte una generación lenta en algo que se puede esperar.

- **La previsualización no crea un `Reporte`** (HU-E10-02 RN-03: «no consume el ciclo de
  generación»). Es una consulta que devuelve una estimación, y por eso vive en la capa de
  aplicación sin tocar esta tabla. Si dejara filas, ajustar un filtro tres veces dejaría tres
  reportes que nadie pidió.

- **La foto es de un período cerrado.** Un reporte no se «actualiza»: se genera de nuevo. Por
  eso `Reporte` no tiene un método para recalcular — un archivo que cambia después de que
  alguien lo mandó por mail es peor que uno viejo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: HU-E10-01 y HU-E10-03, palabra por palabra.
MENSAJE_SIN_ACTIVIDAD = "No hay actividad registrada para este período."
MENSAJE_SIN_DATOS = "No hay datos para generar el reporte en el período seleccionado."


class TipoReporte(StrEnum):
    """Qué se exporta. El DER guarda `tipo` como `varchar`; el enum vive acá.

    Los cuatro son los que HU-E10-04 RN-03 nombra como contenido posible del paquete contable,
    y que HU-E10-03 permite pedir sueltos. **`RESUMEN_EJECUTIVO` no es un listado**: es el
    mismo tablero de HU-E10-01 en un archivo, y por eso su formato natural es PDF.
    """

    FACTURACION = "FACTURACION"
    COBROS = "COBROS"
    OPERACIONES = "OPERACIONES"
    RESUMEN_EJECUTIVO = "RESUMEN_EJECUTIVO"


class FormatoReporte(StrEnum):
    """PDF para leer, CSV para analizar, XML para el contador (HU-E10-04 RN-02)."""

    PDF = "PDF"
    CSV = "CSV"
    XML = "XML"


#: Qué formatos tiene sentido pedir para cada tipo (HU-E10-03 RN-01: «según el tipo»).
#:
#: Una tabla y no «todos con todos»: un resumen ejecutivo en CSV es una fila con cuatro números
#: y ningún gráfico, y un listado de facturación en PDF de un mes ocupado son ochenta páginas
#: que nadie va a leer. Ofrecer lo que no sirve es hacer que alguien lo descubra descargándolo.
FORMATOS_POR_TIPO: dict[TipoReporte, frozenset[FormatoReporte]] = {
    TipoReporte.FACTURACION: frozenset({FormatoReporte.CSV, FormatoReporte.XML}),
    TipoReporte.COBROS: frozenset({FormatoReporte.CSV}),
    TipoReporte.OPERACIONES: frozenset({FormatoReporte.CSV}),
    TipoReporte.RESUMEN_EJECUTIVO: frozenset({FormatoReporte.PDF}),
}


class EstadoReporte(StrEnum):
    """El enum `estado_reporte` del DER."""

    PENDIENTE = "PENDIENTE"
    EN_CURSO = "EN_CURSO"
    LISTO = "LISTO"
    FALLIDO = "FALLIDO"


#: Qué transiciones existen, como tabla y no como diez `if`.
#:
#: **`FALLIDO` no vuelve.** Un reporte que falló se pide de nuevo, y eso deja dos filas: la que
#: falló y la que salió. Reintentar sobre la misma fila borraría la evidencia de que hubo un
#: problema, que es justo lo que alguien va a querer ver cuando pregunte por qué su contador no
#: recibió nada el mes pasado.
TRANSICIONES_LEGALES: dict[EstadoReporte, frozenset[EstadoReporte]] = {
    EstadoReporte.PENDIENTE: frozenset({EstadoReporte.EN_CURSO, EstadoReporte.FALLIDO}),
    EstadoReporte.EN_CURSO: frozenset({EstadoReporte.LISTO, EstadoReporte.FALLIDO}),
    EstadoReporte.LISTO: frozenset(),
    EstadoReporte.FALLIDO: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Periodo:
    """Un rango de fechas cerrado por los dos lados.

    Frozen: un período es la identidad de lo que un reporte mira. Cambiarlo después de generar
    dejaría un archivo que dice una cosa y una fila que dice otra.
    """

    desde: date
    hasta: date

    def __post_init__(self) -> None:
        if self.desde > self.hasta:
            raise EntradaInvalida("El inicio del período debe ser anterior a su fin")

    @classmethod
    def del_mes(cls, anio: int, mes: int) -> Periodo:
        """El mes completo. Lo que HU-E10-01 RN-01 usa por defecto y lo que el paquete cierra."""
        if not 1 <= mes <= 12:
            raise EntradaInvalida("El mes va de 1 a 12")
        inicio = date(anio, mes, 1)
        return cls(desde=inicio, hasta=_dia_anterior(_primero_del_mes_siguiente(inicio)))

    @property
    def es_un_mes_entero(self) -> bool:
        """Si va del día 1 al último día del mismo mes."""
        return (
            self.desde.day == 1
            and self.desde.year == self.hasta.year
            and self.desde.month == self.hasta.month
            and self.hasta == _dia_anterior(_primero_del_mes_siguiente(self.desde))
        )

    @property
    def anterior(self) -> Periodo:
        """El período inmediatamente anterior. Lo que hace posible la variación de RN-02.

        **Un mes entero se compara contra el mes entero anterior**, no contra los treinta y un
        días que lo preceden. Marzo tiene 31 días y febrero 28: «el mismo largo, justo antes»
        de marzo empieza el 29 de enero, y comparar marzo contra un tramo que agarra tres días
        de enero produce una variación que no significa nada — y que además cambiaría de valor
        según el largo del mes, todos los meses, sin que nadie entienda por qué.

        Un rango cualquiera —el que alguien eligió a mano en el selector— sí se compara contra
        la ventana del mismo largo anterior: es lo único que puede significar «el anterior»
        cuando el período no es un mes.
        """
        if self.es_un_mes_entero:
            anterior = _dia_anterior(self.desde)
            return Periodo.del_mes(anterior.year, anterior.month)
        largo = (self.hasta - self.desde).days + 1
        from datetime import timedelta

        return Periodo(
            desde=self.desde - timedelta(days=largo), hasta=self.desde - timedelta(days=1)
        )

    def contiene(self, momento: date) -> bool:
        return self.desde <= momento <= self.hasta


def _dia_anterior(fecha: date) -> date:
    from datetime import timedelta

    return fecha - timedelta(days=1)


def _primero_del_mes_siguiente(fecha: date) -> date:
    return date(fecha.year + (fecha.month // 12), (fecha.month % 12) + 1, 1)


@dataclass(slots=True)
class Reporte:
    """Un pedido de exportación, con su estado y su archivo cuando lo tiene."""

    id: UUID
    empresa_id: EmpresaId
    usuario_id: UsuarioId
    tipo: TipoReporte
    formato: FormatoReporte
    periodo: Periodo
    estado: EstadoReporte = EstadoReporte.PENDIENTE
    filtros: dict[str, Any] = field(default_factory=dict)
    referencia_archivo: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.formato not in FORMATOS_POR_TIPO[self.tipo]:
            # No es una restricción arbitraria: ver el comentario de `FORMATOS_POR_TIPO`.
            admitidos = ", ".join(sorted(uno.value for uno in FORMATOS_POR_TIPO[self.tipo]))
            raise EntradaInvalida(
                f"Un reporte de {self.tipo.value.lower()} sólo puede pedirse en {admitidos}"
            )

    @property
    def esta_listo(self) -> bool:
        return self.estado is EstadoReporte.LISTO

    @property
    def es_descargable(self) -> bool:
        """Listo **y con archivo**. Las dos cosas, porque una sin la otra es un bug.

        Un `LISTO` sin referencia significa que alguien marcó el estado sin guardar el archivo,
        y ofrecer una descarga que va a fallar es peor que no ofrecerla.
        """
        return self.esta_listo and self.referencia_archivo is not None

    def empezar(self) -> None:
        self._transicionar_a(EstadoReporte.EN_CURSO)

    def completar(self, referencia: str) -> None:
        """Lo marca listo **y guarda el archivo en la misma llamada**.

        Un método que sólo cambiara el estado permitiría el `LISTO` sin referencia que
        `es_descargable` tiene que defenderse de. Acá no se puede.
        """
        if not referencia.strip():
            raise EntradaInvalida("Un reporte listo necesita su archivo")
        self._transicionar_a(EstadoReporte.LISTO)
        self.referencia_archivo = referencia

    def fallar(self) -> None:
        self._transicionar_a(EstadoReporte.FALLIDO)

    def _transicionar_a(self, destino: EstadoReporte) -> None:
        if destino not in TRANSICIONES_LEGALES[self.estado]:
            raise InvarianteViolada(
                f"Un reporte {self.estado.value.lower()} no puede pasar a {destino.value.lower()}"
            )
        self.estado = destino


__all__ = [
    "FORMATOS_POR_TIPO",
    "MENSAJE_SIN_ACTIVIDAD",
    "MENSAJE_SIN_DATOS",
    "TRANSICIONES_LEGALES",
    "EstadoReporte",
    "FormatoReporte",
    "Periodo",
    "Reporte",
    "TipoReporte",
]
