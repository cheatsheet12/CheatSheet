"""`Dialogo` — lo que el sistema le ofreció al cliente y espera que conteste (T2, T14).

Es un value object: el sistema lo arma, nunca el modelo ni el cliente. De sus opciones salen los
ids que se reservan o se cancelan, así que sus invariantes son la primera barrera.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.domain.conversacion import Conversacion
from cheatsheet.contexts.conversational.domain.dialogo import (
    VIGENCIA_DEL_DIALOGO,
    Dialogo,
    OpcionDeHorario,
    OpcionDeServicio,
    OpcionDeTurno,
    PasoDelDialogo,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import InvarianteViolada

AHORA = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)


def un_horario() -> OpcionDeHorario:
    return OpcionDeHorario(
        inicio=AHORA + timedelta(days=1), servicio_id=uuid4(), recursos=(uuid4(),)
    )


def un_turno() -> OpcionDeTurno:
    return OpcionDeTurno(
        turno_id=uuid4(), servicio="Corte", inicio=AHORA + timedelta(days=1), tiene_sena=False
    )


class TestVigencia:
    def test_vale_treinta_minutos(self) -> None:
        assert timedelta(minutes=30) == VIGENCIA_DEL_DIALOGO

    def test_vence_a_los_treinta_minutos_justos(self) -> None:
        dialogo = Dialogo.nuevo(PasoDelDialogo.ELEGIR_HORARIO, AHORA, opciones=(un_horario(),))

        assert dialogo.vigente(AHORA + timedelta(minutes=29, seconds=59))
        assert not dialogo.vigente(AHORA + timedelta(minutes=30))


class TestInvariantes:
    def test_elegir_algo_exige_opciones(self) -> None:
        with pytest.raises(InvarianteViolada):
            Dialogo.nuevo(PasoDelDialogo.ELEGIR_HORARIO, AHORA)

    def test_pedir_el_cuando_no_lleva_opciones(self) -> None:
        dialogo = Dialogo.nuevo(PasoDelDialogo.PEDIR_CUANDO, AHORA, servicio_id=uuid4())

        assert dialogo.opciones == ()

    def test_confirmar_una_cancelacion_lleva_exactamente_un_turno(self) -> None:
        with pytest.raises(InvarianteViolada):
            Dialogo.nuevo(
                PasoDelDialogo.CONFIRMAR_CANCELACION, AHORA, opciones=(un_turno(), un_turno())
            )

    def test_las_opciones_son_del_tipo_del_paso(self) -> None:
        with pytest.raises(InvarianteViolada):
            Dialogo.nuevo(PasoDelDialogo.ELEGIR_TURNO_A_CANCELAR, AHORA, opciones=(un_horario(),))
        with pytest.raises(InvarianteViolada):
            Dialogo.nuevo(PasoDelDialogo.ELEGIR_SERVICIO, AHORA, opciones=(un_turno(),))

    def test_no_vence_antes_de_abrirse(self) -> None:
        with pytest.raises(InvarianteViolada):
            Dialogo(paso=PasoDelDialogo.PEDIR_CUANDO, abierto_en=AHORA, vence_en=AHORA)

    def test_los_servicios_se_eligen_solo_por_orden(self) -> None:
        dialogo = Dialogo.nuevo(
            PasoDelDialogo.ELEGIR_SERVICIO,
            AHORA,
            opciones=(OpcionDeServicio(id=uuid4(), nombre="Corte"),),
        )

        assert dialogo.inicios == [None]


class TestEnLaConversacion:
    def test_se_abre_y_se_cierra(self) -> None:
        hilo = Conversacion(id=uuid4(), empresa_id=EmpresaId(uuid4()), cliente_id=uuid4())
        dialogo = Dialogo.nuevo(PasoDelDialogo.PEDIR_CUANDO, AHORA, servicio_id=uuid4())

        hilo.abrir_dialogo(dialogo)
        assert hilo.dialogo == dialogo

        hilo.cerrar_dialogo()
        assert hilo.dialogo is None

    def test_cerrar_sin_dialogo_no_hace_nada(self) -> None:
        hilo = Conversacion(id=uuid4(), empresa_id=EmpresaId(uuid4()), cliente_id=uuid4())

        hilo.cerrar_dialogo()

        assert hilo.dialogo is None
