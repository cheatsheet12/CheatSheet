"""One WhatsApp business account, one empresa (G4 of the Gate 2 of `plantillas-de-whatsapp-en-meta`).

What a double cannot prove: that the unique partial index of migration 0037 stops a second
empresa from registering a WABA that is already linked, across tenants and through RLS, and that
the repository turns that into `CuentaDeWhatsAppEnUso`. They need PostgreSQL: skipped without a
database, run in CI.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.integrations.application.errors import CuentaDeWhatsAppEnUso
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    RepositorioIntegracionesSQL,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _whatsapp(empresa_id: EmpresaId, waba_id: str) -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion.registrar(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        sistema=SistemaExterno.WHATSAPP,
        credencial=CredencialCifrada(contenido=b"x", algoritmo="fernet"),
        ambiente=Ambiente.HOMOLOGACION,
        ahora=AHORA,
        estado=EstadoDeConexion.CONECTADO,
        detalle=None,
        parametros={"waba_id": waba_id, "phone_number_id": "1"},
    )


async def test_la_segunda_empresa_no_puede_registrar_la_misma_cuenta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    primera, segunda = await _empresa(engine_dueno), await _empresa(engine_dueno)
    waba = f"waba-{uuid.uuid4()}"
    async with sesion_de_empresa(sesiones, primera) as sesion:
        await RepositorioIntegracionesSQL(sesion).agregar(_whatsapp(primera, waba))

    with pytest.raises(CuentaDeWhatsAppEnUso):
        async with sesion_de_empresa(sesiones, segunda) as sesion:
            await RepositorioIntegracionesSQL(sesion).agregar(_whatsapp(segunda, waba))


async def test_reconectar_con_la_cuenta_de_otra_empresa_tambien_se_rechaza(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    primera, segunda = await _empresa(engine_dueno), await _empresa(engine_dueno)
    waba = f"waba-{uuid.uuid4()}"
    propia = _whatsapp(segunda, f"waba-{uuid.uuid4()}")
    async with sesion_de_empresa(sesiones, primera) as sesion:
        await RepositorioIntegracionesSQL(sesion).agregar(_whatsapp(primera, waba))
    async with sesion_de_empresa(sesiones, segunda) as sesion:
        await RepositorioIntegracionesSQL(sesion).agregar(propia)

    propia.parametros["waba_id"] = waba
    with pytest.raises(CuentaDeWhatsAppEnUso):
        async with sesion_de_empresa(sesiones, segunda) as sesion:
            await RepositorioIntegracionesSQL(sesion).guardar(propia)


async def test_la_misma_empresa_puede_volver_a_guardar_su_cuenta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    configuracion = _whatsapp(empresa_id, f"waba-{uuid.uuid4()}")
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repositorio = RepositorioIntegracionesSQL(sesion)
        await repositorio.agregar(configuracion)
        await repositorio.guardar(configuracion)


async def test_dos_empresas_sin_cuenta_cargada_no_chocan(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """The index is partial: an empty `waba_id` is "not linked yet", not an account."""
    for _ in range(2):
        empresa_id = await _empresa(engine_dueno)
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioIntegracionesSQL(sesion).agregar(_whatsapp(empresa_id, ""))
