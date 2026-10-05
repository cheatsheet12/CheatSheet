"""`Dialogo` ↔ JSON (T2): la ida y vuelta, y qué pasa con lo que no se puede leer.

El caso 35 del plan se prueba **dos veces**: acá, sin base, que es lo que cubre el mapeo; y en
`tests/integracion/test_conversacional_postgres.py` contra la columna `jsonb` de verdad.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.domain.dialogo import (
    Dialogo,
    OpcionDeHorario,
    OpcionDeServicio,
    OpcionDeTurno,
    PasoDelDialogo,
)
from cheatsheet.contexts.conversational.domain.pedido_de_turno import (
    AccionDeTurno,
    Cuando,
    MomentoDelDia,
    PedidoDeTurno,
    ReferenciaDeDia,
)
from cheatsheet.contexts.conversational.infrastructure.dialogo_json import (
    VERSION_DEL_FORMATO,
    dialogo_a_json,
    dialogo_de_json,
    leer_dialogo_guardado,
)

AHORA = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)
PEDIDO = PedidoDeTurno(
    accion=AccionDeTurno.RESERVAR,
    cuandos=(
        Cuando(ReferenciaDeDia.DIA_DE_SEMANA, dia_semana=3),
        Cuando(ReferenciaDeDia.FECHA, dia=14, mes=10),
    ),
    momento=MomentoDelDia.TARDE,
    hora=time(16, 30),
    servicio="corte",
)


def tres_dialogos() -> list[Dialogo]:
    servicio = uuid4()
    return [
        Dialogo.nuevo(
            PasoDelDialogo.ELEGIR_HORARIO,
            AHORA,
            opciones=(
                OpcionDeHorario(
                    inicio=AHORA + timedelta(days=1),
                    servicio_id=servicio,
                    recursos=(uuid4(), uuid4()),
                ),
            ),
            servicio_id=servicio,
            pedido=PEDIDO,
        ),
        Dialogo.nuevo(
            PasoDelDialogo.ELEGIR_SERVICIO,
            AHORA,
            opciones=(OpcionDeServicio(id=uuid4(), nombre="Corte"),),
            pedido=PedidoDeTurno(accion=AccionDeTurno.RESERVAR),
        ),
        Dialogo.nuevo(
            PasoDelDialogo.CONFIRMAR_CANCELACION,
            AHORA,
            opciones=(
                OpcionDeTurno(
                    turno_id=uuid4(),
                    servicio="Consulta general",
                    inicio=AHORA + timedelta(days=2),
                    tiene_sena=True,
                ),
            ),
        ),
        Dialogo.nuevo(PasoDelDialogo.PEDIR_CUANDO, AHORA, servicio_id=uuid4(), pedido=PEDIDO),
    ]


@pytest.mark.parametrize("dialogo", tres_dialogos(), ids=lambda uno: uno.paso.value)
def test_ida_y_vuelta(dialogo: Dialogo) -> None:
    assert dialogo_de_json(dialogo_a_json(dialogo)) == dialogo


def test_el_json_lleva_la_version() -> None:
    assert dialogo_a_json(tres_dialogos()[0])["version"] == VERSION_DEL_FORMATO == 1


def test_sin_dialogo_no_hay_nada_que_leer() -> None:
    assert leer_dialogo_guardado(None, conversacion_id=uuid4()) is None


@pytest.mark.parametrize(
    "estropear",
    [
        lambda crudo: {**crudo, "version": 2},
        lambda crudo: {**crudo, "version": None},
        lambda crudo: {**crudo, "paso": "BORRAR_TODO"},
        lambda crudo: {k: v for k, v in crudo.items() if k != "opciones"},
        lambda crudo: {**crudo, "vence_en": "ayer"},
        lambda crudo: {**crudo, "opciones": [{"tipo": "otro"}]},
        lambda crudo: {**crudo, "opciones": []},  # ELEGIR_HORARIO sin opciones
        lambda crudo: {**crudo, "vence_en": crudo["abierto_en"]},
        lambda crudo: {**crudo, "opciones": [{"tipo": "turno", "turno_id": "no-es-un-uuid"}]},
    ],
)
def test_un_json_ilegible_se_lee_como_sin_dialogo(estropear: Any) -> None:
    """Nunca se reserva sobre algo que no se pudo leer: se lo trata como si no hubiera diálogo."""
    crudo = dialogo_a_json(tres_dialogos()[0])

    assert leer_dialogo_guardado(estropear(crudo), conversacion_id=uuid4()) is None


def test_un_json_que_no_es_un_objeto_tambien_se_lee_como_sin_dialogo() -> None:
    assert leer_dialogo_guardado([1, 2], conversacion_id=uuid4()) is None  # type: ignore[arg-type]
