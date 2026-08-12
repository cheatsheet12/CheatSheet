"""The isolation guarantee, tested against the engine that enforces it.

This is the most important test file in the unit. `registro_de_auditoria` is the first
table of the system; the twenty-six aggregates that follow will carry the same
`tenant_id` and the same policy. If the mechanism is wrong here, it is wrong
everywhere, and the way it would surface is one company reading another company's
invoices.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.observability.application.registrar_operacion import RegistrarOperacion
from cheatsheet.contexts.observability.infrastructure.repository import (
    RepositorioDeAuditoriaPostgres,
)
from cheatsheet.platform.database import sesion_del_tenant
from cheatsheet.shared.auditoria import (
    EntidadAfectada,
    EventoAuditable,
    Iniciador,
    Modulo,
    Resultado,
)
from cheatsheet.shared.tenant import TenantId
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]


def _evento(tenant_id: TenantId, operacion: str = "operacion_de_prueba") -> EventoAuditable:
    return EventoAuditable(
        evento_id=uuid.uuid4(),
        tenant_id=tenant_id,
        ocurrido_en=datetime.now(UTC),
        modulo=Modulo.IDENTITY,
        operacion=operacion,
        entidad_afectada=EntidadAfectada(tipo="Usuario", identificador=str(uuid.uuid4())),
        iniciador=Iniciador.sistema("test"),
        resultado=Resultado.COMPLETADO,
    )


async def _registrar(
    sesiones: async_sessionmaker[AsyncSession], tenant_id: TenantId, operacion: str
) -> None:
    async with sesion_del_tenant(sesiones, tenant_id) as sesion:
        await RegistrarOperacion(RepositorioDeAuditoriaPostgres(sesion)).ejecutar(
            _evento(tenant_id, operacion)
        )


@pytest.mark.asyncio
async def test_un_tenant_no_ve_las_filas_de_otro(sesiones: async_sessionmaker[AsyncSession]):
    empresa_a, empresa_b = TenantId(uuid.uuid4()), TenantId(uuid.uuid4())
    await _registrar(sesiones, empresa_a, "alta_en_empresa_a")
    await _registrar(sesiones, empresa_b, "alta_en_empresa_b")

    async with sesion_del_tenant(sesiones, empresa_a) as sesion:
        filas = (await sesion.execute(text("SELECT operacion FROM registro_de_auditoria"))).all()

    assert [fila[0] for fila in filas] == ["alta_en_empresa_a"]


@pytest.mark.asyncio
async def test_sin_tenant_declarado_no_se_ve_nada(
    sesiones: async_sessionmaker[AsyncSession], engine_aplicacion: AsyncEngine
):
    """The failure is closed: forgetting to set the tenant hides rows, never exposes."""
    await _registrar(sesiones, TenantId(uuid.uuid4()), "invisible")

    async with engine_aplicacion.connect() as conexion:
        filas = (await conexion.execute(text("SELECT * FROM registro_de_auditoria"))).all()

    assert filas == []


@pytest.mark.asyncio
async def test_no_se_puede_insertar_una_fila_de_otro_tenant(
    sesiones: async_sessionmaker[AsyncSession],
):
    """WITH CHECK: announcing one company and writing another's row is refused."""
    empresa_a, empresa_b = TenantId(uuid.uuid4()), TenantId(uuid.uuid4())

    with pytest.raises(ProgrammingError):
        async with sesion_del_tenant(sesiones, empresa_a) as sesion:
            await RegistrarOperacion(RepositorioDeAuditoriaPostgres(sesion)).ejecutar(
                _evento(empresa_b, "intento_cruzado")
            )


@pytest.mark.asyncio
async def test_el_tenant_no_sobrevive_a_la_transaccion(
    sesiones: async_sessionmaker[AsyncSession],
):
    """`SET LOCAL` semantics: a pooled connection must not carry the previous tenant.

    Without this, request N+1 for company B could inherit company A's setting from a
    recycled connection — the classic multi-tenant leak.
    """
    empresa_a = TenantId(uuid.uuid4())
    await _registrar(sesiones, empresa_a, "de_la_empresa_a")

    async with sesiones() as sesion:
        actual = await sesion.execute(text("SELECT current_setting('app.current_tenant', true)"))
        assert actual.scalar() in (None, "")
