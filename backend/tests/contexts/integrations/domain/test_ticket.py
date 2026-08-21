"""El agregado `TicketDeAcceso` — caso 6 del plan.

Poco código y una distinción que carga con todo: **vigente** y **hay que renovar** son dos
preguntas distintas, y confundirlas es lo que haría que una caída de ARCA durante una
renovación tumbe una operación que podría haber seguido con el ticket viejo.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from cheatsheet.contexts.integrations.domain.ticket import (
    MARGEN_DE_RENOVACION,
    ServicioDeArca,
    TicketDeAcceso,
)
from cheatsheet.contexts.integrations.domain.valores import CredencialCifrada
from cheatsheet.shared.empresa import EmpresaId

from tests.conftest import INSTANTE_FIJO

CONTENIDO = CredencialCifrada(contenido=b"cifrado:token", algoritmo="FALSO/v1")
OTRO = CredencialCifrada(contenido=b"cifrado:otro", algoritmo="FALSO/v1")


def _ticket(horas: float = 12) -> TicketDeAcceso:
    return TicketDeAcceso(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        servicio=ServicioDeArca.WSFE,
        contenido=CONTENIDO,
        expira_en=INSTANTE_FIJO + timedelta(hours=horas),
    )


def test_un_ticket_recien_emitido_esta_vigente_y_no_hay_que_renovarlo() -> None:
    ticket = _ticket()

    assert ticket.vigente(INSTANTE_FIJO)
    assert not ticket.hay_que_renovar(INSTANTE_FIJO)


def test_dentro_del_margen_hay_que_renovar_pero_el_ticket_sigue_sirviendo() -> None:
    """Caso 6, y la distinción entera.

    Que siga sirviendo es lo que permite el respaldo: si ARCA se cae justo cuando toca
    renovar, la operación continúa con el que ya teníamos en vez de fallar.
    """
    ticket = _ticket()
    dentro = ticket.expira_en - MARGEN_DE_RENOVACION + timedelta(minutes=1)

    assert ticket.hay_que_renovar(dentro)
    assert ticket.vigente(dentro)


def test_pasado_el_vencimiento_ni_sirve_ni_alcanza() -> None:
    ticket = _ticket()
    despues = ticket.expira_en + timedelta(seconds=1)

    assert not ticket.vigente(despues)
    assert ticket.hay_que_renovar(despues)


def test_justo_en_el_borde_del_margen_ya_hay_que_renovar() -> None:
    """Un ticket que expira entre el chequeo y la llamada falla a mitad de camino."""
    ticket = _ticket()

    assert ticket.hay_que_renovar(ticket.expira_en - MARGEN_DE_RENOVACION)


def test_el_margen_se_puede_ajustar_por_configuracion() -> None:
    ticket = _ticket()
    dos_horas = timedelta(hours=2)

    assert ticket.hay_que_renovar(ticket.expira_en - timedelta(hours=1), dos_horas)
    assert not ticket.hay_que_renovar(ticket.expira_en - timedelta(hours=3), dos_horas)


def test_reemplazar_pisa_contenido_y_vencimiento() -> None:
    """Una fila por (empresa, servicio): renovar sobrescribe, no acumula."""
    ticket = _ticket()
    nuevo_vencimiento = INSTANTE_FIJO + timedelta(hours=24)

    ticket.reemplazar(OTRO, nuevo_vencimiento)

    assert ticket.contenido == OTRO
    assert ticket.expira_en == nuevo_vencimiento


def test_los_dos_servicios_de_arca_son_valores_distintos() -> None:
    """La clave de almacenamiento los usa: un typo mintaría un TA que ARCA rechaza."""
    assert ServicioDeArca.WSFE.value == "wsfe"
    assert ServicioDeArca.PADRON_A5.value == "ws_sr_padron_a5"
    assert len(set(ServicioDeArca)) == 2
