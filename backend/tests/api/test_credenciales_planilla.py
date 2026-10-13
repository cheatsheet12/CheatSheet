"""Composition of spreadsheet credentials with integrations' public services."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.api.credenciales_planilla import CredencialesDePlanilla
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import Ambiente, SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.cifrado import CifradoAesGcm
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio


class RepositorioFalso:
    def __init__(self) -> None:
        self.rows: dict[EmpresaId, ConfiguracionDeIntegracion] = {}

    async def buscar(
        self, empresa_id: EmpresaId, sistema: SistemaExterno
    ) -> ConfiguracionDeIntegracion | None:
        row = self.rows.get(empresa_id)
        return row if row is not None and row.sistema is sistema else None

    async def agregar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        self.rows[configuracion.empresa_id] = configuracion

    async def guardar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        self.rows[configuracion.empresa_id] = configuracion

    async def listar(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]:
        return [row for row in self.rows.values() if row.empresa_id == empresa_id]

    async def listar_pendientes(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]:
        return await self.listar(empresa_id)


class ProveedorFalso:
    async def renovar(self, credencial: bytes) -> str:
        assert credencial == b"refresh-for-this-company"
        return "fresh-access"


async def test_link_and_worker_use_the_same_company_credential() -> None:
    company = EmpresaId(uuid4())
    repository = RepositorioFalso()
    cipher = CifradoAesGcm(base64.b64encode(b"x" * 32).decode())
    credentials = CredencialesDePlanilla(
        repository, cipher, ProveedorFalso(), Ambiente.HOMOLOGACION
    )
    now = datetime(2026, 10, 12, tzinfo=UTC)

    credential_id = await credentials.guardar(
        empresa_id=company, renovacion="refresh-for-this-company", ahora=now
    )

    assert repository.rows[company].id == credential_id
    assert (
        await credentials.obtener(empresa_id=company, configuracion_id=credential_id, ahora=now)
        == "fresh-access"
    )
