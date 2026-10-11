"""El `wamid` que no entra en su columna se guarda como «sin id», nunca cortado (U7, H3)."""

from __future__ import annotations

import pytest
from cheatsheet.shared.externo_id import LARGO_MAXIMO_EXTERNO_ID, externo_id_o_ninguno


def test_un_id_normal_se_conserva() -> None:
    assert externo_id_o_ninguno("wamid.HBgM123") == "wamid.HBgM123"


def test_un_id_justo_en_el_limite_se_conserva() -> None:
    justo = "w" * LARGO_MAXIMO_EXTERNO_ID

    assert externo_id_o_ninguno(justo) == justo


@pytest.mark.parametrize("invalido", [None, ""])
def test_un_id_ausente_o_vacio_es_ninguno(invalido: str | None) -> None:
    assert externo_id_o_ninguno(invalido) is None


def test_un_id_mas_largo_que_la_columna_es_ninguno_y_no_se_corta() -> None:
    assert externo_id_o_ninguno("w" * (LARGO_MAXIMO_EXTERNO_ID + 1)) is None
