"""El agregado `Servicio` — y el primer dinero del sistema.

Este archivo importa más de lo que su tamaño sugiere: `precio` es el primer `Decimal` que
CheatSheet guarda, y lo que se fije acá lo van a copiar `billing`, `payments` y la seña de
turno. Las dos reglas que se prueban con más insistencia son las de
`docs/code-standards.md` §2.5 — redondeo explícito con `ROUND_HALF_UP`, y ningún `float`
cerca del dinero.

Los otros dos invariantes son de HU-E4-02: precio mayor a cero (RN-02) y duración
obligatoria en los agendables (RN-03), con los mensajes textuales de los criterios.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from inspect import signature
from uuid import uuid4

import pytest
from cheatsheet.contexts.master_data.domain.servicio import (
    MENSAJE_DURACION,
    MENSAJE_PRECIO,
    MENSAJE_RANGO_DURACION,
    FiltrosDeServicio,
    Servicio,
    precio_valido,
)
from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

from tests.conftest import INSTANTE_FIJO

EMPRESA = EmpresaId(uuid4())

MUTADORES = (
    "renombrar",
    "cambiar_precio",
    "cambiar_alicuota",
    "volver_agendable",
    "dejar_de_ser_agendable",
    "desactivar",
    "reactivar",
)


def _servicio(
    *,
    nombre: str = "Corte de pelo",
    precio: Decimal = Decimal("5000.00"),
    alicuota_iva: AlicuotaIVA = AlicuotaIVA.GENERAL,
    agendable: bool = False,
    duracion_estandar_min: int | None = None,
) -> Servicio:
    return Servicio.registrar(
        id=uuid4(),
        empresa_id=EMPRESA,
        nombre=nombre,
        precio=precio,
        alicuota_iva=alicuota_iva,
        origen=OrigenDato.PANEL,
        momento=INSTANTE_FIJO,
        agendable=agendable,
        duracion_estandar_min=duracion_estandar_min,
    )


# --- El dinero -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("10.005", "10.01"),  # el medio centavo sube: ROUND_HALF_UP
        ("10.004", "10.00"),
        ("10.015", "10.02"),
        ("0.005", "0.01"),  # justo medio centavo sigue siendo un precio
        ("5000", "5000.00"),
    ],
)
def test_el_precio_se_cuantiza_a_centavos_con_round_half_up(entrada: str, esperado: str) -> None:
    """`ROUND_HALF_UP` y no el `ROUND_HALF_EVEN` que Python usa por defecto.

    Con el modo por defecto `10.005` daría `10.00`, y la diferencia aparece recién cuando
    alguien compara el total del sistema contra el de una calculadora.
    """
    assert precio_valido(Decimal(entrada)) == Decimal(esperado)


@pytest.mark.parametrize("entrada", ["0", "0.00", "-1", "-0.01", "0.004"])
def test_un_precio_que_no_supera_cero_no_construye_un_servicio(entrada: str) -> None:
    """RN-02, con el mensaje del criterio de aceptación.

    `0.004` está en la lista a propósito: cuantiza a `0.00`, y por eso el orden importa —
    se redondea primero y se compara después.
    """
    with pytest.raises(EntradaInvalida, match=MENSAJE_PRECIO):
        _servicio(precio=Decimal(entrada))


@pytest.mark.parametrize("entrada", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_un_precio_que_no_es_un_numero_finito_se_rechaza(entrada: str) -> None:
    """`Decimal` acepta construirlos; el dinero no.

    `NaN` es el que importa y el que casi se escapa: a diferencia de `Infinity`, no hace
    fallar a `quantize` — lo atraviesa en silencio y explota recién al compararlo, con un
    `InvalidOperation` que habría llegado al usuario como un 500.
    """
    with pytest.raises(EntradaInvalida, match=MENSAJE_PRECIO):
        precio_valido(Decimal(entrada))


def test_el_precio_guardado_es_el_cuantizado_y_no_el_recibido() -> None:
    servicio = _servicio(precio=Decimal("1234.567"))

    assert servicio.precio == Decimal("1234.57")
    assert str(servicio.precio) == "1234.57"


def test_cambiar_precio_vuelve_a_validar() -> None:
    servicio = _servicio()

    with pytest.raises(EntradaInvalida, match=MENSAJE_PRECIO):
        servicio.cambiar_precio(Decimal("0"), INSTANTE_FIJO)

    assert servicio.precio == Decimal("5000.00")


def test_el_agregado_no_calcula_el_precio_con_iva() -> None:
    """A propósito: multiplicar es del épico 5, y una vez por comprobante, no por ítem.

    Si alguien agrega acá un `precio_con_iva`, este test es lo que se lo dice — dos
    lugares redondeando el mismo dinero es exactamente el defecto que se está evitando.
    """
    operaciones = {
        n for n in dir(Servicio) if not n.startswith("_") and callable(getattr(Servicio, n))
    }

    assert not [n for n in operaciones if "total" in n or "con_iva" in n or "importe" in n]


# --- Las alícuotas -------------------------------------------------------------------


def test_las_tres_alicuotas_son_las_de_la_regla() -> None:
    """RN-02: enum cerrado de tres valores."""
    assert [a.tasa for a in AlicuotaIVA] == [Decimal("0.00"), Decimal("0.105"), Decimal("0.21")]


def test_la_alicuota_se_reconstruye_desde_la_columna() -> None:
    """`NUMERIC(5, 4)` devuelve `0.1050`, que como texto no es `0.105` pero como número sí."""
    assert AlicuotaIVA.desde_tasa(Decimal("0.1050")) is AlicuotaIVA.REDUCIDA
    assert AlicuotaIVA.desde_tasa(Decimal("0.2100")) is AlicuotaIVA.GENERAL
    assert AlicuotaIVA.desde_tasa(Decimal("0.0000")) is AlicuotaIVA.CERO


def test_una_alicuota_que_no_existe_no_se_reconstruye() -> None:
    with pytest.raises(EntradaInvalida, match="alicuota"):
        AlicuotaIVA.desde_tasa(Decimal("0.27"))


def test_la_tasa_se_construye_desde_texto_y_no_desde_un_float() -> None:
    """La regla de `code-standards` §2.5, comprobada donde se podría haber roto.

    Escribir `Decimal(0.21)` acá para ilustrar la diferencia **no se puede**, y eso es una
    buena noticia: ruff lo bloquea con `RUF032`, que es el guardrail del proyecto haciendo
    su trabajo. `Decimal.from_float` es la misma conversión dicha en voz alta, y sirve para
    mostrar lo que se está evitando.

    Los dígitos exactos del float no se escriben acá a propósito: son una propiedad de
    IEEE-754, no de este sistema, y afirmarlos de memoria es como se escribe un test que
    parece riguroso y está mal. Lo que importa es que **no son los mismos dígitos** y que
    son muchos más.
    """
    desde_float = Decimal.from_float(0.21)

    assert AlicuotaIVA.GENERAL.tasa == Decimal("0.21")
    assert AlicuotaIVA.GENERAL.tasa != desde_float
    assert len(str(desde_float)) > len("0.21")


# --- Agendable y duración ------------------------------------------------------------


def test_un_servicio_agendable_sin_duracion_no_se_guarda() -> None:
    """RN-03, con el mensaje del criterio de aceptación."""
    with pytest.raises(EntradaInvalida, match=MENSAJE_DURACION):
        _servicio(agendable=True)


@pytest.mark.parametrize("duracion", [4, 481, 99999])
def test_una_duracion_fuera_del_rango_no_se_guarda(duracion: int) -> None:
    """HU-E4-02: entre 5 y 480 minutos."""
    with pytest.raises(EntradaInvalida, match=MENSAJE_RANGO_DURACION):
        _servicio(agendable=True, duracion_estandar_min=duracion)


@pytest.mark.parametrize("duracion", [0, -30])
def test_cero_y_negativos_dan_el_mensaje_de_rango_y_no_el_de_obligatoria(duracion: int) -> None:
    """El usuario escribio algo: decirle que falta seria enganoso."""
    with pytest.raises(EntradaInvalida) as error:
        _servicio(agendable=True, duracion_estandar_min=duracion)

    assert str(error.value) == MENSAJE_RANGO_DURACION


def test_un_booleano_no_es_una_duracion() -> None:
    """`True` es un `int` en Python: sin defensa pasaria como 1 (y `False` como 0)."""
    with pytest.raises(EntradaInvalida, match=MENSAJE_RANGO_DURACION):
        _servicio(agendable=True, duracion_estandar_min=True)


@pytest.mark.parametrize("duracion", [5, 480])
def test_los_limites_del_rango_se_aceptan(duracion: int) -> None:
    assert _servicio(agendable=True, duracion_estandar_min=duracion).duracion_estandar_min == (
        duracion
    )


def test_un_servicio_no_agendable_puede_no_tener_duracion() -> None:
    servicio = _servicio()

    assert servicio.agendable is False
    assert servicio.duracion_estandar_min is None


def test_un_servicio_no_agendable_no_conserva_una_duracion_que_le_manden() -> None:
    """El espejo de RN-03: los dos campos no pueden contradecirse."""
    servicio = _servicio(agendable=False, duracion_estandar_min=45)

    assert servicio.duracion_estandar_min is None


def test_dejar_de_ser_agendable_borra_la_duracion() -> None:
    servicio = _servicio(agendable=True, duracion_estandar_min=45)

    servicio.dejar_de_ser_agendable(INSTANTE_FIJO)

    assert servicio.agendable is False
    assert servicio.duracion_estandar_min is None


def test_volver_agendable_exige_la_duracion() -> None:
    servicio = _servicio()

    with pytest.raises(EntradaInvalida, match=MENSAJE_RANGO_DURACION):
        servicio.volver_agendable(0, INSTANTE_FIJO)

    servicio.volver_agendable(30, INSTANTE_FIJO)
    assert servicio.duracion_estandar_min == 30


def test_volver_agendable_fuera_del_rango_rechaza_sin_dejar_el_servicio_a_medias() -> None:
    servicio = _servicio()

    with pytest.raises(EntradaInvalida, match=MENSAJE_RANGO_DURACION):
        servicio.volver_agendable(600, INSTANTE_FIJO)

    assert servicio.agendable is False
    assert servicio.duracion_estandar_min is None


# --- Lo que comparte con `Cliente` ----------------------------------------------------


def test_el_agregado_no_expone_forma_de_cambiar_el_origen() -> None:
    operaciones = {
        n for n in dir(Servicio) if not n.startswith("_") and callable(getattr(Servicio, n))
    }

    assert not [n for n in operaciones if "origen" in n]
    for nombre in MUTADORES:
        assert "origen" not in signature(getattr(Servicio, nombre)).parameters, nombre


def test_no_hay_forma_de_borrar_un_servicio() -> None:
    """RN-04: desactivar oculta del catálogo activo y no toca nada histórico."""
    operaciones = {
        n for n in dir(Servicio) if not n.startswith("_") and callable(getattr(Servicio, n))
    }

    assert "desactivar" in operaciones
    assert not [n for n in operaciones if "eliminar" in n or "borrar" in n]


def test_desactivar_y_reactivar_mueven_la_marca_de_tiempo() -> None:
    servicio = _servicio()
    despues = INSTANTE_FIJO + timedelta(hours=1)

    servicio.desactivar(despues)
    assert servicio.activo is False
    assert servicio.actualizado_en == despues

    servicio.reactivar(despues + timedelta(hours=1))
    assert servicio.activo is True


def test_el_nombre_vacio_no_construye_un_servicio() -> None:
    with pytest.raises(EntradaInvalida, match="nombre"):
        _servicio(nombre="   ")


def test_los_filtros_normalizan_el_texto_vacio() -> None:
    assert FiltrosDeServicio(texto="   ").texto is None
    assert FiltrosDeServicio(texto=" corte ").texto == "corte"
