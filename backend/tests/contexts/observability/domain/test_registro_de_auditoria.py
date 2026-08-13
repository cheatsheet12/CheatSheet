"""HS-T5 at the domain level: what a record is, and what it refuses to become."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.shared.auditoria import (
    LARGO_MAXIMO_ACCION,
    LARGO_MAXIMO_ENTIDAD,
    Modulo,
    Resultado,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida

from tests.conftest import INSTANTE_FIJO


def _registro(**overrides: object) -> RegistroDeAuditoria:
    base: dict[str, object] = {
        "id": uuid4(),
        "evento_id": uuid4(),
        "empresa_id": EmpresaId(uuid4()),
        "usuario_id": UsuarioId(uuid4()),
        "modulo": Modulo.BILLING,
        "accion": "emitir_comprobante",
        "entidad_afectada": "Comprobante:A-0001-00000042",
        "resultado": Resultado.COMPLETADO,
        "direccion_ip": "190.0.0.1",
        "timestamp": INSTANTE_FIJO,
    }
    base.update(overrides)
    return RegistroDeAuditoria(**base)  # type: ignore[arg-type]  # kwargs built above


def test_un_registro_no_puede_modificarse_tras_crearse():
    """RN-03, level 1: the type system refuses the mutation."""
    registro = _registro()

    with pytest.raises(dataclasses.FrozenInstanceError):
        registro.accion = "otra_cosa"  # type: ignore[misc]  # that is the point


def test_un_registro_con_resultado_error_es_igual_de_valido():
    """RN-04: the log records failures, so `ERROR` is not a rejected input."""
    registro = _registro(resultado=Resultado.ERROR)

    assert registro.resultado is Resultado.ERROR
    assert registro.fue_exitosa is False


def test_sin_usuario_el_registro_es_del_sistema():
    """The DER models a nullable usuario_id, and null means: nobody asked, the system did."""
    registro = _registro(usuario_id=None)

    assert registro.fue_del_sistema is True


def test_con_usuario_el_registro_no_es_del_sistema():
    assert _registro().fue_del_sistema is False


def test_una_accion_vacia_es_rechazada():
    with pytest.raises(EntradaInvalida, match="accion"):
        _registro(accion="   ")


def test_una_accion_demasiado_larga_es_rechazada():
    with pytest.raises(EntradaInvalida, match="excede"):
        _registro(accion="x" * (LARGO_MAXIMO_ACCION + 1))


def test_una_entidad_afectada_vacia_es_rechazada():
    with pytest.raises(EntradaInvalida, match="entidad afectada"):
        _registro(entidad_afectada="  ")


def test_una_entidad_afectada_demasiado_larga_es_rechazada():
    with pytest.raises(EntradaInvalida, match="excede"):
        _registro(entidad_afectada="x" * (LARGO_MAXIMO_ENTIDAD + 1))


def test_un_instante_sin_zona_horaria_es_rechazado():
    """A naive timestamp in an audit log is a timestamp nobody can reconstruct."""
    with pytest.raises(EntradaInvalida, match="zona horaria"):
        _registro(timestamp=datetime(2026, 8, 12, 15, 30))  # noqa: DTZ001 — that is the case


def test_la_accion_se_normaliza_sin_espacios():
    assert _registro(accion="  emitir_comprobante  ").accion == "emitir_comprobante"


def test_la_direccion_ip_es_opcional():
    """Not every operation arrives over HTTP: a Beat task has no IP."""
    assert _registro(direccion_ip=None).direccion_ip is None
