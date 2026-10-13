"""Encrypted per-company OAuth credentials for unattended integrations."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.credenciales_oauth import (
    CredencialOAuthRevocada,
    ObtenerAccesoOAuth,
    RegistrarCredencialOAuth,
)
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.cifrado import CifradoAesGcm
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 12, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


class RepositorioFalso:
    def __init__(self) -> None:
        self.filas: dict[EmpresaId, ConfiguracionDeIntegracion] = {}

    async def buscar(
        self, empresa_id: EmpresaId, sistema: SistemaExterno
    ) -> ConfiguracionDeIntegracion | None:
        fila = self.filas.get(empresa_id)
        return fila if fila is not None and fila.sistema is sistema else None

    async def agregar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        self.filas[configuracion.empresa_id] = configuracion

    async def guardar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        self.filas[configuracion.empresa_id] = configuracion

    async def listar(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]:
        return [self.filas[empresa_id]] if empresa_id in self.filas else []

    async def listar_pendientes(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]:
        return await self.listar(empresa_id)


class RefrescadorFalso:
    async def renovar(self, credencial: bytes) -> str:
        assert credencial == b"refresh-company-one"
        return "new-access-token"


async def test_refresh_token_is_encrypted_and_yields_access_only_for_its_company() -> None:
    repository = RepositorioFalso()
    cipher = CifradoAesGcm(base64.b64encode(b"x" * 32).decode())
    credential_id = await RegistrarCredencialOAuth(repository, cipher).ejecutar(
        empresa_id=EMPRESA,
        sistema=SistemaExterno.GOOGLE_SHEETS,
        renovacion="refresh-company-one",
        ambiente=Ambiente.HOMOLOGACION,
        ahora=AHORA,
    )

    stored = repository.filas[EMPRESA]
    assert credential_id == stored.id
    assert b"refresh-company-one" not in stored.credencial.contenido
    access = await ObtenerAccesoOAuth(repository, cipher, RefrescadorFalso()).ejecutar(
        empresa_id=EMPRESA,
        sistema=SistemaExterno.GOOGLE_SHEETS,
        configuracion_id=credential_id,
        ahora=AHORA,
    )
    assert access == "new-access-token"

    other_company = EmpresaId(uuid4())
    with pytest.raises(ValueError, match="credencial"):
        await ObtenerAccesoOAuth(repository, cipher, RefrescadorFalso()).ejecutar(
            empresa_id=other_company,
            sistema=SistemaExterno.GOOGLE_SHEETS,
            configuracion_id=credential_id,
            ahora=AHORA,
        )


async def test_revoked_credential_is_marked_disconnected() -> None:
    repository = RepositorioFalso()
    cipher = CifradoAesGcm(base64.b64encode(b"x" * 32).decode())
    credential_id = await RegistrarCredencialOAuth(repository, cipher).ejecutar(
        empresa_id=EMPRESA,
        sistema=SistemaExterno.GOOGLE_SHEETS,
        renovacion="revoked-token",
        ambiente=Ambiente.HOMOLOGACION,
        ahora=AHORA,
    )

    class Revocado:
        async def renovar(self, credencial: bytes) -> str:
            assert credencial == b"revoked-token"
            raise CredencialOAuthRevocada()

    with pytest.raises(CredencialOAuthRevocada):
        await ObtenerAccesoOAuth(repository, cipher, Revocado()).ejecutar(
            empresa_id=EMPRESA,
            sistema=SistemaExterno.GOOGLE_SHEETS,
            configuracion_id=credential_id,
            ahora=AHORA,
        )
    assert repository.filas[EMPRESA].estado is EstadoDeConexion.NO_CONECTADO
    with pytest.raises(CredencialOAuthRevocada):
        await ObtenerAccesoOAuth(repository, cipher, Revocado()).ejecutar(
            empresa_id=EMPRESA,
            sistema=SistemaExterno.GOOGLE_SHEETS,
            configuracion_id=credential_id,
            ahora=AHORA,
        )


async def test_second_link_keeps_the_connected_company_credential() -> None:
    repository = RepositorioFalso()
    cipher = CifradoAesGcm(base64.b64encode(b"x" * 32).decode())
    registrar = RegistrarCredencialOAuth(repository, cipher)
    first_id = await registrar.ejecutar(
        empresa_id=EMPRESA,
        sistema=SistemaExterno.GOOGLE_SHEETS,
        renovacion="refresh-company-one",
        ambiente=Ambiente.HOMOLOGACION,
        ahora=AHORA,
    )
    second_id = await registrar.ejecutar(
        empresa_id=EMPRESA,
        sistema=SistemaExterno.GOOGLE_SHEETS,
        renovacion="refresh-other-account",
        ambiente=Ambiente.HOMOLOGACION,
        ahora=AHORA,
    )
    assert second_id == first_id
    assert (
        await ObtenerAccesoOAuth(repository, cipher, RefrescadorFalso()).ejecutar(
            empresa_id=EMPRESA,
            sistema=SistemaExterno.GOOGLE_SHEETS,
            configuracion_id=first_id,
            ahora=AHORA,
        )
        == "new-access-token"
    )
