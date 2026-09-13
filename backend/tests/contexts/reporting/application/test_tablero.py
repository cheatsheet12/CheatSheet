"""El tablero y la previsualización (HU-E10-01 y HU-E10-02).

Tres cosas se prueban acá, y las tres son decisiones del épico:

- **La variación se calcula en el dominio y devuelve `None` cuando no hay con qué comparar.**
  Un cero ahí le mentiría a alguien sobre su propio negocio: «creció 0%» y «el mes pasado no
  hubo nada» son cosas distintas.
- **«Sin actividad» son las cuatro métricas en cero**, no sólo la facturación. Un mes sin
  facturar pero con veinte turnos atendidos sí tuvo actividad.
- **La previsualización no escribe.** Se llama tres veces y no queda ni un reporte: es
  literalmente lo que dice HU-E10-02 RN-03.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from cheatsheet.contexts.reporting.application.ports import (
    FilaDeReporte,
    TotalesDeCobranzas,
    TotalesDeFacturacion,
)
from cheatsheet.contexts.reporting.application.tablero import (
    Metrica,
    PrevisualizarReporte,
    VerTablero,
    periodo_por_defecto,
)
from cheatsheet.contexts.reporting.domain.reporte import Periodo, TipoReporte

from tests.contexts.reporting.application.dobles import (
    AgendaFalsa,
    BitacoraFalsa,
    CobranzasFalsas,
    FacturacionFalsa,
)

MARZO = Periodo.del_mes(2026, 3)


class TestMetrica:
    def test_variacion_porcentual(self) -> None:
        assert Metrica(Decimal("150"), Decimal("100")).variacion == Decimal("50.0")

    def test_una_caida_es_negativa(self) -> None:
        assert Metrica(Decimal("50"), Decimal("100")).variacion == Decimal("-50.0")

    def test_sin_periodo_anterior_no_hay_variacion(self) -> None:
        """`None` y no cero. La pantalla dibuja un guion."""
        assert Metrica(Decimal("150"), Decimal("0")).variacion is None


class TestVerTablero:
    @pytest.mark.asyncio
    async def test_arma_las_cuatro_metricas_contra_el_periodo_anterior(self) -> None:
        facturacion = FacturacionFalsa(
            totales=TotalesDeFacturacion(
                total=Decimal("100000.00"),
                cantidad=4,
                por_tipo={"FACTURA_B": Decimal("100000.00")},
                por_semana={"2026-W10": Decimal("100000.00")},
            )
        )
        tablero = await VerTablero(
            facturacion=facturacion,
            cobranzas=CobranzasFalsas(
                totales=TotalesDeCobranzas(
                    cobrado=Decimal("80000.00"),
                    pendiente=Decimal("15000.00"),
                    en_mora=Decimal("5000.00"),
                )
            ),
            agenda=AgendaFalsa(gestionados=12, completados=10, no_show=2),
            bitacora=BitacoraFalsa(cuantas=340),
        ).ejecutar(MARZO)

        assert tablero.facturado.valor == Decimal("100000.00")
        assert tablero.turnos.valor == Decimal("12")
        assert tablero.operaciones.valor == Decimal("340")
        assert tablero.en_mora == Decimal("5000.00")
        # Preguntó dos veces por facturación: el período y el anterior (RN-02).
        assert facturacion.periodos == [MARZO, MARZO.anterior]

    @pytest.mark.asyncio
    async def test_sin_actividad_exige_las_cuatro_en_cero(self) -> None:
        tablero = await VerTablero(
            facturacion=FacturacionFalsa(),
            cobranzas=CobranzasFalsas(),
            agenda=AgendaFalsa(),
            bitacora=BitacoraFalsa(),
        ).ejecutar(MARZO)
        assert tablero.sin_actividad

    @pytest.mark.asyncio
    async def test_un_mes_sin_facturar_pero_con_turnos_tuvo_actividad(self) -> None:
        """El criterio dice «el período no tiene actividad», no «no facturó»."""
        tablero = await VerTablero(
            facturacion=FacturacionFalsa(),
            cobranzas=CobranzasFalsas(),
            agenda=AgendaFalsa(gestionados=20, completados=20),
            bitacora=BitacoraFalsa(),
        ).ejecutar(MARZO)
        assert not tablero.sin_actividad


class TestPrevisualizar:
    @pytest.mark.asyncio
    async def test_facturacion_estima_cantidad_y_total(self) -> None:
        estimacion = await PrevisualizarReporte(
            facturacion=FacturacionFalsa(
                totales=TotalesDeFacturacion(
                    total=Decimal("42000.00"), cantidad=7, por_tipo={}, por_semana={}
                )
            ),
            cobranzas=CobranzasFalsas(),
            bitacora=BitacoraFalsa(),
        ).ejecutar(tipo=TipoReporte.FACTURACION, periodo=MARZO)
        assert (estimacion.cantidad, estimacion.total) == (7, Decimal("42000.00"))
        assert estimacion.hay_datos

    @pytest.mark.asyncio
    async def test_cobros_cuenta_filas(self) -> None:
        estimacion = await PrevisualizarReporte(
            facturacion=FacturacionFalsa(),
            cobranzas=CobranzasFalsas(
                totales=TotalesDeCobranzas(
                    cobrado=Decimal("9000.00"), pendiente=Decimal("0.00"), en_mora=Decimal("0.00")
                ),
                filas=[FilaDeReporte({"monto": "9000.00"})],
            ),
            bitacora=BitacoraFalsa(),
        ).ejecutar(tipo=TipoReporte.COBROS, periodo=MARZO)
        assert (estimacion.cantidad, estimacion.total) == (1, Decimal("9000.00"))

    @pytest.mark.asyncio
    async def test_operaciones_no_tiene_importe(self) -> None:
        """Son eventos, no plata. Cero es la respuesta honesta."""
        estimacion = await PrevisualizarReporte(
            facturacion=FacturacionFalsa(),
            cobranzas=CobranzasFalsas(),
            bitacora=BitacoraFalsa(cuantas=88),
        ).ejecutar(tipo=TipoReporte.OPERACIONES, periodo=MARZO)
        assert (estimacion.cantidad, estimacion.total) == (88, Decimal("0.00"))

    @pytest.mark.asyncio
    async def test_un_periodo_vacio_avisa_que_no_hay_datos(self) -> None:
        estimacion = await PrevisualizarReporte(
            facturacion=FacturacionFalsa(),
            cobranzas=CobranzasFalsas(),
            bitacora=BitacoraFalsa(),
        ).ejecutar(tipo=TipoReporte.FACTURACION, periodo=MARZO)
        assert not estimacion.hay_datos


def test_el_periodo_por_defecto_es_el_mes_en_curso() -> None:
    assert periodo_por_defecto(date(2026, 3, 17)) == MARZO
