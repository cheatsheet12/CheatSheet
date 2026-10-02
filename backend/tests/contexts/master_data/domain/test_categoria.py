"""El agregado `CategoriaEmpresa` — el ámbito, que es toda la regla.

HU-E4-04 RN-01 dice que sólo pueden asignarse categorías cuyo ámbito corresponda al
elemento. La pantalla lo cumple **escondiendo** las que no van; esconder no es rechazar, y
el que rechaza es este agregado. Por eso la mitad del archivo son las cuatro combinaciones
de ámbito contra elemento.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.master_data.domain.categoria import (
    AmbitoIncompatible,
    CategoriaEmpresa,
    clave_de_unicidad,
)
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

from tests.conftest import INSTANTE_FIJO

EMPRESA = EmpresaId(uuid4())


def _categoria(
    *, nombre: str = "VIP", aplica_a: AmbitoDeCategoria = AmbitoDeCategoria.CLIENTE
) -> CategoriaEmpresa:
    return CategoriaEmpresa.registrar(
        id=uuid4(),
        empresa_id=EMPRESA,
        nombre=nombre,
        aplica_a=aplica_a,
        momento=INSTANTE_FIJO,
    )


# --- El ámbito, en sus cuatro combinaciones ------------------------------------------


@pytest.mark.parametrize(
    ("ambito", "admite_clientes", "admite_servicios"),
    [
        (AmbitoDeCategoria.CLIENTE, True, False),
        (AmbitoDeCategoria.SERVICIO, False, True),
        (AmbitoDeCategoria.AMBOS, True, True),
    ],
)
def test_que_admite_cada_ambito(
    ambito: AmbitoDeCategoria, admite_clientes: bool, admite_servicios: bool
) -> None:
    categoria = _categoria(aplica_a=ambito)

    assert categoria.admite_clientes is admite_clientes
    assert categoria.admite_servicios is admite_servicios


def test_una_categoria_de_servicios_no_se_asigna_a_un_cliente() -> None:
    categoria = _categoria(aplica_a=AmbitoDeCategoria.SERVICIO)

    with pytest.raises(AmbitoIncompatible, match="cliente"):
        categoria.exigir_admite_cliente()


def test_una_categoria_de_clientes_no_se_asigna_a_un_servicio() -> None:
    categoria = _categoria(aplica_a=AmbitoDeCategoria.CLIENTE)

    with pytest.raises(AmbitoIncompatible, match="servicio"):
        categoria.exigir_admite_servicio()


def test_ambos_se_asigna_a_las_dos_cosas() -> None:
    """Decisión D9 del mapa: el valor que el enum del DER no tenía y la historia pide."""
    categoria = _categoria(aplica_a=AmbitoDeCategoria.AMBOS)

    categoria.exigir_admite_cliente()
    categoria.exigir_admite_servicio()


# --- Nombre y unicidad ----------------------------------------------------------------


def test_el_nombre_vacio_no_construye_una_categoria() -> None:
    with pytest.raises(EntradaInvalida, match="nombre"):
        _categoria(nombre="   ")


def test_el_nombre_se_recorta() -> None:
    assert _categoria(nombre="  Vip  ").nombre == "Vip"


def test_la_clave_de_unicidad_ignora_mayusculas_y_espacios() -> None:
    """RN-02 compara nombres, y «VIP» y «vip» son el mismo nombre para quien mira la lista."""
    assert clave_de_unicidad("VIP") == clave_de_unicidad(" vip ")
    assert clave_de_unicidad("Mayorista") != clave_de_unicidad("Minorista")


# --- Renombrar y cambiar de ámbito ----------------------------------------------------


def test_renombrar_no_toca_a_los_elementos_clasificados() -> None:
    """El tercer criterio de HU-E4-03 sale gratis: el nombre vive en una sola fila.

    Se comprueba sobre la interfaz — el agregado no tiene forma de alcanzar a un cliente
    ni a un servicio — porque eso es exactamente lo que hace que el criterio sea cierto.
    """
    operaciones = {
        n
        for n in dir(CategoriaEmpresa)
        if not n.startswith("_") and callable(getattr(CategoriaEmpresa, n))
    }

    assert "renombrar" in operaciones
    assert not [n for n in operaciones if "cliente" in n and n.startswith(("actualizar", "sync"))]


def test_renombrar_valida_el_nombre_nuevo() -> None:
    categoria = _categoria()

    with pytest.raises(EntradaInvalida):
        categoria.renombrar("  ")

    assert categoria.nombre == "Vip"


def test_achicar_el_ambito_no_desasigna_lo_que_ya_estaba() -> None:
    """Decisión de esta unidad: pasar de `AMBOS` a `CLIENTE` no borra clasificaciones.

    La historia no lo pide, y borrar en silencio las clasificaciones de alguien como
    efecto secundario de una edición es de las sorpresas que se descubren meses después.
    El agregado directamente no puede alcanzarlas, que es la forma de garantizarlo.
    """
    categoria = _categoria(aplica_a=AmbitoDeCategoria.AMBOS)

    categoria.cambiar_ambito(AmbitoDeCategoria.CLIENTE)

    assert categoria.aplica_a is AmbitoDeCategoria.CLIENTE
    assert categoria.admite_servicios is False


# --- Normalización del nombre (HU-E4-05 RN-04) ---------------------------------------


def test_el_nombre_de_la_categoria_se_guarda_normalizado() -> None:
    categoria = _categoria(nombre="  VIP   GOLD ")

    assert categoria.nombre == "Vip gold"

    categoria.renombrar("CLIENTES FRECUENTES")
    assert categoria.nombre == "Clientes frecuentes"


def test_una_categoria_con_nombre_de_invisibles_es_obligatoria() -> None:
    with pytest.raises(EntradaInvalida, match="obligatorio"):
        _categoria(nombre="\ufeff \u200b")


def test_la_clave_de_unicidad_es_el_nombre_normalizado_sin_mayusculas() -> None:
    assert clave_de_unicidad("VIP   GOLD") == clave_de_unicidad("Vip gold") == "vip gold"
