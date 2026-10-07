"""A WhatsApp business account belongs to one empresa (unit `plantillas-de-whatsapp-en-meta`, G4).

The unique index of migration 0036 is the guard; this proves the repository turns *that* index's
violation into a domain error answered as 409, and lets every other violation through untouched.
The index itself is proven against PostgreSQL in `tests/integracion/test_waba_unica_postgres.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from cheatsheet.api.errors import _codigo_para
from cheatsheet.contexts.integrations.application.errors import CuentaDeWhatsAppEnUso
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    INDICE_WABA_UNICO,
    MENSAJE_CUENTA_EN_USO,
    RepositorioIntegracionesSQL,
)
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


class SesionQueChoca:
    """A session whose `flush` fails the way asyncpg reports a violated constraint."""

    def __init__(self, motivo: str) -> None:
        self._motivo = motivo

    def add(self, _fila: object) -> None:
        return None

    async def get(self, _modelo: object, _clave: object) -> Any:
        return _FilaVacia()

    async def flush(self) -> None:
        raise IntegrityError("INSERT ...", {}, Exception(self._motivo))


class _FilaVacia:
    """Accepts the attribute writes `_volcar` makes."""


def _configuracion() -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion.registrar(
        id=uuid.uuid4(),
        empresa_id=EmpresaId(uuid.uuid4()),
        sistema=SistemaExterno.WHATSAPP,
        credencial=CredencialCifrada(contenido=b"x", algoritmo="fernet"),
        ambiente=Ambiente.HOMOLOGACION,
        ahora=AHORA,
        estado=EstadoDeConexion.CONECTADO,
        detalle=None,
        parametros={"waba_id": "123"},
    )


def _repositorio(motivo: str) -> RepositorioIntegracionesSQL:
    return RepositorioIntegracionesSQL(cast(AsyncSession, SesionQueChoca(motivo)))


async def test_agregar_traduce_la_violacion_del_indice_de_la_cuenta() -> None:
    repositorio = _repositorio(
        f'duplicate key value violates unique constraint "{INDICE_WABA_UNICO}"'
    )
    with pytest.raises(CuentaDeWhatsAppEnUso):
        await repositorio.agregar(_configuracion())


async def test_guardar_traduce_la_violacion_del_indice_de_la_cuenta() -> None:
    repositorio = _repositorio(
        f'duplicate key value violates unique constraint "{INDICE_WABA_UNICO}"'
    )
    with pytest.raises(CuentaDeWhatsAppEnUso):
        await repositorio.guardar(_configuracion())


async def test_cualquier_otra_violacion_sigue_siendo_un_error_de_verdad() -> None:
    repositorio = _repositorio('violates unique constraint "uq_integracion_empresa_sistema"')
    with pytest.raises(IntegrityError):
        await repositorio.agregar(_configuracion())


async def test_el_error_se_contesta_como_409_sin_nombrar_a_la_otra_empresa() -> None:
    assert _codigo_para(CuentaDeWhatsAppEnUso(MENSAJE_CUENTA_EN_USO)) == 409
    assert "otra empresa" in MENSAJE_CUENTA_EN_USO
