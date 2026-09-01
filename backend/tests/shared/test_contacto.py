"""`Email` y `Telefono` — los dos value objects de contacto del Shared Kernel.

`Email` se mudó acá desde `identity/domain/valores.py` en el épico 3, así que la mitad de
este archivo prueba comportamiento que ya existía y la otra mitad prueba `Telefono`, que
es nuevo. El test que ata las dos cosas es el último: los imports viejos siguen andando.
"""

from __future__ import annotations

import pytest
from cheatsheet.shared.contacto import (
    LARGO_MAXIMO_TELEFONO,
    LARGO_MINIMO_TELEFONO,
    Email,
    Telefono,
)
from cheatsheet.shared.errors import EntradaInvalida


def test_el_email_se_normaliza_a_minusculas_y_sin_espacios() -> None:
    assert Email("  Ana@Ejemplo.COM ").valor == "ana@ejemplo.com"


def test_dos_emails_que_solo_difieren_en_mayusculas_son_el_mismo() -> None:
    """Es la razón por la que existe la normalización: HU-E1-01 RN-03."""
    assert Email("Ana@x.com") == Email("ana@x.com")


@pytest.mark.parametrize("valor", ["sin-arroba", "dos@@arrobas.com", "sin@punto", "", "a@b.c d"])
def test_un_email_mal_formado_no_construye(valor: str) -> None:
    with pytest.raises(EntradaInvalida):
        Email(valor)


def test_el_telefono_se_queda_solo_con_los_digitos() -> None:
    """`+54 9 11 1234-5678` y `5491112345678` son el mismo número."""
    assert Telefono("+54 9 11 1234-5678") == Telefono("5491112345678")
    assert Telefono("+54 9 11 1234-5678").valor == "5491112345678"


def test_el_telefono_acepta_un_numero_local_sin_prefijo() -> None:
    """Diez dígitos, que es como la mayoría de la gente carga un contacto."""
    assert Telefono("11 1234-5678").valor == "1112345678"


@pytest.mark.parametrize("digitos", [LARGO_MINIMO_TELEFONO - 1, LARGO_MAXIMO_TELEFONO + 1])
def test_un_telefono_fuera_de_rango_no_construye(digitos: int) -> None:
    with pytest.raises(EntradaInvalida, match="telefono"):
        Telefono("1" * digitos)


@pytest.mark.parametrize("digitos", [LARGO_MINIMO_TELEFONO, LARGO_MAXIMO_TELEFONO])
def test_los_extremos_del_rango_si_construyen(digitos: int) -> None:
    assert Telefono("1" * digitos).valor == "1" * digitos


def test_el_telefono_no_valida_el_pais_ni_la_linea() -> None:
    """A propósito: quien decide si un número es alcanzable es WhatsApp, en el épico 8.

    Rechazar acá un número raro pero real es peor que guardar uno que Meta después
    rechace — es la misma razón por la que `CUIT` no valida su prefijo.
    """
    assert Telefono("999999999999").valor == "999999999999"


def test_los_imports_viejos_desde_identity_siguen_funcionando() -> None:
    """La mudanza no rompió las ~10 importaciones que ya existían de `Email` y `CUIT`."""
    from cheatsheet.contexts.identity.domain.valores import CUIT as CUITDesdeIdentity
    from cheatsheet.contexts.identity.domain.valores import Email as EmailDesdeIdentity
    from cheatsheet.shared.fiscal import CUIT as CUITDesdeShared

    assert EmailDesdeIdentity is Email
    assert CUITDesdeIdentity is CUITDesdeShared
