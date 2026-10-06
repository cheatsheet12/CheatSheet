"""HS-T2 RN-04 — el horario de atención: invariantes y forma JSON (casos 1 y 2, 11 del plan)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.contexts.business_config.domain.horario_de_atencion import (
    MENSAJE_CIERRE_ANTES_QUE_APERTURA,
    MENSAJE_DEMASIADAS_FECHAS,
    MENSAJE_FORMATO_DE_HORA,
    MENSAJE_FRANJAS_DESORDENADAS,
    MENSAJE_FRANJAS_SUPERPUESTAS,
    MENSAJE_SIN_DIAS,
    ConfiguracionDeAtencion,
    FranjaDeAtencion,
    PoliticaFueraDeHorario,
)
from cheatsheet.contexts.business_config.domain.horario_de_atencion_json import (
    MENSAJE_FORMATO_DE_FECHA,
    MENSAJE_POLITICA_INVALIDA,
    MENSAJE_VERSION_DESCONOCIDA,
    como_json,
    desde_json,
)
from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio, TipoRegla
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida


def _franja(desde: str, hasta: str) -> FranjaDeAtencion:
    return FranjaDeAtencion.desde_textos(desde, hasta)


def _json(**cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "version": 1,
        "politica": "AGENTE_RESPONDE",
        "dias": [{"dia": 0, "franjas": [{"desde": "09:00", "hasta": "19:00"}]}],
        "fechas_cerradas": [],
    }
    base.update(cambios)
    return base


def _dias(*franjas: tuple[str, str]) -> dict[int, tuple[FranjaDeAtencion, ...]]:
    return {0: tuple(_franja(desde, hasta) for desde, hasta in franjas)}


def test_ida_y_vuelta_con_dos_franjas_en_un_dia_y_fechas() -> None:
    configuracion = ConfiguracionDeAtencion(
        dias={
            0: (_franja("09:00", "13:00"), _franja("16:00", "20:00")),
            5: (_franja("09:00", "14:00"),),
        },
        fechas_cerradas=frozenset({date(2026, 10, 14), date(2026, 10, 12)}),
        politica=PoliticaFueraDeHorario.MENSAJE_FIJO,
    )

    crudo = como_json(configuracion)

    assert crudo == {
        "version": 1,
        "politica": "MENSAJE_FIJO",
        "dias": [
            {
                "dia": 0,
                "franjas": [
                    {"desde": "09:00", "hasta": "13:00"},
                    {"desde": "16:00", "hasta": "20:00"},
                ],
            },
            {"dia": 5, "franjas": [{"desde": "09:00", "hasta": "14:00"}]},
        ],
        "fechas_cerradas": ["2026-10-12", "2026-10-14"],
    }
    assert desde_json(crudo) == configuracion


def test_el_fin_del_dia_se_escribe_24_00() -> None:
    configuracion = ConfiguracionDeAtencion(dias={0: (_franja("20:00", "24:00"),)})

    assert como_json(configuracion)["dias"][0]["franjas"] == [{"desde": "20:00", "hasta": "24:00"}]
    assert desde_json(como_json(configuracion)) == configuracion


def test_la_politica_por_defecto_es_que_el_agente_responde() -> None:
    assert (
        ConfiguracionDeAtencion(dias=_dias(("09:00", "19:00"))).politica
        is PoliticaFueraDeHorario.AGENTE_RESPONDE
    )


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [("19:00", "09:00"), ("09:00", "09:00"), ("00:00", "00:00")],
)
def test_una_franja_con_cierre_no_posterior_a_la_apertura_se_rechaza(
    desde: str, hasta: str
) -> None:
    with pytest.raises(EntradaInvalida) as exc:
        _franja(desde, hasta)

    assert str(exc.value) == MENSAJE_CIERRE_ANTES_QUE_APERTURA


@pytest.mark.parametrize("texto", ["9:00", "09:0", "24:01", "25:00", "09-00", "", "0900"])
def test_una_hora_mal_escrita_se_rechaza(texto: str) -> None:
    with pytest.raises(EntradaInvalida) as exc:
        _franja(texto, "19:00")

    assert str(exc.value) == MENSAJE_FORMATO_DE_HORA


def test_dos_franjas_superpuestas_se_rechazan() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        ConfiguracionDeAtencion(dias=_dias(("09:00", "13:00"), ("12:00", "16:00")))

    assert str(exc.value) == MENSAJE_FRANJAS_SUPERPUESTAS


def test_dos_franjas_que_se_tocan_se_rechazan() -> None:
    """`09-13` y `13-16` son una sola franja `09-16`: una única forma de escribir el horario."""
    with pytest.raises(EntradaInvalida) as exc:
        ConfiguracionDeAtencion(dias=_dias(("09:00", "13:00"), ("13:00", "16:00")))

    assert str(exc.value) == MENSAJE_FRANJAS_SUPERPUESTAS


def test_dos_franjas_desordenadas_se_rechazan() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        ConfiguracionDeAtencion(dias=_dias(("16:00", "20:00"), ("09:00", "13:00")))

    assert str(exc.value) == MENSAJE_FRANJAS_DESORDENADAS


def test_ningun_dia_con_franja_no_es_un_horario() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        ConfiguracionDeAtencion(dias={})
    assert str(exc.value) == MENSAJE_SIN_DIAS

    with pytest.raises(EntradaInvalida) as exc:
        desde_json(_json(dias=[{"dia": 0, "franjas": []}]))
    assert str(exc.value) == MENSAJE_SIN_DIAS


def test_un_dia_fuera_de_0_a_6_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida):
        desde_json(_json(dias=[{"dia": 7, "franjas": [{"desde": "09:00", "hasta": "10:00"}]}]))


def test_un_dia_repetido_se_rechaza() -> None:
    franjas = [{"desde": "09:00", "hasta": "10:00"}]

    with pytest.raises(EntradaInvalida) as exc:
        desde_json(_json(dias=[{"dia": 1, "franjas": franjas}, {"dia": 1, "franjas": franjas}]))

    assert "repetido" in str(exc.value)


def test_una_version_desconocida_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        desde_json(_json(version=2))
    assert str(exc.value) == MENSAJE_VERSION_DESCONOCIDA

    sin_version = _json()
    del sin_version["version"]
    with pytest.raises(EntradaInvalida):
        desde_json(sin_version)


def test_una_politica_fuera_del_enum_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        desde_json(_json(politica="SILENCIO"))

    assert str(exc.value) == MENSAJE_POLITICA_INVALIDA


@pytest.mark.parametrize("fecha", ["12/10/2026", "2026-13-01", "2026-02-30", "20261012", 20261012])
def test_una_fecha_mal_escrita_se_rechaza(fecha: object) -> None:
    with pytest.raises(EntradaInvalida) as exc:
        desde_json(_json(fechas_cerradas=[fecha]))

    assert str(exc.value) == MENSAJE_FORMATO_DE_FECHA


def test_una_fecha_repetida_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        desde_json(_json(fechas_cerradas=["2026-10-12", "2026-10-12"]))

    assert str(exc.value) == "La fecha 2026-10-12 está repetida."


def test_200_fechas_se_aceptan_y_201_se_rechazan() -> None:
    def fechas(cantidad: int) -> list[str]:
        return [
            date.fromordinal(date(2026, 1, 1).toordinal() + i).isoformat() for i in range(cantidad)
        ]

    assert len(desde_json(_json(fechas_cerradas=fechas(200))).fechas_cerradas) == 200
    with pytest.raises(EntradaInvalida) as exc:
        desde_json(_json(fechas_cerradas=fechas(201)))

    assert str(exc.value) == MENSAJE_DEMASIADAS_FECHAS


# --------------------------------------------------------------------- caso 2: la versión


def test_un_json_v1_sin_fechas_cerradas_se_lee_con_la_lista_vacia() -> None:
    crudo = _json()
    del crudo["fechas_cerradas"]

    configuracion = desde_json(crudo)

    assert configuracion.fechas_cerradas == frozenset()
    assert como_json(configuracion)["fechas_cerradas"] == []


def test_la_escritura_ordena_y_solo_incluye_los_dias_con_franjas() -> None:
    configuracion = ConfiguracionDeAtencion(
        dias={3: (_franja("09:00", "10:00"),), 1: (_franja("09:00", "10:00"),), 2: ()}
    )

    assert [dia["dia"] for dia in como_json(configuracion)["dias"]] == [1, 3]


# --------------------------------------------------------------------- caso 11: la regla


def test_la_regla_de_horario_se_interpreta_y_la_de_otro_tipo_no() -> None:
    horario = ReglaDeNegocio(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        tipo=TipoRegla.HORARIO_DE_ATENCION,
        configuracion=_json(),
        created_at=datetime(2026, 10, 5, tzinfo=UTC),
    )
    escalamiento = ReglaDeNegocio(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        tipo=TipoRegla.ESCALAMIENTO_DE_COBRO,
        configuracion={"pasos": []},
        created_at=datetime(2026, 10, 5, tzinfo=UTC),
    )

    assert TipoRegla("HORARIO_DE_ATENCION") is TipoRegla.HORARIO_DE_ATENCION
    assert horario.interpretada_como_atencion().dias[0] == (_franja("09:00", "19:00"),)
    with pytest.raises(EntradaInvalida):
        escalamiento.interpretada_como_atencion()
