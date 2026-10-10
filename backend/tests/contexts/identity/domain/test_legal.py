"""The legal-document catalogue: one current version per document (HU-E1-08 RN-01)."""

from __future__ import annotations

from datetime import date

import pytest
from cheatsheet.contexts.identity.domain.legal import (
    CatalogoLegal,
    DocumentoLegal,
    VersionDeDocumento,
)
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


def _version(
    version: str,
    desde: date,
    documento: DocumentoLegal = DocumentoLegal.PRIVACIDAD,
    *,
    borrador: bool = False,
) -> VersionDeDocumento:
    return VersionDeDocumento(
        documento=documento, version=version, vigente_desde=desde, borrador=borrador
    )


# ------------------------------------------------------------------------------- case 1


def test_la_vigente_es_la_de_mayor_fecha_que_ya_llego():
    catalogo = CatalogoLegal([_version("1.0", date(2026, 1, 1)), _version("1.1", date(2026, 6, 1))])

    assert catalogo.vigente(DocumentoLegal.PRIVACIDAD, date(2026, 7, 1)).version == "1.1"
    assert catalogo.vigente(DocumentoLegal.PRIVACIDAD, date(2026, 3, 1)).version == "1.0"


def test_una_version_futura_no_es_vigente():
    catalogo = CatalogoLegal([_version("1.0", date(2026, 1, 1)), _version("2.0", date(2027, 1, 1))])

    assert catalogo.vigente(DocumentoLegal.PRIVACIDAD, date(2026, 12, 31)).version == "1.0"


def test_el_dia_de_vigencia_ya_cuenta():
    catalogo = CatalogoLegal([_version("1.0", date(2026, 1, 1))])

    assert catalogo.vigente(DocumentoLegal.PRIVACIDAD, date(2026, 1, 1)).version == "1.0"


def test_cada_documento_tiene_su_propia_vigente():
    catalogo = CatalogoLegal(
        [
            _version("1.0", date(2026, 1, 1), DocumentoLegal.PRIVACIDAD),
            _version("1.1", date(2026, 1, 1), DocumentoLegal.TERMINOS),
        ]
    )

    assert catalogo.vigente(DocumentoLegal.TERMINOS, date(2026, 2, 1)).version == "1.1"
    assert catalogo.vigente(DocumentoLegal.PRIVACIDAD, date(2026, 2, 1)).version == "1.0"


def test_sin_ninguna_vigente_es_una_invariante_violada():
    catalogo = CatalogoLegal([_version("1.0", date(2027, 1, 1))])

    with pytest.raises(InvarianteViolada):
        catalogo.vigente(DocumentoLegal.PRIVACIDAD, date(2026, 1, 1))
    with pytest.raises(InvarianteViolada):
        catalogo.vigente(DocumentoLegal.TERMINOS, date(2030, 1, 1))


def test_las_versiones_anteriores_se_conservan():
    catalogo = CatalogoLegal([_version("1.1", date(2026, 6, 1)), _version("1.0", date(2026, 1, 1))])

    assert [v.version for v in catalogo.versiones(DocumentoLegal.PRIVACIDAD)] == ["1.0", "1.1"]


# ------------------------------------------------------------------------------- case 2


def test_rechaza_dos_versiones_con_el_mismo_identificador():
    with pytest.raises(InvarianteViolada):
        CatalogoLegal([_version("1.0", date(2026, 1, 1)), _version("1.0", date(2026, 2, 1))])


def test_rechaza_dos_versiones_con_la_misma_fecha():
    with pytest.raises(InvarianteViolada):
        CatalogoLegal([_version("1.0", date(2026, 1, 1)), _version("1.1", date(2026, 1, 1))])


def test_el_mismo_identificador_en_documentos_distintos_es_valido():
    CatalogoLegal(
        [
            _version("1.0", date(2026, 1, 1), DocumentoLegal.PRIVACIDAD),
            _version("1.0", date(2026, 1, 1), DocumentoLegal.TERMINOS),
        ]
    )


# ---------------------------------------------------------------- value object well-formed


@pytest.mark.parametrize("version", ["", "1", "1.0.0", "v1.0", "1.a", "12345678901234567890.1"])
def test_el_identificador_de_version_tiene_formato_n_punto_n(version: str):
    with pytest.raises(EntradaInvalida):
        _version(version, date(2026, 1, 1))


def test_el_identificador_acepta_el_formato_n_punto_n():
    assert _version("12.34", date(2026, 1, 1)).version == "12.34"
