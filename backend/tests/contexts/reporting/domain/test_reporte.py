"""El dominio de `Reporte` y `Periodo` (HU-E10-01 … HU-E10-03).

Lo que se prueba acá son las reglas que no se ven desde afuera:

- **Un `LISTO` sin archivo no se puede construir.** `completar` exige la referencia, así que la
  combinación que `es_descargable` tiene que defenderse de no es alcanzable por esa vía.
- **`FALLIDO` no vuelve.** Un reporte que falló se pide de nuevo y deja dos filas; reintentar
  sobre la misma borraría la evidencia de que hubo un problema.
- **El período anterior es del mismo largo.** Es lo que hace comparable la variación del
  tablero, y donde un error de un día se vuelve un porcentaje mal calculado todos los meses.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from cheatsheet.contexts.reporting.domain.reporte import (
    EstadoReporte,
    FormatoReporte,
    Periodo,
    Reporte,
    TipoReporte,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


def _reporte(
    tipo: TipoReporte = TipoReporte.FACTURACION,
    formato: FormatoReporte = FormatoReporte.CSV,
) -> Reporte:
    return Reporte(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        usuario_id=UsuarioId(uuid4()),
        tipo=tipo,
        formato=formato,
        periodo=Periodo.del_mes(2026, 3),
    )


class TestPeriodo:
    def test_del_mes_cierra_en_el_ultimo_dia(self) -> None:
        assert Periodo.del_mes(2026, 2) == Periodo(desde=date(2026, 2, 1), hasta=date(2026, 2, 28))

    def test_diciembre_cruza_de_ano(self) -> None:
        """El caso que rompe un `mes + 1` escrito sin pensar."""
        assert Periodo.del_mes(2026, 12).hasta == date(2026, 12, 31)

    def test_el_anterior_de_un_mes_es_el_mes_anterior(self) -> None:
        """Marzo se compara contra febrero entero, no contra los 31 días previos.

        Es la diferencia entre una variación que significa algo y una que cambia de valor
        todos los meses según cuántos días tenga el mes que se mira.
        """
        assert Periodo.del_mes(2026, 3).anterior == Periodo.del_mes(2026, 2)

    def test_el_anterior_de_enero_es_diciembre(self) -> None:
        assert Periodo.del_mes(2026, 1).anterior == Periodo.del_mes(2025, 12)

    def test_el_anterior_de_un_rango_suelto_es_del_mismo_largo(self) -> None:
        """Cuando el período no es un mes, «el anterior» sólo puede ser la ventana previa."""
        rango = Periodo(desde=date(2026, 3, 10), hasta=date(2026, 3, 16))
        assert rango.anterior == Periodo(desde=date(2026, 3, 3), hasta=date(2026, 3, 9))

    def test_un_periodo_al_reves_no_existe(self) -> None:
        with pytest.raises(EntradaInvalida):
            Periodo(desde=date(2026, 3, 31), hasta=date(2026, 3, 1))

    def test_mes_fuera_de_rango(self) -> None:
        with pytest.raises(EntradaInvalida):
            Periodo.del_mes(2026, 13)

    def test_contiene(self) -> None:
        periodo = Periodo.del_mes(2026, 3)
        assert periodo.contiene(date(2026, 3, 15))
        assert not periodo.contiene(date(2026, 4, 1))


class TestReporte:
    def test_un_formato_que_el_tipo_no_admite_se_rechaza(self) -> None:
        """`FORMATOS_POR_TIPO`: un resumen ejecutivo en CSV son cuatro números sin gráfico."""
        with pytest.raises(EntradaInvalida) as error:
            _reporte(TipoReporte.RESUMEN_EJECUTIVO, FormatoReporte.CSV)
        assert "PDF" in str(error.value)

    def test_el_ciclo_completo(self) -> None:
        reporte = _reporte()
        reporte.empezar()
        reporte.completar("reportes/x.csv")
        assert reporte.estado is EstadoReporte.LISTO
        assert reporte.es_descargable

    def test_listo_sin_archivo_no_se_puede(self) -> None:
        reporte = _reporte()
        reporte.empezar()
        with pytest.raises(EntradaInvalida):
            reporte.completar("   ")
        assert reporte.estado is EstadoReporte.EN_CURSO

    def test_pendiente_no_salta_a_listo(self) -> None:
        with pytest.raises(InvarianteViolada):
            _reporte().completar("reportes/x.csv")

    def test_fallido_no_vuelve(self) -> None:
        reporte = _reporte()
        reporte.empezar()
        reporte.fallar()
        with pytest.raises(InvarianteViolada):
            reporte.empezar()

    def test_no_es_descargable_sin_archivo(self) -> None:
        reporte = _reporte()
        reporte.empezar()
        assert not reporte.es_descargable
