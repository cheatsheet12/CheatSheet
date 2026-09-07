"""La máquina de reglas de `Mapeo` (HU-E3-01, HU-E3-02).

Dos cosas se prueban acá y no más arriba: que **una columna con confianza baja queda sin
asignar** (RN-03) y que **un mapeo con obligatorias faltantes no se confirma** (RN-02).
La segunda es la que importa: confirmar es lo que habilita procesar cuarenta mil filas, y
un mapeo sin `nombre` produce cuarenta mil clientes sin nombre.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import huella_de
from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import (
    UMBRAL_CONFIANZA_ALTA,
    UMBRAL_CONFIANZA_MEDIA,
    EntradaDeMapeo,
    EstadoMapeo,
    Mapeo,
    NivelDeConfianza,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
OBLIGATORIOS = frozenset({"nombre"})


def _entrada(columna: str, atributo: str | None, score: str) -> EntradaDeMapeo:
    return EntradaDeMapeo(
        id=uuid4(), columna_origen=columna, atributo_destino=atributo, score=Decimal(score)
    )


def _mapeo(*entradas: EntradaDeMapeo) -> Mapeo:
    return Mapeo(
        id=uuid4(),
        empresa_id=EMPRESA,
        huella_encabezado="abc123",
        entradas=list(entradas),
        created_at=AHORA,
        updated_at=AHORA,
    )


@pytest.mark.parametrize(
    ("score", "esperado"),
    [
        ("1.00", NivelDeConfianza.ALTA),
        ("0.95", NivelDeConfianza.ALTA),
        (str(UMBRAL_CONFIANZA_ALTA), NivelDeConfianza.ALTA),
        ("0.80", NivelDeConfianza.MEDIA),
        (str(UMBRAL_CONFIANZA_MEDIA), NivelDeConfianza.MEDIA),
        ("0.74", NivelDeConfianza.BAJA),
        ("0.00", NivelDeConfianza.BAJA),
    ],
)
def test_los_tres_niveles_de_confianza_de_rn01(score: str, esperado: NivelDeConfianza) -> None:
    """Los umbrales se comparan por igualdad, y por eso el score es `Decimal`.

    Con `float`, `Decimal("0.75") == 0.75` es una pregunta cuya respuesta depende del
    binario, y el borde exacto entre «Media» y «Baja» es justo donde una columna deja de
    asignarse sola.
    """
    assert _entrada("Nombre", "nombre", score).confianza is esperado


def test_una_columna_corregida_a_mano_pasa_a_confianza_alta() -> None:
    """Seguir mostrando «revisar» al lado de lo que el usuario acaba de decidir es ruido."""
    entrada = _entrada("Razon Soc.", None, "0.20")
    entrada.asignar("nombre")

    assert entrada.confianza is NivelDeConfianza.ALTA
    assert entrada.corregida_a_mano


def test_un_mapeo_con_obligatorias_sin_asignar_no_se_confirma() -> None:
    """Caso central de RN-02, y el mensaje es el de la historia."""
    mapeo = _mapeo(_entrada("Columna rara", None, "0.10"))

    assert mapeo.faltantes(OBLIGATORIOS) == ("nombre",)

    with pytest.raises(InvarianteViolada) as exc:
        mapeo.confirmar(obligatorios=OBLIGATORIOS, ahora=AHORA)

    assert "Debe asignar todas las columnas obligatorias antes de continuar" in str(exc.value)
    assert mapeo.estado is EstadoMapeo.BORRADOR


def test_un_mapeo_completo_se_confirma() -> None:
    mapeo = _mapeo(_entrada("Cliente", "nombre", "0.97"))

    mapeo.confirmar(obligatorios=OBLIGATORIOS, ahora=AHORA)

    assert mapeo.esta_confirmado
    assert mapeo.faltantes(OBLIGATORIOS) == ()


def test_un_mapeo_confirmado_no_se_corrige_en_el_lugar() -> None:
    """Re-mapear una planilla que ya alimenta el catálogo es otra operación.

    Va por `nueva_version`, que deja las dos: la que interpretó lo ya ingerido y la que
    va a interpretar lo que viene.
    """
    mapeo = _mapeo(_entrada("Cliente", "nombre", "0.97"))
    mapeo.confirmar(obligatorios=OBLIGATORIOS, ahora=AHORA)

    with pytest.raises(InvarianteViolada):
        mapeo.corregir(columna="Cliente", atributo="cuit", ahora=AHORA)


def test_una_version_nueva_vuelve_a_borrador_y_conserva_las_entradas() -> None:
    """RN-03 de HU-E3-04: la estructura cambió, hay que revisar — no empezar de cero.

    Hacer que el usuario rehaga cuarenta asignaciones porque le renombraron una columna
    es cómo una pausa se convierte en un abandono.
    """
    mapeo = _mapeo(_entrada("Cliente", "nombre", "0.97"), _entrada("CUIT", "cuit", "0.99"))
    mapeo.confirmar(obligatorios=OBLIGATORIOS, ahora=AHORA)

    mapeo.nueva_version(ahora=AHORA)

    assert mapeo.estado is EstadoMapeo.BORRADOR
    assert mapeo.version == 2
    assert len(mapeo.entradas) == 2
    assert mapeo.entradas[0].atributo_destino == "nombre"


def test_desasignar_una_columna_la_deja_sin_asignar() -> None:
    """RN-03: el usuario puede vaciar una asignación a propósito."""
    mapeo = _mapeo(_entrada("Cliente", "nombre", "0.97"))

    mapeo.corregir(columna="Cliente", atributo=None, ahora=AHORA)

    assert mapeo.faltantes(OBLIGATORIOS) == ("nombre",)
    assert not mapeo.entradas[0].esta_asignada


def test_corregir_una_columna_que_no_existe_falla() -> None:
    mapeo = _mapeo(_entrada("Cliente", "nombre", "0.97"))

    with pytest.raises(EntradaInvalida):
        mapeo.corregir(columna="No existe", atributo="cuit", ahora=AHORA)


@pytest.mark.parametrize("score", ["-0.1", "1.5"])
def test_un_score_fuera_de_rango_es_rechazado(score: str) -> None:
    with pytest.raises(EntradaInvalida):
        _entrada("Cliente", "nombre", score)


def test_un_mapeo_sin_huella_es_rechazado() -> None:
    with pytest.raises(EntradaInvalida):
        Mapeo(
            id=uuid4(),
            empresa_id=EMPRESA,
            huella_encabezado="  ",
            created_at=AHORA,
            updated_at=AHORA,
        )


def test_la_huella_cambia_con_la_estructura_y_no_con_el_formato() -> None:
    """RN-02. Mayúsculas y espacios no son un cambio de estructura; el orden sí.

    Vive acá y no junto a los casos de uso porque es una función pura: normalizar de más
    haría que ordenar las columnas pase inadvertido, y los datos caerían en otros campos.
    """
    base = huella_de(("Nombre", "CUIT"))

    assert huella_de(("nombre ", " CUIT")) == base
    assert huella_de(("CUIT", "Nombre")) != base
    assert huella_de(("Nombre", "CUIT", "Mail")) != base
