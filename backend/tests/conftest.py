"""Shared test fixtures.

The doubles here are hand-written rather than `unittest.mock` objects, and that is a
choice, not an omission: a `Mock` satisfies any interface, including one that no
longer exists. `RepositorioDeAuditoriaEnMemoria` implements `PortRegistroDeAuditoria`
for real, so the day the port changes, these tests fail — which is the whole point of
having a port.

Integration tests need a real PostgreSQL, because Row-Level Security is a feature of
the engine and cannot be faked. They are skipped when the database is not configured,
so `pytest` passes on a laptop without Docker; CI always configures it, so the gate
never silently stops checking. See `backend/docker-compose.yml`.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.observability.application.errors import RegistroDuplicado
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.shared.auditoria import (
    EntidadAfectada,
    EventoAuditable,
    Iniciador,
    Modulo,
    Resultado,
)
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.tenant import TenantId

INSTANTE_FIJO = datetime(2026, 8, 12, 15, 30, tzinfo=UTC)


class RepositorioDeAuditoriaEnMemoria:
    """A real implementation of `PortRegistroDeAuditoria`, backed by a dict.

    It reproduces the one behaviour the production adapter has that matters to the use
    case: a duplicate `evento_id` raises instead of overwriting.
    """

    def __init__(self) -> None:
        self.registros: dict[UUID, RegistroDeAuditoria] = {}

    async def agregar(self, registro: RegistroDeAuditoria) -> None:
        if any(r.evento_id == registro.evento_id for r in self.registros.values()):
            raise RegistroDuplicado(registro.evento_id)
        self.registros[registro.id] = registro

    async def buscar_por_evento(self, evento_id: UUID) -> RegistroDeAuditoria | None:
        return next((r for r in self.registros.values() if r.evento_id == evento_id), None)

    async def buscar_por_id(self, registro_id: UUID) -> RegistroDeAuditoria | None:
        return self.registros.get(registro_id)


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo(INSTANTE_FIJO)


@pytest.fixture
def tenant_id() -> TenantId:
    return TenantId(uuid4())


@pytest.fixture
def repositorio() -> RepositorioDeAuditoriaEnMemoria:
    return RepositorioDeAuditoriaEnMemoria()


@pytest.fixture
def evento_auditable(tenant_id: TenantId) -> EventoAuditable:
    return EventoAuditable(
        evento_id=uuid4(),
        tenant_id=tenant_id,
        ocurrido_en=INSTANTE_FIJO,
        modulo=Modulo.IDENTITY,
        operacion="cambiar_rol_de_usuario",
        entidad_afectada=EntidadAfectada(tipo="Usuario", identificador=str(uuid4())),
        iniciador=Iniciador.sistema("test"),
        resultado=Resultado.COMPLETADO,
    )


def url_de_migraciones() -> str | None:
    return os.environ.get("DATABASE_URL_MIGRATIONS", "").strip() or None


requiere_base = pytest.mark.skipif(
    url_de_migraciones() is None,
    reason="Necesita PostgreSQL: levantá backend/docker-compose.yml y exportá DATABASE_URL*",
)
