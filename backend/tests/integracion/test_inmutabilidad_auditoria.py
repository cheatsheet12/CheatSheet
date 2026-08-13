"""HS-T5 RN-03 at the level that survives everything else: the database.

The aggregate refuses mutation and the port offers no `actualizar`. Both are Python,
and Python is what someone bypasses at three in the morning with a `psql` session
during an incident. These tests check the layer that is still there afterwards.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.observability.application.registrar_operacion import RegistrarOperacion
from cheatsheet.contexts.observability.infrastructure.repository import (
    RepositorioDeAuditoriaPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]


def _evento(empresa_id: EmpresaId, evento_id: uuid.UUID | None = None) -> EventoAuditable:
    return EventoAuditable(
        evento_id=evento_id or uuid.uuid4(),
        empresa_id=empresa_id,
        ocurrido_en=datetime.now(UTC),
        modulo=Modulo.BILLING,
        accion="emitir_comprobante",
        entidad_afectada="Comprobante:A-0001-42",
        resultado=Resultado.COMPLETADO,
    )


@pytest.mark.asyncio
async def test_la_aplicacion_no_puede_actualizar_un_registro(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
):
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RegistrarOperacion(RepositorioDeAuditoriaPostgres(sesion)).ejecutar(
            _evento(empresa_id)
        )

    with pytest.raises(ProgrammingError, match=r"permission denied|permiso denegado"):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(text("UPDATE registro_de_auditoria SET accion = 'alterada'"))


@pytest.mark.asyncio
async def test_la_aplicacion_no_puede_borrar_un_registro(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
):
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RegistrarOperacion(RepositorioDeAuditoriaPostgres(sesion)).ejecutar(
            _evento(empresa_id)
        )

    with pytest.raises(ProgrammingError, match=r"permission denied|permiso denegado"):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(text("DELETE FROM registro_de_auditoria"))


@pytest.mark.asyncio
async def test_el_mismo_evento_en_dos_transacciones_deja_una_sola_fila(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
):
    """The unique index is the real idempotency guarantee (ADR-009)."""
    evento_id = uuid.uuid4()

    for _ in range(2):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RegistrarOperacion(RepositorioDeAuditoriaPostgres(sesion)).ejecutar(
                _evento(empresa_id, evento_id)
            )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        total = await sesion.execute(text("SELECT count(*) FROM registro_de_auditoria"))
        assert total.scalar() == 1


@pytest.mark.asyncio
async def test_un_registro_persistido_se_relee_identico(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
):
    """The hand-written mapping in both directions is a place bugs hide."""
    evento = _evento(empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        resultado = await RegistrarOperacion(RepositorioDeAuditoriaPostgres(sesion)).ejecutar(
            evento
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        recuperado = await RepositorioDeAuditoriaPostgres(sesion).buscar_por_id(
            resultado.registro_id
        )

    assert recuperado is not None
    assert recuperado.evento_id == evento.evento_id
    assert recuperado.modulo is evento.modulo
    assert recuperado.entidad_afectada == evento.entidad_afectada
    assert recuperado.accion == evento.accion
    assert recuperado.usuario_id == evento.usuario_id
    assert recuperado.direccion_ip == evento.direccion_ip
    assert recuperado.resultado is evento.resultado
    assert recuperado.timestamp == evento.ocurrido_en
