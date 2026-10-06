"""`leer_respuesta` y `elegir` — cómo se lee lo que el cliente contesta a una oferta (T3).

**Es un analizador determinista y no el modelo.** Con un diálogo vigente, «el primero» o «sí» se
leen acá: cero tokens, ningún dato al proveedor, y ninguna acción con efecto que dependa de una
salida de modelo. Por eso la lista es cerrada y con límites de palabra, y por eso lo que se prueba
con más cuidado es lo que **no** tiene que reconocer: una pregunta no es una elección, y «si hay
más tarde» no es un «sí».
"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest
from cheatsheet.contexts.conversational.domain.respuesta_del_cliente import (
    ULTIMO,
    Ambigua,
    FueraDeRango,
    HoraNoOfrecida,
    NoEsEleccion,
    Unica,
    elegir,
    leer_respuesta,
)
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA


def local(dia: int, hora: int, minuto: int = 0) -> datetime:
    """Un instante de octubre de 2026 en hora argentina. El 14/10 es miércoles."""
    return datetime.combine(date(2026, 10, dia), time(hora, minuto), tzinfo=ZONA_ARGENTINA)


#: Cuatro horarios en dos días: miércoles 14 y viernes 16.
OFERTA = [local(14, 10, 30), local(14, 16), local(16, 10, 30), local(16, 17)]


class TestOrdinales:
    @pytest.mark.parametrize(
        ("texto", "ordinal"),
        [
            ("1", 1),
            ("2", 2),
            ("el 2", 2),
            ("opción 3", 3),
            ("opcion 4", 4),
            ("Prefiero el primero", 1),
            ("el segundo", 2),
            ("la tercera", 3),
            ("el cuarto por favor", 4),
            ("el último", ULTIMO),
            ("2.", 2),
        ],
    )
    def test_lee_el_numero_o_la_palabra(self, texto: str, ordinal: int) -> None:
        assert leer_respuesta(texto).ordinal == ordinal

    @pytest.mark.parametrize("texto", ["hola, ¿cuánto sale?", "a las 5", "10:30", "17 hs"])
    def test_una_hora_o_una_pregunta_no_es_un_ordinal(self, texto: str) -> None:
        assert leer_respuesta(texto).ordinal is None


class TestHoras:
    @pytest.mark.parametrize(
        ("texto", "esperadas"),
        [
            ("10:30", (time(10, 30), time(22, 30))),
            ("10.30", (time(10, 30), time(22, 30))),
            ("10 y media", (time(10, 30), time(22, 30))),
            ("el de las 16", (time(16),)),
            ("17 hs", (time(17),)),
            ("a las 5", (time(17), time(5))),
            ("5 de la tarde", (time(17),)),
            ("a las 9 de la mañana", (time(9),)),
            ("a las 8 de la noche", (time(20),)),
        ],
    )
    def test_lee_la_hora_con_sus_lecturas_posibles(
        self, texto: str, esperadas: tuple[time, ...]
    ) -> None:
        assert leer_respuesta(texto).horas == esperadas

    def test_una_fecha_no_es_una_hora(self) -> None:
        assert leer_respuesta("el 14/10").horas == ()


class TestDiasYAfirmaciones:
    def test_lee_el_dia_de_la_semana(self) -> None:
        assert leer_respuesta("el del viernes").dias_semana == (4,)
        assert leer_respuesta("miércoles o sábado").dias_semana == (2, 5)

    @pytest.mark.parametrize(
        "texto", ["sí", "Si", "dale", "ok", "confirmo", "sí, confirmo", "dale gracias"]
    )
    def test_afirma(self, texto: str) -> None:
        respuesta = leer_respuesta(texto)
        assert respuesta.afirma
        assert not respuesta.niega

    @pytest.mark.parametrize("texto", ["no", "ninguno", "otro día", "otra fecha", "no, gracias"])
    def test_niega(self, texto: str) -> None:
        respuesta = leer_respuesta(texto)
        assert respuesta.niega
        assert not respuesta.afirma

    @pytest.mark.parametrize(
        "texto", ["si hay más tarde", "sí pero no sé", "no sé si puedo", "quiero cancelar todo"]
    )
    def test_una_frase_con_un_si_adentro_no_es_un_si(self, texto: str) -> None:
        """El riesgo real: reservar o cancelar por una subcadena. Sólo cuenta el mensaje que **es**
        una afirmación (o una negación), no el que la nombra de pasada."""
        respuesta = leer_respuesta(texto)
        assert not respuesta.afirma
        assert not respuesta.niega

    def test_un_si_y_un_no_juntos_no_son_ninguno(self) -> None:
        respuesta = leer_respuesta("sí no")
        assert not respuesta.afirma
        assert not respuesta.niega


class TestSoloUnMensajeConFormaDeEleccionEligeAlgo:
    """Nombrar un día o un ordinal de pasada no es elegir: sería reservar lo que nadie eligió."""

    @pytest.mark.parametrize(
        "texto",
        [
            "quiero un turno el viernes",
            "necesito un turno el segundo martes del mes",
            "un turno a las 10",
            "puedo ir a las 5",
            "mañana tengo el 2 de la facultad",
            "el viernes no puedo",
        ],
    )
    def test_un_pedido_que_nombra_un_dia_una_hora_o_un_ordinal_no_elige(self, texto: str) -> None:
        respuesta = leer_respuesta(texto)

        assert respuesta.ordinal is None
        assert respuesta.horas == ()
        assert respuesta.dias_semana == ()
        assert elegir(OFERTA, respuesta) == NoEsEleccion()

    @pytest.mark.parametrize(
        "texto", ["quiero el segundo", "me queda mejor el del viernes", "el de las 16, gracias"]
    )
    def test_una_eleccion_con_cortesias_si_elige(self, texto: str) -> None:
        assert not isinstance(elegir(OFERTA, leer_respuesta(texto)), NoEsEleccion)


class TestElegir:
    def test_por_orden(self) -> None:
        assert elegir(OFERTA, leer_respuesta("2")) == Unica(1)
        assert elegir(OFERTA, leer_respuesta("el segundo")) == Unica(1)
        assert elegir(OFERTA, leer_respuesta("opción 3")) == Unica(2)
        assert elegir(OFERTA, leer_respuesta("el último")) == Unica(3)

    def test_por_hora(self) -> None:
        assert elegir(OFERTA, leer_respuesta("el de las 16")) == Unica(1)
        assert elegir(OFERTA, leer_respuesta("10:30")) == Ambigua()
        assert elegir(OFERTA, leer_respuesta("17 hs")) == Unica(3)

    def test_las_diez_y_media_con_un_solo_dia_son_unicas(self) -> None:
        assert elegir(OFERTA[:2], leer_respuesta("10.30")) == Unica(0)
        assert elegir(OFERTA[:2], leer_respuesta("10 y media")) == Unica(0)

    def test_por_hora_y_dia(self) -> None:
        assert elegir(OFERTA, leer_respuesta("el de las 10:30 del viernes")) == Unica(2)

    def test_por_dia_si_es_uno_solo(self) -> None:
        solos = [local(14, 10), local(16, 10)]

        assert elegir(solos, leer_respuesta("el del viernes")) == Unica(1)
        assert elegir(OFERTA, leer_respuesta("el del viernes")) == Ambigua()

    def test_a_las_5_coincide_con_las_17_si_es_lo_ofrecido(self) -> None:
        assert elegir(OFERTA, leer_respuesta("a las 5")) == Unica(3)

    def test_a_las_5_con_las_5_y_las_17_ofrecidas_es_ambigua(self) -> None:
        ofrecidas = [local(14, 5), local(14, 17)]

        assert elegir(ofrecidas, leer_respuesta("a las 5")) == Ambigua()

    def test_un_ordinal_fuera_de_rango(self) -> None:
        assert elegir(OFERTA, leer_respuesta("7")) == FueraDeRango()
        assert elegir(OFERTA, leer_respuesta("0")) == FueraDeRango()

    def test_una_hora_que_no_se_ofrecio(self) -> None:
        assert elegir(OFERTA, leer_respuesta("a las 11")) == HoraNoOfrecida(time(11))
        assert elegir(OFERTA, leer_respuesta("a las 5 de la mañana")) == HoraNoOfrecida(time(5))

    def test_una_pregunta_no_es_una_eleccion(self) -> None:
        assert elegir(OFERTA, leer_respuesta("hola, ¿cuánto sale?")) == NoEsEleccion()
        assert elegir(OFERTA, leer_respuesta("")) == NoEsEleccion()

    def test_un_dia_que_no_se_ofrecio_pasa_al_interprete(self) -> None:
        assert elegir(OFERTA, leer_respuesta("el del sábado")) == NoEsEleccion()

    def test_cuando_las_opciones_no_tienen_hora_solo_se_elige_por_orden(self) -> None:
        servicios: list[datetime | None] = [None, None]

        assert elegir(servicios, leer_respuesta("2")) == Unica(1)
        assert elegir(servicios, leer_respuesta("a las 5")) == NoEsEleccion()
