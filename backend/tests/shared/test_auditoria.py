"""The Shared Kernel vocabulary of HS-T5."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida

from tests.conftest import INSTANTE_FIJO


def _evento(**overrides: object) -> EventoAuditable:
    base: dict[str, object] = {
        "evento_id": uuid4(),
        "empresa_id": EmpresaId(uuid4()),
        "ocurrido_en": INSTANTE_FIJO,
        "modulo": Modulo.BILLING,
        "accion": "emitir_comprobante",
        "entidad_afectada": "Comprobante:A-0001-42",
        "resultado": Resultado.COMPLETADO,
    }
    base.update(overrides)
    return EventoAuditable(**base)  # type: ignore[arg-type]  # kwargs built above


def test_el_catalogo_de_modulos_son_los_doce_bounded_contexts():
    """A thirteenth module means a context nobody declared in the architecture."""
    assert len(list(Modulo)) == 12
    assert Modulo.BILLING.value == "billing"


def test_los_modulos_coinciden_con_los_directorios_del_backend():
    """The enum is what the audit panel filters by; a typo here is a filter that misses."""
    esperados = {
        "identity",
        "master_data",
        "business_config",
        "integrations",
        "spreadsheet_sync",
        "billing",
        "payments",
        "scheduling",
        "conversational",
        "observability",
        "reporting",
        "reference_data",
    }

    assert {modulo.value for modulo in Modulo} == esperados


def test_un_evento_sin_usuario_es_del_sistema():
    assert _evento().fue_del_sistema is True


def test_un_evento_con_usuario_no_es_del_sistema():
    assert _evento(usuario_id=UsuarioId(uuid4())).fue_del_sistema is False


def test_un_evento_sin_accion_es_rechazado():
    with pytest.raises(EntradaInvalida, match="accion"):
        _evento(accion="")


def test_un_evento_sin_entidad_afectada_es_rechazado():
    with pytest.raises(EntradaInvalida, match="entidad afectada"):
        _evento(entidad_afectada="")


def test_un_evento_sin_zona_horaria_es_rechazado():
    from datetime import datetime

    with pytest.raises(ValueError, match="zona horaria"):
        _evento(ocurrido_en=datetime(2026, 8, 12))  # noqa: DTZ001 — that is the case


def test_la_direccion_ip_por_defecto_es_ausente():
    """Most events do not come from a request, so the default must not invent one."""
    assert _evento().direccion_ip is None
