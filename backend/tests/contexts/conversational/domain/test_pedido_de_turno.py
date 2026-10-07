"""`PedidoDeTurno` y `resolver_dias` — el «para cuándo» del cliente, calculado por el código.

El modelo no sabe qué día es hoy y no se le dice (T5): devuelve una referencia relativa
(«jueves», «mañana») y es esta función pura la que la convierte en fechas. Por eso lo que se
prueba acá es el calendario, con un `hoy` fijo.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from cheatsheet.contexts.conversational.domain.pedido_de_turno import (
    AccionDeTurno,
    Cuando,
    MomentoDelDia,
    PedidoDeTurno,
    ReferenciaDeDia,
    coincidir_servicio,
    resolver_dias,
)
from cheatsheet.shared.errors import EntradaInvalida

#: Un jueves; el primer test lo comprueba para no depender de la memoria de nadie.
JUEVES = date(2026, 10, 1)


def pedido(*cuandos: Cuando, hora: time | None = None) -> PedidoDeTurno:
    return PedidoDeTurno(accion=AccionDeTurno.RESERVAR, cuandos=cuandos, hora=hora)


def test_el_fixture_es_un_jueves() -> None:
    assert JUEVES.weekday() == 3


class TestResolverDias:
    def test_un_dia_de_la_semana_es_su_proxima_ocurrencia_y_hoy_cuenta(self) -> None:
        dias = resolver_dias(
            pedido(Cuando(ReferenciaDeDia.DIA_DE_SEMANA, dia_semana=3)), hoy=JUEVES
        )

        assert dias.fechas == (JUEVES,)
        assert not dias.paso_alguna

    def test_otro_dia_de_la_semana_es_el_que_viene(self) -> None:
        dias = resolver_dias(
            pedido(Cuando(ReferenciaDeDia.DIA_DE_SEMANA, dia_semana=1)), hoy=JUEVES
        )

        assert dias.fechas == (date(2026, 10, 6),)

    def test_las_referencias_relativas(self) -> None:
        todas = pedido(
            Cuando(ReferenciaDeDia.HOY),
            Cuando(ReferenciaDeDia.MANANA),
            Cuando(ReferenciaDeDia.PASADO_MANANA),
        )

        assert resolver_dias(todas, hoy=JUEVES).fechas == (
            date(2026, 10, 1),
            date(2026, 10, 2),
            date(2026, 10, 3),
        )

    def test_un_dia_del_mes_ya_pasado_es_el_del_mes_siguiente(self) -> None:
        hoy = date(2026, 10, 4)

        dias = resolver_dias(pedido(Cuando(ReferenciaDeDia.FECHA, dia=3)), hoy=hoy)

        assert dias.fechas == (date(2026, 11, 3),)
        assert not dias.paso_alguna

    def test_un_dia_y_mes_ya_pasados_son_pasado(self) -> None:
        """CA6: «2 de octubre» con hoy 4/10 es una fecha que ya pasó, no la del año que viene."""
        hoy = date(2026, 10, 4)

        dias = resolver_dias(pedido(Cuando(ReferenciaDeDia.FECHA, dia=2, mes=10)), hoy=hoy)

        assert dias.fechas == ()
        assert dias.paso_alguna

    def test_un_dia_y_mes_futuros(self) -> None:
        dias = resolver_dias(
            pedido(Cuando(ReferenciaDeDia.FECHA, dia=14, mes=10)), hoy=date(2026, 10, 4)
        )

        assert dias.fechas == (date(2026, 10, 14),)

    def test_una_fecha_imposible_se_ignora_sin_decir_que_paso(self) -> None:
        dias = resolver_dias(
            pedido(Cuando(ReferenciaDeDia.FECHA, dia=31, mes=2)), hoy=date(2026, 1, 4)
        )

        assert dias.fechas == ()
        assert not dias.paso_alguna

    def test_una_hora_de_hoy_que_ya_paso_es_pasado(self) -> None:
        """CA6: «hoy a las 9» cuando son las 11."""
        dias = resolver_dias(
            pedido(Cuando(ReferenciaDeDia.HOY), hora=time(9)), hoy=JUEVES, ahora_local=time(11)
        )

        assert dias.fechas == ()
        assert dias.paso_alguna

    def test_una_hora_de_hoy_que_todavia_no_paso_se_conserva(self) -> None:
        dias = resolver_dias(
            pedido(Cuando(ReferenciaDeDia.HOY), hora=time(15)), hoy=JUEVES, ahora_local=time(11)
        )

        assert dias.fechas == (JUEVES,)

    def test_no_repite_ni_desordena_las_fechas(self) -> None:
        dias = resolver_dias(
            pedido(
                Cuando(ReferenciaDeDia.MANANA),
                Cuando(ReferenciaDeDia.HOY),
                Cuando(ReferenciaDeDia.MANANA),
            ),
            hoy=JUEVES,
        )

        assert dias.fechas == (date(2026, 10, 1), date(2026, 10, 2))


class TestValidacion:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"referencia": ReferenciaDeDia.DIA_DE_SEMANA},
            {"referencia": ReferenciaDeDia.DIA_DE_SEMANA, "dia_semana": 9},
            {"referencia": ReferenciaDeDia.FECHA},
            {"referencia": ReferenciaDeDia.FECHA, "dia": 32},
            {"referencia": ReferenciaDeDia.FECHA, "dia": 3, "mes": 13},
        ],
    )
    def test_un_cuando_incompleto_o_fuera_de_rango_se_rechaza(
        self, kwargs: dict[str, object]
    ) -> None:
        with pytest.raises(EntradaInvalida):
            Cuando(**kwargs)  # type: ignore[arg-type]

    def test_a_lo_sumo_tres_cuandos(self) -> None:
        with pytest.raises(EntradaInvalida):
            PedidoDeTurno(
                accion=AccionDeTurno.RESERVAR,
                cuandos=tuple(Cuando(ReferenciaDeDia.HOY) for _ in range(4)),
            )

    def test_el_servicio_es_corto(self) -> None:
        with pytest.raises(EntradaInvalida):
            PedidoDeTurno(accion=AccionDeTurno.RESERVAR, servicio="x" * 61)

    def test_los_momentos_parten_el_dia_en_tres(self) -> None:
        assert MomentoDelDia.MANANA.contiene(time(12, 59))
        assert MomentoDelDia.TARDE.contiene(time(13))
        assert MomentoDelDia.TARDE.contiene(time(19, 59))
        assert MomentoDelDia.NOCHE.contiene(time(20))
        assert not MomentoDelDia.TARDE.contiene(time(20))


class TestCoincidirServicio:
    CATALOGO = ("Corte", "Color", "Consulta general")

    @pytest.mark.parametrize(
        ("texto", "indice"),
        [
            ("corte", 0),
            ("Un turno para corte", 0),
            ("quiero color", 1),
            ("consulta", 2),
            ("la consulta general", 2),
        ],
    )
    def test_un_nombre_del_catalogo_en_el_texto_elige_ese_servicio(
        self, texto: str, indice: int
    ) -> None:
        assert coincidir_servicio(self.CATALOGO, texto) == indice

    @pytest.mark.parametrize(
        "texto", ["corte y color", "masajes", "", None, "un turno para mañana"]
    )
    def test_sin_coincidencia_unica_no_elige(self, texto: str | None) -> None:
        assert coincidir_servicio(self.CATALOGO, texto) is None

    def test_ignora_tildes_y_mayusculas(self) -> None:
        assert coincidir_servicio(("Depilación",), "DEPILACION") == 0

    def test_el_nombre_exacto_gana_sobre_el_que_lo_contiene(self) -> None:
        assert coincidir_servicio(("Corte", "Corte y color"), "corte") == 0


class TestCompletarCon:
    def test_lo_que_no_dijo_sale_del_pedido_anterior(self) -> None:
        previo = PedidoDeTurno(
            accion=AccionDeTurno.RESERVAR, momento=MomentoDelDia.TARDE, servicio="corte"
        )
        nuevo = PedidoDeTurno(
            accion=AccionDeTurno.RESERVAR, cuandos=(Cuando(ReferenciaDeDia.MANANA),)
        )

        completo = nuevo.completar_con(previo)

        assert completo.cuandos == nuevo.cuandos
        assert completo.momento is MomentoDelDia.TARDE
        assert completo.servicio == "corte"

    def test_lo_que_si_dijo_pisa_al_anterior(self) -> None:
        previo = PedidoDeTurno(accion=AccionDeTurno.RESERVAR, hora=time(9))
        nuevo = PedidoDeTurno(accion=AccionDeTurno.RESERVAR, hora=time(0))

        assert nuevo.completar_con(previo).hora == time(0)

    def test_dice_algo_del_cuando(self) -> None:
        assert not PedidoDeTurno(accion=AccionDeTurno.RESERVAR).dice_algo_del_cuando
        assert PedidoDeTurno(
            accion=AccionDeTurno.RESERVAR, momento=MomentoDelDia.NOCHE
        ).dice_algo_del_cuando
