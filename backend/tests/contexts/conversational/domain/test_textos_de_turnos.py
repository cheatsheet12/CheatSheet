"""Los textos de turnos: el formato no depende del locale del servidor."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cheatsheet.contexts.conversational.domain.dialogo import OpcionDeHorario, OpcionDeTurno
from cheatsheet.contexts.conversational.domain.textos_de_turnos import (
    cancelacion_confirmada,
    confirmar_cancelacion,
    formatear_inicio,
    listado_de_turnos,
    oferta_de_horarios,
    reserva_confirmada,
)

#: 13:30 UTC es 10:30 en Argentina. El 14 de octubre de 2026 es miércoles.
INICIO = datetime(2026, 10, 14, 13, 30, tzinfo=UTC)


def test_el_formato_es_en_hora_argentina_y_en_espanol() -> None:
    assert formatear_inicio(INICIO) == "miércoles 14/10 a las 10:30"


def test_un_instante_de_la_noche_utc_cae_en_el_dia_anterior_en_argentina() -> None:
    assert formatear_inicio(datetime(2026, 10, 15, 1, 30, tzinfo=UTC)) == (
        "miércoles 14/10 a las 22:30"
    )


def test_la_reserva_confirmada_dice_el_dia_y_la_hora() -> None:
    assert reserva_confirmada(INICIO) == (
        "Listo, tu turno quedó reservado para el miércoles 14/10 a las 10:30."
    )


def test_la_oferta_es_un_listado_numerado() -> None:
    opciones = [
        OpcionDeHorario(inicio=INICIO, servicio_id=uuid4(), recursos=(uuid4(),)),
        OpcionDeHorario(inicio=INICIO.replace(hour=19), servicio_id=uuid4(), recursos=(uuid4(),)),
    ]

    texto = oferta_de_horarios(opciones, antes="Ese horario se acaba de ocupar.")

    assert texto.splitlines()[0] == "Ese horario se acaba de ocupar."
    assert "1) miércoles 14/10 a las 10:30" in texto
    assert "2) miércoles 14/10 a las 16:30" in texto


def test_las_frases_de_cancelacion_nombran_el_turno() -> None:
    turno = OpcionDeTurno(
        turno_id=uuid4(), servicio="Consulta general", inicio=INICIO, tiene_sena=False
    )

    assert confirmar_cancelacion(turno) == (
        "¿Confirmás que cancelamos tu turno de Consulta general del miércoles 14/10 a las 10:30?"
    )
    assert cancelacion_confirmada(turno).startswith("Listo, cancelamos tu turno de Consulta")
    assert listado_de_turnos([turno]).splitlines()[1] == (
        "1) Consulta general del miércoles 14/10 a las 10:30"
    )
