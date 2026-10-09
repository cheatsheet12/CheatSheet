"""`ObtenerTicketDePlataforma` — el ticket del certificado de CheatSheet (ADR-0014).

Las reglas son las de ADR-0004 aplicadas a un solo certificado para todas las empresas: se
reusa hasta cerca del vencimiento, se vuelve al guardado si renovar falla, y nunca sale el
texto cifrado.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ProveedorNoDisponible,
    TicketNoDisponible,
    TicketTodaviaVigente,
)
from cheatsheet.contexts.integrations.application.tickets_de_plataforma import (
    ObtenerTicketDePlataforma,
)
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca, TicketDePlataforma
from cheatsheet.contexts.integrations.domain.valores import CredencialCifrada
from cheatsheet.shared.clock import RelojFijo

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest import ALGORITMO_FALSO, CifradoFalso, EmisorProgramado

pytestmark = pytest.mark.asyncio


class TicketsEnMemoria:
    def __init__(self) -> None:
        self.filas: dict[ServicioDeArca, TicketDePlataforma] = {}
        self.guardados = 0

    async def buscar_para_renovar(self, servicio: ServicioDeArca) -> TicketDePlataforma | None:
        return self.filas.get(servicio)

    async def guardar(self, ticket: TicketDePlataforma) -> None:
        self.guardados += 1
        self.filas[ticket.servicio] = ticket


def _caso(emisor: EmisorProgramado, tickets: TicketsEnMemoria) -> ObtenerTicketDePlataforma:
    return ObtenerTicketDePlataforma(
        tickets=tickets,
        cifrado=CifradoFalso(),
        emisor=emisor,
        credencial=b"credencial-de-plataforma",
        reloj=RelojFijo(INSTANTE_FIJO),
    )


def _guardado(expira_en_horas: float) -> TicketDePlataforma:
    return TicketDePlataforma(
        servicio=ServicioDeArca.WSFE,
        contenido=CredencialCifrada(contenido=b"cifrado:viejo\nsign", algoritmo=ALGORITMO_FALSO),
        expira_en=INSTANTE_FIJO + timedelta(hours=expira_en_horas),
    )


async def test_sin_ticket_guardado_emite_uno_y_lo_guarda_cifrado() -> None:
    tickets, emisor = TicketsEnMemoria(), EmisorProgramado()

    vigente = await _caso(emisor, tickets).ejecutar(ServicioDeArca.WSFE)

    assert vigente.contenido == b"token\nfirma"
    assert tickets.filas[ServicioDeArca.WSFE].contenido.contenido == b"cifrado:token\nfirma"
    assert emisor.llamadas == 1


async def test_un_ticket_lejos_de_vencer_se_reusa_sin_llamar_a_wsaa() -> None:
    tickets, emisor = TicketsEnMemoria(), EmisorProgramado()
    tickets.filas[ServicioDeArca.WSFE] = _guardado(10)

    vigente = await _caso(emisor, tickets).ejecutar(ServicioDeArca.WSFE)

    assert vigente.contenido == b"viejo\nsign"
    assert emisor.llamadas == 0


async def test_cerca_del_vencimiento_se_renueva_y_se_reemplaza() -> None:
    tickets, emisor = TicketsEnMemoria(), EmisorProgramado()
    tickets.filas[ServicioDeArca.WSFE] = _guardado(0.1)

    vigente = await _caso(emisor, tickets).ejecutar(ServicioDeArca.WSFE)

    assert vigente.contenido == b"token\nfirma"
    assert emisor.llamadas == 1
    assert tickets.guardados == 1


async def test_si_arca_ya_tiene_uno_vigente_se_usa_el_guardado() -> None:
    """`coe.alreadyAuthenticated`: la respuesta es usar el que ya tenemos."""
    tickets = TicketsEnMemoria()
    tickets.filas[ServicioDeArca.WSFE] = _guardado(0.1)
    emisor = EmisorProgramado(excepcion=TicketTodaviaVigente("ya posee un TA valido"))

    vigente = await _caso(emisor, tickets).ejecutar(ServicioDeArca.WSFE)

    assert vigente.contenido == b"viejo\nsign"


async def test_sin_guardado_y_con_wsaa_caido_no_hay_ticket() -> None:
    emisor = EmisorProgramado(excepcion=ProveedorNoDisponible("WSAA no responde"))

    with pytest.raises(TicketNoDisponible):
        await _caso(emisor, TicketsEnMemoria()).ejecutar(ServicioDeArca.WSFE)


async def test_cada_servicio_tiene_su_propio_ticket() -> None:
    """Un TA vale para un servicio: el del padrón no sirve para facturar."""
    tickets, emisor = TicketsEnMemoria(), EmisorProgramado()
    caso = _caso(emisor, tickets)

    await caso.ejecutar(ServicioDeArca.WSFE)
    await caso.ejecutar(ServicioDeArca.PADRON_A5)

    assert emisor.llamadas == 2
    assert set(tickets.filas) == {ServicioDeArca.WSFE, ServicioDeArca.PADRON_A5}
