"""El `wamid` de un recordatorio contra el motor (U7, casos 2 y 10; riesgo de RLS del plan).

`recordatorio` no tiene `empresa_id`: su aislamiento pasa por el cobro padre (`aislamiento_por_cobro`,
migración 0019). Lo que hay que demostrar con un motor real es que la búsqueda por `externo_id`
**no cruza empresas** (un `wamid` ajeno no existe) y que el índice único parcial se respeta.

Sin PostgreSQL se saltean; los confirma la CI del PR.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from cheatsheet.contexts.payments.application.entregas import RegistrarEntregaDeRecordatorio
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.contexts.payments.infrastructure.repositorio_recordatorio import (
    RepositorioRecordatoriosPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.payments.application.test_confirmacion import PublicadorFalso
from tests.integracion.conftest import requiere_base
from tests.integracion.test_cobros_postgres import AHORA, _cliente, _cobro, _empresa, _guardar

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]


async def _recordatorio_enviado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine, externo_id: str
) -> tuple[EmpresaId, Recordatorio]:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id, vence_en_dias=0, preferencia=f"pref-{uuid.uuid4()}")
    await _guardar(sesiones, empresa_id, cobro)
    recordatorio = Recordatorio(id=uuid.uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
    recordatorio.marcar_enviado(AHORA + timedelta(days=1), externo_id=externo_id)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioRecordatoriosPostgres(sesion).agregar(recordatorio)
    return empresa_id, recordatorio


async def test_el_callback_encuentra_el_recordatorio_por_su_wamid_y_deja_el_motivo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    wamid = f"wamid-{uuid.uuid4()}"
    empresa_id, recordatorio = await _recordatorio_enviado(sesiones, engine_dueno, wamid)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        caso = RegistrarEntregaDeRecordatorio(
            recordatorios=RepositorioRecordatoriosPostgres(sesion), publicador=PublicadorFalso()
        )
        encontrado = await caso.ejecutar(
            empresa_id=empresa_id,
            externo_id=wamid,
            estado=EstadoEntrega.FALLIDO,
            codigo_de_error="131047",
            ahora=AHORA,
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        (leido,) = await RepositorioRecordatoriosPostgres(sesion).de_cobro(recordatorio.cobro_id)
    assert encontrado is True
    assert leido.estado_entrega is EstadoEntrega.FALLIDO
    assert leido.ultimo_error == "131047"
    assert leido.externo_id == wamid


async def test_el_wamid_de_un_recordatorio_de_otra_empresa_no_existe(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 10: RLS por el cobro padre. El callback de B que llega por A no toca nada."""
    wamid = f"wamid-{uuid.uuid4()}"
    _, recordatorio = await _recordatorio_enviado(sesiones, engine_dueno, wamid)
    otra = await _empresa(engine_dueno)

    async with sesion_de_empresa(sesiones, otra) as sesion:
        caso = RegistrarEntregaDeRecordatorio(
            recordatorios=RepositorioRecordatoriosPostgres(sesion), publicador=PublicadorFalso()
        )
        encontrado = await caso.ejecutar(
            empresa_id=otra, externo_id=wamid, estado=EstadoEntrega.LEIDO, ahora=AHORA
        )

    assert encontrado is False
    async with engine_dueno.connect() as conexion:
        estado = (
            await conexion.execute(
                text("SELECT estado_entrega FROM recordatorio WHERE id = :id"),
                {"id": recordatorio.id},
            )
        ).scalar_one()
    assert estado == EstadoEntrega.ENVIADO.value
