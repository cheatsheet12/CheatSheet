"""The legal-document catalogue: one current version per document (HU-E1-08 RN-01)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.domain.legal import (
    AceptacionLegal,
    CatalogoLegal,
    DocumentoLegal,
    VersionDeDocumento,
    documentos_pendientes,
)
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
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


# ------------------------------------------------------------------------------ case 11


def _aceptacion(**cambios: object) -> AceptacionLegal:
    datos: dict[str, object] = {
        "empresa_id": EmpresaId(uuid4()),
        "usuario_id": UsuarioId(uuid4()),
        "documento": DocumentoLegal.PRIVACIDAD,
        "version": "1.0",
        "fecha_aceptacion": datetime(2026, 10, 10, 15, 0, tzinfo=UTC),
    }
    datos.update(cambios)
    return AceptacionLegal.registrar(**datos)  # type: ignore[arg-type]


def test_una_aceptacion_guarda_documento_version_y_fecha():
    aceptacion = _aceptacion()

    assert aceptacion.documento is DocumentoLegal.PRIVACIDAD
    assert aceptacion.version == "1.0"
    assert aceptacion.fecha_aceptacion == datetime(2026, 10, 10, 15, 0, tzinfo=UTC)
    assert aceptacion.usuario_id is not None


def test_la_aceptacion_es_inmutable():
    with pytest.raises(FrozenInstanceError):
        _aceptacion().version = "2.0"  # type: ignore[misc]


def test_la_fecha_de_aceptacion_lleva_zona_horaria():
    with pytest.raises(EntradaInvalida):
        _aceptacion(fecha_aceptacion=datetime.now(UTC).replace(tzinfo=None))


@pytest.mark.parametrize("version", ["", "1", "v1.0", "1.0.1", "1." + "0" * 30])
def test_la_aceptacion_exige_una_version_con_el_formato_del_catalogo(version: str):
    with pytest.raises(EntradaInvalida):
        _aceptacion(version=version)


def test_la_privacidad_exige_usuario():
    with pytest.raises(EntradaInvalida):
        _aceptacion(usuario_id=None)


def test_los_terminos_pueden_no_tener_usuario():
    """Only the backfill leaves it empty: nobody can say who accepted a text that never existed."""
    aceptacion = _aceptacion(documento=DocumentoLegal.TERMINOS, usuario_id=None)

    assert aceptacion.usuario_id is None


# ------------------------------------------------------------------------------ case 25


def _pendientes(
    rol: RolUsuario, *, terminos_aceptados: str | None, privacidad_aceptada: bool
) -> frozenset[DocumentoLegal]:
    return documentos_pendientes(
        rol=rol,
        version_de_terminos_de_la_empresa=terminos_aceptados,
        acepto_privacidad_vigente=privacidad_aceptada,
        terminos_vigente="1.1",
    )


def test_un_administrador_con_terminos_viejos_debe_los_terminos():
    pendientes = _pendientes(
        RolUsuario.ADMINISTRADOR, terminos_aceptados="1.0", privacidad_aceptada=True
    )

    assert pendientes == {DocumentoLegal.TERMINOS}


@pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA])
def test_los_otros_roles_nunca_se_bloquean_por_los_terminos(rol: RolUsuario):
    """HU-E1-03 RN-03: the company's terms are accepted by an Administrador, nobody else."""
    pendientes = _pendientes(rol, terminos_aceptados="1.0", privacidad_aceptada=True)

    assert pendientes == frozenset()


@pytest.mark.parametrize("rol", list(RolUsuario))
def test_cualquiera_sin_la_privacidad_vigente_la_debe(rol: RolUsuario):
    pendientes = _pendientes(rol, terminos_aceptados="1.1", privacidad_aceptada=False)

    assert pendientes == {DocumentoLegal.PRIVACIDAD}


def test_un_administrador_puede_deber_las_dos():
    pendientes = _pendientes(
        RolUsuario.ADMINISTRADOR, terminos_aceptados="1.0", privacidad_aceptada=False
    )

    assert pendientes == {DocumentoLegal.TERMINOS, DocumentoLegal.PRIVACIDAD}


def test_una_empresa_sin_terminos_registrados_los_debe_su_administrador():
    pendientes = _pendientes(
        RolUsuario.ADMINISTRADOR, terminos_aceptados=None, privacidad_aceptada=True
    )

    assert pendientes == {DocumentoLegal.TERMINOS}


def test_al_dia_no_debe_nada():
    pendientes = _pendientes(
        RolUsuario.ADMINISTRADOR, terminos_aceptados="1.1", privacidad_aceptada=True
    )

    assert pendientes == frozenset()
