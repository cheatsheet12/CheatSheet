"""The Shared Kernel vocabulary of HS-T5."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.shared.auditoria import (
    EntidadAfectada,
    EventoAuditable,
    Iniciador,
    Modulo,
    Resultado,
    TipoDeIniciador,
)
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.tenant import TenantId, UserId

from tests.conftest import INSTANTE_FIJO


def test_el_catalogo_de_modulos_son_los_doce_bounded_contexts():
    """A thirteenth module means a context nobody declared in the architecture."""
    assert len(list(Modulo)) == 12
    assert Modulo.BILLING.value == "billing"


def test_un_iniciador_usuario_exige_user_id():
    with pytest.raises(EntradaInvalida, match="user_id"):
        Iniciador(tipo=TipoDeIniciador.USUARIO)


def test_un_iniciador_sistema_exige_referencia():
    with pytest.raises(EntradaInvalida, match="referencia"):
        Iniciador(tipo=TipoDeIniciador.SISTEMA)


def test_las_fabricas_construyen_los_tres_tipos_de_iniciador():
    usuario = Iniciador.usuario(UserId(uuid4()))
    sistema = Iniciador.sistema("despachar_recordatorios")
    agente = Iniciador.agente("conv-42")

    assert usuario.tipo is TipoDeIniciador.USUARIO
    assert sistema.referencia == "despachar_recordatorios"
    assert agente.tipo is TipoDeIniciador.AGENTE


def test_una_entidad_afectada_sin_identificador_es_rechazada():
    with pytest.raises(EntradaInvalida):
        EntidadAfectada(tipo="Comprobante", identificador="  ")


def test_un_evento_auditable_congela_su_detalle():
    detalle = {"cae": "75123456789012"}
    evento = EventoAuditable(
        evento_id=uuid4(),
        tenant_id=TenantId(uuid4()),
        ocurrido_en=INSTANTE_FIJO,
        modulo=Modulo.BILLING,
        operacion="emitir_comprobante",
        entidad_afectada=EntidadAfectada(tipo="Comprobante", identificador="A-0001-42"),
        iniciador=Iniciador.sistema("worker"),
        resultado=Resultado.COMPLETADO,
        detalle=detalle,
    )

    detalle["cae"] = "otro"

    assert evento.detalle["cae"] == "75123456789012"
