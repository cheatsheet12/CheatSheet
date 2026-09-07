"""El tablero y la previsualización (HU-E10-01, HU-E10-02).

**Todos los roles leen, incluido el contador externo** (RN-04 y RN-05 de HU-E10-01). Es la
única consulta del sistema a la que llega alguien sin cuenta, y por eso el tablero no muestra
un solo dato de un cliente: son totales, y los totales no identifican a nadie.

**La variación contra el período anterior se calcula acá y no en la pantalla.** Es una regla de
negocio —RN-02 dice «con su variación respecto al período anterior»— y dejarla en el frontend
haría que el mismo número saliera distinto en el panel y en el resumen ejecutivo del paquete.

**La previsualización no crea nada** (HU-E10-02 RN-03). Es esta misma consulta con otro nombre:
cuántos comprobantes y por cuánto, sin tocar la tabla de reportes. Ajustar un filtro cinco veces
tiene que costar cinco consultas y cero filas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cheatsheet.contexts.reporting.application.ports import (
    PortAgendaLeida,
    PortBitacora,
    PortCobranzas,
    PortFacturacion,
)
from cheatsheet.contexts.reporting.domain.reporte import Periodo, TipoReporte

CERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class Metrica:
    """Un número del encabezado, con su variación (HU-E10-01 RN-02)."""

    valor: Decimal
    anterior: Decimal

    @property
    def variacion(self) -> Decimal | None:
        """El cambio porcentual, o `None` cuando el período anterior fue cero.

        **`None` y no cero**: «creció 0%» y «no hay con qué comparar» son cosas distintas, y
        mostrar la primera cuando pasa la segunda le miente a alguien sobre su propio negocio.
        La pantalla dibuja un guion.
        """
        if self.anterior == 0:
            return None
        return ((self.valor - self.anterior) / self.anterior * 100).quantize(Decimal("0.1"))


@dataclass(frozen=True, slots=True)
class Tablero:
    """Lo que PAN-REP-01 muestra."""

    periodo: Periodo
    facturado: Metrica
    cobrado: Metrica
    turnos: Metrica
    operaciones: Metrica
    por_tipo: dict[str, Decimal]
    por_semana: dict[str, Decimal]
    pendiente: Decimal
    en_mora: Decimal

    @property
    def sin_actividad(self) -> bool:
        """Tercer criterio de HU-E10-01: «el período no tiene actividad».

        Las cuatro en cero, no sólo la facturación: un mes sin facturar pero con veinte turnos
        atendidos **sí** tuvo actividad, y decirle a esa empresa que no pasó nada sería falso.
        """
        return (
            self.facturado.valor == 0
            and self.cobrado.valor == 0
            and self.turnos.valor == 0
            and self.operaciones.valor == 0
        )


@dataclass(frozen=True, slots=True)
class Previsualizacion:
    """La estimación de HU-E10-02 RN-01: cuántos y por cuánto, sin generar nada."""

    tipo: TipoReporte
    periodo: Periodo
    cantidad: int
    total: Decimal

    @property
    def hay_datos(self) -> bool:
        return self.cantidad > 0


class VerTablero:
    """HU-E10-01. Cuatro consultas de sólo lectura, y la comparación contra el mes anterior."""

    def __init__(
        self,
        *,
        facturacion: PortFacturacion,
        cobranzas: PortCobranzas,
        agenda: PortAgendaLeida,
        bitacora: PortBitacora,
    ) -> None:
        self._facturacion = facturacion
        self._cobranzas = cobranzas
        self._agenda = agenda
        self._bitacora = bitacora

    async def ejecutar(self, periodo: Periodo) -> Tablero:
        anterior = periodo.anterior

        actual_facturacion = await self._facturacion.totales(periodo)
        previa_facturacion = await self._facturacion.totales(anterior)
        actual_cobros = await self._cobranzas.totales(periodo)
        previa_cobros = await self._cobranzas.totales(anterior)
        actual_agenda = await self._agenda.totales(periodo)
        previa_agenda = await self._agenda.totales(anterior)
        actuales_operaciones = await self._bitacora.cuantas_operaciones(periodo)
        previas_operaciones = await self._bitacora.cuantas_operaciones(anterior)

        return Tablero(
            periodo=periodo,
            facturado=Metrica(actual_facturacion.total, previa_facturacion.total),
            cobrado=Metrica(actual_cobros.cobrado, previa_cobros.cobrado),
            turnos=Metrica(Decimal(actual_agenda.gestionados), Decimal(previa_agenda.gestionados)),
            operaciones=Metrica(Decimal(actuales_operaciones), Decimal(previas_operaciones)),
            por_tipo=actual_facturacion.por_tipo,
            por_semana=actual_facturacion.por_semana,
            pendiente=actual_cobros.pendiente,
            en_mora=actual_cobros.en_mora,
        )


class PrevisualizarReporte:
    """HU-E10-02. **No escribe nada.** Ver el docstring del módulo."""

    def __init__(
        self,
        *,
        facturacion: PortFacturacion,
        cobranzas: PortCobranzas,
        bitacora: PortBitacora,
    ) -> None:
        self._facturacion = facturacion
        self._cobranzas = cobranzas
        self._bitacora = bitacora

    async def ejecutar(self, *, tipo: TipoReporte, periodo: Periodo) -> Previsualizacion:
        if tipo is TipoReporte.FACTURACION or tipo is TipoReporte.RESUMEN_EJECUTIVO:
            totales = await self._facturacion.totales(periodo)
            return Previsualizacion(tipo, periodo, totales.cantidad, totales.total)
        if tipo is TipoReporte.COBROS:
            cobros = await self._cobranzas.totales(periodo)
            filas = await self._cobranzas.filas(periodo)
            return Previsualizacion(tipo, periodo, len(filas), cobros.cobrado)
        cuantas = await self._bitacora.cuantas_operaciones(periodo)
        # Un reporte de operaciones no tiene «total»: son eventos, no plata. Cero es la
        # respuesta honesta, y la pantalla no muestra un importe para este tipo.
        return Previsualizacion(tipo, periodo, cuantas, CERO)


def periodo_por_defecto(hoy: date) -> Periodo:
    """El mes en curso (HU-E10-01 RN-01).

    Vive acá y no en el router porque el paquete contable y el resumen ejecutivo lo necesitan
    igual: si cada uno decidiera su período por defecto, el tablero y el PDF dirían cosas
    distintas del mismo mes.
    """
    return Periodo.del_mes(hoy.year, hoy.month)


__all__ = [
    "Metrica",
    "Previsualizacion",
    "PrevisualizarReporte",
    "Tablero",
    "VerTablero",
    "periodo_por_defecto",
]
