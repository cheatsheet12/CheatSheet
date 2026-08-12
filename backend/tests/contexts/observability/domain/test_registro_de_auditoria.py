"""HS-T5 at the domain level: what a record is, and what it refuses to become."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.observability.domain.registro_de_auditoria import (
    LARGO_MAXIMO_OPERACION,
    RegistroDeAuditoria,
)
from cheatsheet.shared.auditoria import EntidadAfectada, Iniciador, Modulo, Resultado
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.tenant import TenantId, UserId

from tests.conftest import INSTANTE_FIJO


def _registro(**overrides: object) -> RegistroDeAuditoria:
    base: dict[str, object] = {
        "id": uuid4(),
        "evento_id": uuid4(),
        "tenant_id": TenantId(uuid4()),
        "modulo": Modulo.BILLING,
        "operacion": "emitir_comprobante",
        "entidad_afectada": EntidadAfectada(tipo="Comprobante", identificador="A-0001-00000042"),
        "iniciador": Iniciador.usuario(UserId(uuid4())),
        "resultado": Resultado.COMPLETADO,
        "ocurrido_en": INSTANTE_FIJO,
    }
    base.update(overrides)
    return RegistroDeAuditoria(**base)  # type: ignore[arg-type]  # kwargs built above


def test_un_registro_no_puede_modificarse_tras_crearse():
    """RN-03, level 1: the type system refuses the mutation."""
    registro = _registro()

    with pytest.raises(dataclasses.FrozenInstanceError):
        registro.operacion = "otra_cosa"  # type: ignore[misc]  # that is the point


def test_el_detalle_no_puede_modificarse_a_traves_del_diccionario_original():
    """A frozen dataclass still shares the dict it was handed. This closes that hole."""
    detalle = {"punto_de_venta": "0001"}
    registro = _registro(detalle=detalle)

    detalle["punto_de_venta"] = "9999"

    assert registro.detalle["punto_de_venta"] == "0001"
    with pytest.raises(TypeError):
        registro.detalle["otro"] = "x"  # type: ignore[index]  # read-only mapping


def test_un_registro_con_resultado_error_es_igual_de_valido():
    """RN-04: the log records failures, so `ERROR` is not a rejected input."""
    registro = _registro(resultado=Resultado.ERROR)

    assert registro.resultado is Resultado.ERROR
    assert registro.fue_exitosa is False


def test_una_operacion_vacia_es_rechazada():
    with pytest.raises(EntradaInvalida, match="operacion"):
        _registro(operacion="   ")


def test_una_operacion_demasiado_larga_es_rechazada():
    with pytest.raises(EntradaInvalida, match="excede"):
        _registro(operacion="x" * (LARGO_MAXIMO_OPERACION + 1))


def test_un_instante_sin_zona_horaria_es_rechazado():
    """A naive timestamp in an audit log is a timestamp nobody can reconstruct."""
    with pytest.raises(EntradaInvalida, match="zona horaria"):
        _registro(ocurrido_en=datetime(2026, 8, 12, 15, 30))  # noqa: DTZ001 — that is the case


def test_la_operacion_se_normaliza_sin_espacios():
    assert _registro(operacion="  emitir_comprobante  ").operacion == "emitir_comprobante"
