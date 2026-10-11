"""HU-E11-01 / HU-E8-04 — la agenda de notificación: invariantes y forma JSON (casos 2 a 4)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.contexts.business_config.domain.agenda_de_notificacion import (
    AGENDA_POR_DEFECTO,
    MAXIMO_DE_RECORDATORIOS,
    MENSAJE_DEMASIADOS_RECORDATORIOS,
    MENSAJE_FORMA_INVALIDA,
    MENSAJE_HORAS_FUERA_DE_RANGO,
    MENSAJE_REPETIDOS,
    MENSAJE_SIN_RECORDATORIOS,
    AnticipacionDeRecordatorio,
    ConfiguracionDeAgenda,
)
from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio, TipoRegla
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida


def _agenda(*horas: int) -> ConfiguracionDeAgenda:
    return ConfiguracionDeAgenda(tuple(AnticipacionDeRecordatorio(h) for h in horas))


def test_la_anticipacion_expone_los_minutos() -> None:
    assert AnticipacionDeRecordatorio(24).minutos == 24 * 60


@pytest.mark.parametrize("horas", [0, -1, 169, 1000])
def test_las_horas_fuera_de_1_a_168_se_rechazan_con_la_frase(horas: int) -> None:
    with pytest.raises(EntradaInvalida) as exc:
        AnticipacionDeRecordatorio(horas)
    assert str(exc.value) == MENSAJE_HORAS_FUERA_DE_RANGO
    assert MENSAJE_HORAS_FUERA_DE_RANGO == "Las horas de anticipación deben estar entre 1 y 168."


@pytest.mark.parametrize("horas", [1, 168])
def test_los_bordes_del_rango_se_aceptan(horas: int) -> None:
    assert AnticipacionDeRecordatorio(horas).horas_antes == horas


def test_sin_recordatorios_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        ConfiguracionDeAgenda(())
    assert str(exc.value) == MENSAJE_SIN_RECORDATORIOS


def test_mas_de_tres_recordatorios_se_rechaza() -> None:
    assert MAXIMO_DE_RECORDATORIOS == 3
    with pytest.raises(EntradaInvalida) as exc:
        _agenda(1, 2, 3, 4)
    assert str(exc.value) == MENSAJE_DEMASIADOS_RECORDATORIOS


def test_los_repetidos_se_rechazan() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        _agenda(24, 24)
    assert str(exc.value) == MENSAJE_REPETIDOS


def test_se_ordenan_de_mayor_a_menor_anticipacion() -> None:
    agenda = _agenda(2, 48, 24)
    assert [a.horas_antes for a in agenda.recordatorios] == [48, 24, 2]
    assert agenda.anticipaciones_min == (48 * 60, 24 * 60, 2 * 60)


def test_el_default_es_un_recordatorio_a_24_horas() -> None:
    assert AGENDA_POR_DEFECTO.anticipaciones_min == (24 * 60,)


def test_ida_y_vuelta_json() -> None:
    agenda = _agenda(24, 2)
    assert agenda.como_json() == {"recordatorios": [{"horas_antes": 24}, {"horas_antes": 2}]}
    assert ConfiguracionDeAgenda.desde_json(agenda.como_json()) == agenda


@pytest.mark.parametrize(
    "crudo",
    [
        {},
        {"recordatorios": "24"},
        {"recordatorios": [24]},
        {"recordatorios": [{}]},
        {"recordatorios": [{"horas_antes": "veinticuatro"}]},
        {"recordatorios": [{"horas_antes": True}]},
        {"recordatorios": [{"horas_antes": 2.5}]},
    ],
)
def test_una_fila_mal_formada_falla_al_leer(crudo: dict[str, Any]) -> None:
    with pytest.raises(EntradaInvalida) as exc:
        ConfiguracionDeAgenda.desde_json(crudo)
    assert str(exc.value) == MENSAJE_FORMA_INVALIDA


def test_una_fila_con_valores_invalidos_falla_al_leer_con_la_frase_del_dominio() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        ConfiguracionDeAgenda.desde_json({"recordatorios": [{"horas_antes": 169}]})
    assert str(exc.value) == MENSAJE_HORAS_FUERA_DE_RANGO


def _regla(tipo: TipoRegla, configuracion: dict[str, Any]) -> ReglaDeNegocio:
    from datetime import UTC, datetime

    return ReglaDeNegocio(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        tipo=tipo,
        configuracion=configuracion,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


def test_interpretada_como_agenda_devuelve_la_configuracion_tipada() -> None:
    regla = _regla(TipoRegla.AGENDA_DE_NOTIFICACION, _agenda(24, 2).como_json())
    assert regla.interpretada_como_agenda() == _agenda(24, 2)


def test_interpretada_como_agenda_falla_si_el_tipo_no_es_el_pedido() -> None:
    regla = _regla(TipoRegla.POLITICA_DE_TURNO, {})
    with pytest.raises(EntradaInvalida):
        regla.interpretada_como_agenda()
