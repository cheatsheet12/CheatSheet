"""Lo que `GET /reporteria/tablero` serializa de la cobranza, sin base de datos.

La prueba de punta a punta vive en `integracion/test_api_reporteria.py` y necesita PostgreSQL;
esta fija que la tasa, el cobrado por semana y los cobros por estado viajan como texto exacto y
salen del campo que les corresponde, y no de uno vecino.
"""

from __future__ import annotations

from decimal import Decimal

from cheatsheet.api.routers.tablero_salida import tablero_salida
from cheatsheet.contexts.reporting.application.ports import CobrosPorEstado
from cheatsheet.contexts.reporting.application.tablero import Metrica, Tablero
from cheatsheet.contexts.reporting.domain.reporte import Periodo


def _tablero() -> Tablero:
    cero = Metrica(valor=Decimal("0.00"), anterior=Decimal("0.00"))
    return Tablero(
        periodo=Periodo.del_mes(2026, 3),
        facturado=cero,
        cobrado=Metrica(valor=Decimal("700.00"), anterior=Decimal("0.00")),
        turnos=cero,
        operaciones=cero,
        por_tipo={},
        por_semana={"2026-W10": Decimal("999.00")},
        pendiente=Decimal("200.00"),
        en_mora=Decimal("100.00"),
        tasa_de_cobro=Decimal("72.50"),
        cobrado_por_semana={"2026-W10": Decimal("1000.00"), "2026-W11": Decimal("-300.00")},
        cobros_por_estado={"pagado": CobrosPorEstado(cantidad=8, monto=Decimal("120000.10"))},
    )


def test_la_cobranza_viaja_como_texto_exacto_y_desde_su_propio_campo() -> None:
    salida = tablero_salida(_tablero()).model_dump()

    assert salida["tasa_de_cobro"] == "72.50"
    assert salida["cobrado_por_semana"] == {"2026-W10": "1000.00", "2026-W11": "-300.00"}
    assert salida["por_semana"] == {"2026-W10": "999.00"}
    assert salida["cobros_por_estado"] == {"pagado": {"cantidad": 8, "monto": "120000.10"}}
    assert salida["sin_actividad"] is False
