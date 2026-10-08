"""HS-T2 RN-04 — el cálculo de «¿está abierto?» (casos 3 a 10 del plan).

Fechas de ejemplo: el lunes 05/10/2026; el 12/10 es lunes, el 13/10 martes, el 14/10 miércoles.
Todo se evalúa en hora argentina: un `datetime` UTC comparado contra un horario local es el bug
clásico del borde de la medianoche.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from cheatsheet.contexts.business_config.domain.apertura import (
    HORIZONTE_DIAS,
    SIEMPRE_ABIERTO,
    cerrado_desde,
    esta_abierto,
    estado_de_atencion,
    proxima_apertura,
)
from cheatsheet.contexts.business_config.domain.horario_de_atencion import (
    ConfiguracionDeAtencion,
    FranjaDeAtencion,
    PoliticaFueraDeHorario,
)
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA


def _f(desde: str, hasta: str) -> FranjaDeAtencion:
    return FranjaDeAtencion.desde_textos(desde, hasta)


def _local(dia: int, hora: int = 0, minuto: int = 0, mes: int = 10) -> datetime:
    return datetime(2026, mes, dia, hora, minuto, tzinfo=ZONA_ARGENTINA)


def _tipico(
    *cerradas: date, politica: PoliticaFueraDeHorario | None = None
) -> ConfiguracionDeAtencion:
    """Lunes a viernes 09-19, sábado 09-14, domingo cerrado."""
    dias = {dia: (_f("09:00", "19:00"),) for dia in range(5)}
    dias[5] = (_f("09:00", "14:00"),)
    return ConfiguracionDeAtencion(
        dias=dias,
        fechas_cerradas=frozenset(cerradas),
        politica=politica or PoliticaFueraDeHorario.AGENTE_RESPONDE,
    )


# --------------------------------------------------------------------- caso 3


def test_los_bordes_de_la_franja_son_semiabiertos() -> None:
    config = _tipico()

    assert not esta_abierto(config, _local(5, 8, 59))
    assert esta_abierto(config, _local(5, 9, 0))
    assert esta_abierto(config, _local(5, 18, 59))
    assert not esta_abierto(config, _local(5, 19, 0))


def test_un_segundo_antes_del_cierre_sigue_abierto() -> None:
    assert esta_abierto(_tipico(), _local(5, 18, 59).replace(second=59))


# --------------------------------------------------------------------- caso 4


def test_el_borde_de_medianoche_se_decide_en_hora_argentina_no_en_utc() -> None:
    config = ConfiguracionDeAtencion(dias={0: (_f("20:00", "24:00"),)})

    # 23:59 del lunes en Argentina es el martes 02:59 en UTC.
    assert esta_abierto(config, datetime(2026, 10, 6, 2, 59, tzinfo=UTC))
    assert not esta_abierto(config, datetime(2026, 10, 6, 3, 0, tzinfo=UTC))


# --------------------------------------------------------------------- caso 5


def test_dos_dias_contiguos_forman_un_solo_tramo() -> None:
    config = ConfiguracionDeAtencion(dias={0: (_f("20:00", "24:00"),), 1: (_f("00:00", "02:00"),)})

    assert esta_abierto(config, _local(5, 23, 59))
    assert esta_abierto(config, _local(6, 0, 0))
    assert not esta_abierto(config, _local(6, 2, 0))
    # Cerrado el martes 03:00: el último cierre es el del martes 02:00, no el de la medianoche.
    assert cerrado_desde(config, _local(6, 3, 0)) == _local(6, 2, 0)
    assert proxima_apertura(config, _local(6, 3, 0)) == _local(12, 20, 0)


def test_con_el_martes_sin_atencion_el_lunes_cierra_a_las_24() -> None:
    config = ConfiguracionDeAtencion(
        dias={0: (_f("20:00", "24:00"),), 1: (_f("00:00", "02:00"),)},
        fechas_cerradas=frozenset({date(2026, 10, 6)}),
    )

    assert not esta_abierto(config, _local(6, 0, 30))
    assert cerrado_desde(config, _local(6, 0, 30)) == _local(6, 0, 0)


# --------------------------------------------------------------------- caso 6


def test_horario_cortado_el_hueco_del_mediodia_es_fuera_de_horario() -> None:
    config = ConfiguracionDeAtencion(dias={0: (_f("09:00", "13:00"), _f("16:00", "20:00"))})

    assert esta_abierto(config, _local(5, 12, 59))
    assert not esta_abierto(config, _local(5, 13, 0))
    assert not esta_abierto(config, _local(5, 13, 30))
    assert proxima_apertura(config, _local(5, 13, 30)) == _local(5, 16, 0)
    assert cerrado_desde(config, _local(5, 13, 30)) == _local(5, 13, 0)
    assert esta_abierto(config, _local(5, 16, 0))
    assert not esta_abierto(config, _local(5, 20, 0))
    assert cerrado_desde(config, _local(5, 20, 0)) == _local(5, 20, 0)
    assert proxima_apertura(config, _local(5, 20, 0)) == _local(12, 9, 0)


# --------------------------------------------------------------------- caso 7


def test_el_domingo_cerrado_y_la_proxima_apertura() -> None:
    config = _tipico()

    assert not esta_abierto(config, _local(4, 12, 0))  # domingo 04/10
    assert proxima_apertura(config, _local(3, 14, 0)) == _local(5, 9, 0)  # sábado 14:00


def test_con_un_solo_dia_abierto_la_apertura_es_el_mismo_dia_de_la_semana_siguiente() -> None:
    config = ConfiguracionDeAtencion(dias={0: (_f("09:00", "19:00"),)})

    assert proxima_apertura(config, _local(5, 19, 0)) == _local(12, 9, 0)


def test_si_esta_abierto_la_proxima_apertura_es_ahora() -> None:
    ahora = _local(5, 10, 0)

    assert proxima_apertura(_tipico(), ahora) == ahora


# --------------------------------------------------------------------- caso 8


def test_cerrado_desde() -> None:
    config = _tipico()

    assert cerrado_desde(config, _local(5, 22, 0)) == _local(5, 19, 0)
    assert cerrado_desde(config, _local(4, 10, 0)) == _local(3, 14, 0)  # domingo → sábado 14:00
    assert cerrado_desde(config, _local(5, 8, 0)) == _local(3, 14, 0)  # lunes 08:00


# --------------------------------------------------------------------- caso 9


def test_una_fecha_sin_atencion_cierra_el_dia_aunque_tenga_franja() -> None:
    config = _tipico(date(2026, 10, 12), date(2026, 10, 14))

    assert not esta_abierto(config, _local(12, 10, 0))
    assert proxima_apertura(config, _local(10, 20, 0)) == _local(13, 9, 0)
    assert cerrado_desde(config, _local(12, 10, 0)) == _local(10, 14, 0)
    assert cerrado_desde(config, _local(14, 10, 0)) == _local(13, 19, 0)
    assert proxima_apertura(config, _local(14, 10, 0)) == _local(15, 9, 0)


def test_la_fecha_sin_atencion_se_compara_con_la_fecha_local_no_con_la_de_utc() -> None:
    config = ConfiguracionDeAtencion(
        dias={0: (_f("20:00", "24:00"),)}, fechas_cerradas=frozenset({date(2026, 10, 6)})
    )

    # Lunes 05/10 23:30 local = martes 06/10 02:30Z: en UTC ya es la fecha sin atención.
    assert esta_abierto(config, datetime(2026, 10, 6, 2, 30, tzinfo=UTC))


# --------------------------------------------------------------------- caso 10


def test_sin_apertura_en_el_horizonte_devuelve_none() -> None:
    lunes = [date(2026, 10, 5) + timedelta(weeks=n) for n in range(54)]
    config = ConfiguracionDeAtencion(
        dias={0: (_f("09:00", "19:00"),)}, fechas_cerradas=frozenset(lunes[1:54][:53])
    )

    # Sólo se cargan 53 de los 200 posibles: el lunes de hoy (cerrado a las 22) no cuenta.
    assert HORIZONTE_DIAS == 366
    assert proxima_apertura(config, _local(5, 22, 0)) is None


def test_sin_franja_terminada_en_el_horizonte_cerrado_desde_es_el_borde_de_la_ventana() -> None:
    config = ConfiguracionDeAtencion(
        dias={0: (_f("09:00", "19:00"),)},
        fechas_cerradas=frozenset(date(2026, 10, 5) - timedelta(weeks=n) for n in range(0, 54)),
    )
    ahora = _local(5, 22, 0)

    assert cerrado_desde(config, ahora) == ahora - timedelta(days=HORIZONTE_DIAS)


def test_una_fecha_sin_atencion_de_ayer_sigue_contando_para_cerrado_desde() -> None:
    config = _tipico(date(2026, 10, 12))  # lunes sin atención

    # Martes 13/10 08:00: el último cierre fue el sábado 10/10 14:00, porque ayer no hubo atención.
    assert cerrado_desde(config, _local(13, 8, 0)) == _local(10, 14, 0)


def test_una_fecha_a_mas_de_un_horizonte_no_cambia_el_calculo_de_hoy() -> None:
    lejana = date(2026, 10, 5) + timedelta(days=HORIZONTE_DIAS + 30)
    config = _tipico(lejana)
    ahora = _local(5, 22, 0)

    assert proxima_apertura(config, ahora) == _local(6, 9, 0)
    assert cerrado_desde(config, ahora) == _local(5, 19, 0)


# --------------------------------------------------------------------- el estado


def test_siempre_abierto_es_el_estado_sin_configuracion() -> None:
    assert SIEMPRE_ABIERTO.configurado is False
    assert SIEMPRE_ABIERTO.abierto is True
    assert SIEMPRE_ABIERTO.politica is PoliticaFueraDeHorario.AGENTE_RESPONDE


def test_el_estado_cerrado_trae_la_politica_la_apertura_y_el_cierre() -> None:
    config = _tipico(politica=PoliticaFueraDeHorario.MENSAJE_FIJO)

    estado = estado_de_atencion(config, _local(5, 22, 0))

    assert estado.configurado is True
    assert estado.abierto is False
    assert estado.politica is PoliticaFueraDeHorario.MENSAJE_FIJO
    assert estado.proxima_apertura == _local(6, 9, 0)
    assert estado.cerrado_desde == _local(5, 19, 0)


def test_el_estado_abierto_no_trae_cierre() -> None:
    estado = estado_de_atencion(_tipico(), _local(5, 10, 0))

    assert estado.abierto is True
    assert estado.cerrado_desde is None
