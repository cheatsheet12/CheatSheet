"""H3: el buscador de clientes tiene que encontrar el CUIT tal como la pantalla lo muestra.

La consulta contra la base se prueba en `tests/integracion/test_clientes_postgres.py`; acá va la
parte pura: que patron se le pasa a la columna, que guarda solo digitos.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.master_data.infrastructure.repositories import _patron_de_cuit


@pytest.mark.parametrize(
    ("texto", "patron"),
    [
        ("30-71234567-1", "%30712345671%"),
        ("30-7123", "%307123%"),
        ("30 71234567 1", "%30712345671%"),
        ("30.71234567.1", "%30712345671%"),
        ("7123", "%7123%"),
    ],
)
def test_un_texto_con_forma_de_cuit_se_reduce_a_sus_digitos(texto: str, patron: str) -> None:
    assert _patron_de_cuit(texto) == patron


@pytest.mark.parametrize(
    ("texto", "patron"),
    [
        ("Rosa", "%rosa%"),
        ("Panaderia 2", "%panaderia 2%"),
        ("3M Argentina", "%3m argentina%"),
        ("-", "%-%"),
    ],
)
def test_un_texto_con_letras_o_sin_digitos_se_compara_como_se_escribio(
    texto: str, patron: str
) -> None:
    assert _patron_de_cuit(texto) == patron
