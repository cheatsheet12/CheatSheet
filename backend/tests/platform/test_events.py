"""The publisher, and the subscriber that makes `all → observability` executable.

The point being protected here is architectural: an emitting context must be able to
publish an auditable event without importing `observability`. These tests emit as
`billing` would, and assert the audit row appears — with `billing` nowhere in the
imports of the emitting side.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.observability.application.registrar_operacion import RegistrarOperacion
from cheatsheet.contexts.observability.infrastructure.subscriber import SuscriptorDeAuditoria
from cheatsheet.platform.events import PublicadorEnProceso
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import EventoDeDominio

from tests.conftest import INSTANTE_FIJO, RepositorioDeAuditoriaEnMemoria


def _publicador(repositorio: RepositorioDeAuditoriaEnMemoria) -> PublicadorEnProceso:
    publicador = PublicadorEnProceso()
    publicador.suscribir(SuscriptorDeAuditoria(RegistrarOperacion(repositorio)))
    return publicador


@pytest.mark.asyncio
async def test_publicar_un_evento_auditable_deja_su_registro(
    repositorio: RepositorioDeAuditoriaEnMemoria, empresa_id: EmpresaId
):
    evento = EventoAuditable(
        evento_id=uuid4(),
        empresa_id=empresa_id,
        ocurrido_en=INSTANTE_FIJO,
        modulo=Modulo.BILLING,
        accion="emitir_comprobante",
        entidad_afectada="Comprobante:A-0001-42",
        resultado=Resultado.COMPLETADO,
    )

    await _publicador(repositorio).publicar(evento)

    assert len(repositorio.registros) == 1
    assert next(iter(repositorio.registros.values())).modulo is Modulo.BILLING


@pytest.mark.asyncio
async def test_un_evento_no_auditable_pasa_de_largo(
    repositorio: RepositorioDeAuditoriaEnMemoria, empresa_id: EmpresaId
):
    """The same bus carries PagoConfirmado; the audit sink has no opinion about it."""
    evento = EventoDeDominio(evento_id=uuid4(), empresa_id=empresa_id, ocurrido_en=INSTANTE_FIJO)

    await _publicador(repositorio).publicar(evento)

    assert repositorio.registros == {}


@pytest.mark.asyncio
async def test_sin_suscriptores_publicar_no_falla(empresa_id: EmpresaId):
    evento = EventoDeDominio(evento_id=uuid4(), empresa_id=empresa_id, ocurrido_en=INSTANTE_FIJO)

    await PublicadorEnProceso().publicar(evento)


@pytest.mark.asyncio
async def test_la_falla_de_un_suscriptor_propaga_al_emisor(empresa_id: EmpresaId):
    """HS-T5 makes the record a requirement, not a side effect.

    If the audit write fails, the operation must fail with it — a silently swallowed
    exception here would produce operations that happened and were never recorded.
    """

    class SuscriptorRoto:
        async def manejar(self, _evento: EventoDeDominio) -> None:
            raise RuntimeError("la base se cayo")

    publicador = PublicadorEnProceso()
    publicador.suscribir(SuscriptorRoto())

    with pytest.raises(RuntimeError, match="la base se cayo"):
        await publicador.publicar(
            EventoDeDominio(evento_id=uuid4(), empresa_id=empresa_id, ocurrido_en=INSTANTE_FIJO)
        )
