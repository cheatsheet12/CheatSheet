"""HS-T5 at the application level: what the use case guarantees."""

from __future__ import annotations

import dataclasses
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.observability.application.registrar_operacion import RegistrarOperacion
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.tenant import TenantId

from tests.conftest import RepositorioDeAuditoriaEnMemoria


@pytest.mark.asyncio
async def test_registra_los_seis_datos_que_exige_rn02(
    repositorio: RepositorioDeAuditoriaEnMemoria, evento_auditable: EventoAuditable
):
    resultado = await RegistrarOperacion(repositorio).ejecutar(evento_auditable)

    registro = repositorio.registros[resultado.registro_id]
    assert registro.modulo is evento_auditable.modulo
    assert registro.operacion == evento_auditable.operacion
    assert registro.entidad_afectada == evento_auditable.entidad_afectada
    assert registro.iniciador == evento_auditable.iniciador
    assert registro.resultado is evento_auditable.resultado
    assert registro.ocurrido_en == evento_auditable.ocurrido_en


@pytest.mark.asyncio
async def test_una_operacion_fallida_se_registra_igual(
    repositorio: RepositorioDeAuditoriaEnMemoria, evento_auditable: EventoAuditable
):
    """RN-04: the outcome is data, never a condition for writing the row."""
    fallido = dataclasses.replace(evento_auditable, resultado=Resultado.ERROR)

    resultado = await RegistrarOperacion(repositorio).ejecutar(fallido)

    assert resultado.fue_creado is True
    assert repositorio.registros[resultado.registro_id].resultado is Resultado.ERROR


@pytest.mark.asyncio
async def test_el_mismo_evento_entregado_dos_veces_deja_una_sola_fila(
    repositorio: RepositorioDeAuditoriaEnMemoria, evento_auditable: EventoAuditable
):
    """At-least-once delivery is the only thing a queue promises (ADR-009)."""
    caso = RegistrarOperacion(repositorio)

    primero = await caso.ejecutar(evento_auditable)
    segundo = await caso.ejecutar(evento_auditable)

    assert primero.fue_creado is True
    assert segundo.fue_creado is False
    assert segundo.registro_id == primero.registro_id
    assert len(repositorio.registros) == 1


@pytest.mark.asyncio
async def test_pierde_la_carrera_contra_una_entrega_concurrente_y_devuelve_la_fila_ganadora(
    repositorio: RepositorioDeAuditoriaEnMemoria, evento_auditable: EventoAuditable
):
    """The read-then-insert window is real; the unique index is what closes it.

    Simulated by making the repository forget the row on lookup but reject it on
    insert — exactly what a concurrent writer looks like from in here.
    """

    class RepositorioEnCarrera(RepositorioDeAuditoriaEnMemoria):
        def __init__(self) -> None:
            super().__init__()
            self.primera_busqueda = True

        async def buscar_por_evento(self, evento_id: UUID) -> RegistroDeAuditoria | None:
            if self.primera_busqueda:
                self.primera_busqueda = False
                return None
            return await super().buscar_por_evento(evento_id)

    concurrente = RepositorioEnCarrera()
    ganador = await RegistrarOperacion(concurrente).ejecutar(evento_auditable)
    concurrente.primera_busqueda = True

    perdedor = await RegistrarOperacion(concurrente).ejecutar(evento_auditable)

    assert perdedor.fue_creado is False
    assert perdedor.registro_id == ganador.registro_id


@pytest.mark.asyncio
async def test_eventos_distintos_producen_registros_distintos(
    repositorio: RepositorioDeAuditoriaEnMemoria, evento_auditable: EventoAuditable
):
    otro = dataclasses.replace(
        evento_auditable,
        evento_id=uuid4(),
        modulo=Modulo.PAYMENTS,
        tenant_id=TenantId(uuid4()),
    )
    caso = RegistrarOperacion(repositorio)

    await caso.ejecutar(evento_auditable)
    await caso.ejecutar(otro)

    assert len(repositorio.registros) == 2
