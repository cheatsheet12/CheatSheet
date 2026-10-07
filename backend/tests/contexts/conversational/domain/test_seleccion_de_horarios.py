"""`elegir_horarios` — qué se le ofrece al cliente de todo lo que hay libre (T6).

El defecto que esta función corrige es el de la unidad anterior: con un recurso que abre a las
9, el agente ofrecía siempre 9:00, 9:30 y 10:00 de mañana. Acá los horarios se **reparten** en el
día, para que haya mañana y tarde, y se respeta lo que el cliente dijo (franja, hora, varios
días).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.domain.dialogo import OpcionDeHorario
from cheatsheet.contexts.conversational.domain.pedido_de_turno import MomentoDelDia
from cheatsheet.contexts.conversational.domain.seleccion_de_horarios import (
    HORARIOS_A_OFRECER,
    HorarioOfrecible,
    elegir_horarios,
)
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

DIA = date(2026, 10, 8)
SERVICIO = uuid4()
RECURSO = uuid4()


def local(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime.combine(dia, time(hora, minuto), tzinfo=ZONA_ARGENTINA)


def grilla(
    dia: date = DIA, *, desde: int = 9, hasta: int = 18, recurso: UUID = RECURSO
) -> list[HorarioOfrecible]:
    """Un inicio cada 30 minutos, de `desde` a `hasta` exclusive."""
    inicio = local(dia, desde)
    cantidad = (hasta - desde) * 2
    return [
        HorarioOfrecible(
            recurso_id=recurso, servicio_id=SERVICIO, inicio=inicio + timedelta(minutes=30 * i)
        )
        for i in range(cantidad)
    ]


def horas(opciones: list[OpcionDeHorario]) -> list[time]:
    return [uno.inicio.astimezone(ZONA_ARGENTINA).time() for uno in opciones]


class TestSinPreferencia:
    def test_ofrece_cuatro_repartidos_entre_la_manana_y_la_tarde(self) -> None:
        """RED del caso 9: antes eran 9:00, 9:30 y 10:00, siempre de mañana."""
        opciones = elegir_horarios([grilla()])

        assert len(opciones) == HORARIOS_A_OFRECER == 4
        assert horas(opciones) == [time(9), time(11), time(13, 30), time(15, 30)]
        assert any(hora >= time(13) for hora in horas(opciones))

    def test_si_hay_menos_de_los_que_se_ofrecen_ofrece_todos(self) -> None:
        opciones = elegir_horarios([grilla(desde=9, hasta=10)])

        assert horas(opciones) == [time(9), time(9, 30)]

    def test_sin_libres_no_ofrece_nada(self) -> None:
        assert elegir_horarios([]) == []
        assert elegir_horarios([[]]) == []


class TestConFranja:
    def test_con_tarde_todos_son_de_la_tarde(self) -> None:
        opciones = elegir_horarios([grilla()], momento=MomentoDelDia.TARDE)

        assert len(opciones) == 4
        assert all(time(13) <= hora < time(20) for hora in horas(opciones))

    def test_una_franja_sin_libres_no_ofrece_nada(self) -> None:
        assert elegir_horarios([grilla(desde=9, hasta=12)], momento=MomentoDelDia.NOCHE) == []


class TestConHora:
    def test_la_hora_pedida_si_esta_libre_se_ofrece_sola(self) -> None:
        opciones = elegir_horarios([grilla()], hora=time(16))

        assert horas(opciones) == [time(16)]

    def test_la_hora_pedida_ocupada_ofrece_las_mas_cercanas_en_orden_cronologico(self) -> None:
        libres = [uno for uno in grilla() if uno.inicio != local(DIA, 16)]

        opciones = elegir_horarios([libres], hora=time(16))

        assert horas(opciones) == [time(15), time(15, 30), time(16, 30), time(17)]


class TestVariosRecursos:
    def test_el_mismo_inicio_en_dos_recursos_es_una_sola_opcion_con_los_dos(self) -> None:
        otro = uuid4()
        libres = grilla(desde=9, hasta=10) + grilla(desde=9, hasta=10, recurso=otro)

        opciones = elegir_horarios([libres])

        assert horas(opciones) == [time(9), time(9, 30)]
        assert opciones[0].recursos == (RECURSO, otro)


class TestVariosDias:
    def test_reparte_el_cupo_entre_los_dias(self) -> None:
        jueves, viernes = DIA, DIA + timedelta(days=1)

        opciones = elegir_horarios([grilla(jueves), grilla(viernes)])

        dias = [uno.inicio.astimezone(ZONA_ARGENTINA).date() for uno in opciones]
        assert dias == [jueves, jueves, viernes, viernes]

    def test_un_dia_sin_libres_no_se_lleva_cupo(self) -> None:
        opciones = elegir_horarios([[], grilla()])

        assert len(opciones) == 4
