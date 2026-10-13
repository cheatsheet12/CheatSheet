"""The platform ticket survives whatever the request that minted it does next (ADR-0014).

WSAA hands out one ticket per certificate and service and refuses a second while the first is
alive (`coe.alreadyAuthenticated`). A ticket minted and then lost to a rollback is therefore not
a missing row: it is twelve hours in which no company can reach WSFE. Staging hit it on
2026-10-13, when a company that had not delegated was rejected on connect and took the ticket
down with its transaction.

Only a real PostgreSQL can show it: the bug is about which transaction the row belongs to.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.ports import TicketEmitido
from cheatsheet.contexts.integrations.application.tickets_de_plataforma import (
    ObtenerTicketDePlataforma,
)
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    RepositorioTicketsDePlataformaSQL,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest import CifradoFalso, EmisorProgramado
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]


class ConexionRechazadaDespues(Exception):
    """What the request does after it holds a ticket: here, fail like a rejected connection."""


class EmisorLento(EmisorProgramado):
    """Takes long enough for a second request to arrive while the first is still minting."""

    async def emitir(self, credencial: bytes, servicio: ServicioDeArca) -> TicketEmitido:
        await asyncio.sleep(0.2)
        return await super().emitir(credencial, servicio)


def _caso(sesion: AsyncSession, emisor: EmisorProgramado) -> ObtenerTicketDePlataforma:
    return ObtenerTicketDePlataforma(
        tickets=RepositorioTicketsDePlataformaSQL(sesion),
        cifrado=CifradoFalso(),
        emisor=emisor,
        credencial=b"credencial-de-plataforma",
        reloj=RelojFijo(INSTANTE_FIJO),
    )


async def _tickets_guardados(engine_dueno: AsyncEngine) -> int:
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT count(*) FROM ticket_de_plataforma WHERE servicio = 'wsfe'")
        )
        return int(filas.scalar_one())


async def _obtener_y_fallar(
    sesiones: async_sessionmaker[AsyncSession], emisor: EmisorProgramado
) -> None:
    async with sesion_de_empresa(sesiones, EmpresaId(uuid4())) as sesion:
        await _caso(sesion, emisor).ejecutar(ServicioDeArca.WSFE)
        raise ConexionRechazadaDespues


async def _pedido_que_falla(
    sesiones: async_sessionmaker[AsyncSession], emisor: EmisorProgramado
) -> None:
    with pytest.raises(ConexionRechazadaDespues):
        await _obtener_y_fallar(sesiones, emisor)


async def test_un_ticket_emitido_sobrevive_al_rollback_del_pedido(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """The staging incident: the connection is rejected after WSAA already answered."""
    await _pedido_que_falla(sesiones, EmisorProgramado())

    assert await _tickets_guardados(engine_dueno) == 1


async def test_despues_del_rollback_el_proximo_pedido_reusa_el_ticket(
    sesiones: async_sessionmaker[AsyncSession],
) -> None:
    """Asking WSAA again is exactly what it answers with `coe.alreadyAuthenticated`."""
    emisor = EmisorProgramado()
    await _pedido_que_falla(sesiones, emisor)

    async with sesion_de_empresa(sesiones, EmpresaId(uuid4())) as sesion:
        vigente = await _caso(sesion, emisor).ejecutar(ServicioDeArca.WSFE)

    assert vigente.contenido == b"token\nfirma"
    assert emisor.llamadas == 1


async def test_dos_pedidos_a_la_vez_piden_un_solo_ticket(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """The second waits for the first's lock and reuses what it stored."""
    emisor = EmisorLento()

    async def pedido() -> bytes:
        async with sesion_de_empresa(sesiones, EmpresaId(uuid4())) as sesion:
            return (await _caso(sesion, emisor).ejecutar(ServicioDeArca.WSFE)).contenido

    primero, segundo = await asyncio.gather(pedido(), pedido())

    assert primero == segundo
    assert emisor.llamadas == 1
    assert await _tickets_guardados(engine_dueno) == 1
