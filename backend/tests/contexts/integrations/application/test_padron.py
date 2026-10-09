"""`ConsultarPadron` — caso 10 del plan, ADR-0014, y la regla que sostiene toda la unidad.

Lo que se prueba acá no es que devuelva datos: es **qué diferencia hay entre no encontrar
y no poder preguntar**. Un `None` bloquea al Administrador; una excepción no puede. Si los
dos caminos se juntaran, una tarde mala de ARCA dejaría a una empresa sin poder guardar sus
propios datos fiscales.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ConsultaDePadronNoDisponible,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.application.padron import ConsultarPadron
from cheatsheet.contexts.integrations.application.ports import DatosDePadron
from cheatsheet.contexts.integrations.application.tickets_de_plataforma import (
    ObtenerTicketDePlataforma,
)
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca, TicketDePlataforma
from cheatsheet.contexts.integrations.domain.valores import CLAVE_CUIT, SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.registro import ParDeAdaptadores
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest import (
    CifradoFalso,
    ConectorProgramado,
    EmisorProgramado,
    PadronProgramado,
    RegistroFalso,
    VerificadorProgramado,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
OTRA_EMPRESA = EmpresaId(uuid4())
CUIT_DE_PLATAFORMA = "20111111112"
CUIT_CONSULTADO = "20123456789"

DATOS = DatosDePadron(
    cuit=CUIT_CONSULTADO,
    razon_social="PANADERIA DONA ROSA SRL",
    condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
    activo=True,
)


class TicketsDePlataformaEnMemoria:
    """`PortRepositorioTicketsDePlataforma` sin base: una fila por servicio."""

    def __init__(self) -> None:
        self.filas: dict[ServicioDeArca, TicketDePlataforma] = {}

    async def buscar_para_renovar(self, servicio: ServicioDeArca) -> TicketDePlataforma | None:
        return self.filas.get(servicio)

    async def guardar(self, ticket: TicketDePlataforma) -> None:
        self.filas[ticket.servicio] = ticket


async def _armar(
    padron: PadronProgramado, *, emisor: EmisorProgramado | None = None
) -> tuple[ConsultarPadron, EmisorProgramado]:
    emisor = emisor or EmisorProgramado()
    registro = RegistroFalso(
        {
            SistemaExterno.ARCA: ParDeAdaptadores(
                conector=ConectorProgramado(),
                verificador=VerificadorProgramado(),
                emisor=emisor,
                padron=padron,
            )
        }
    )
    tickets = ObtenerTicketDePlataforma(
        tickets=TicketsDePlataformaEnMemoria(),
        cifrado=CifradoFalso(),
        emisor=emisor,
        credencial=b"credencial-de-plataforma",
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    caso = ConsultarPadron(
        tickets=tickets, adaptadores=registro, cuit_de_plataforma=CUIT_DE_PLATAFORMA
    )
    return caso, emisor


async def test_una_consulta_normal_devuelve_lo_que_dice_el_padron() -> None:
    padron = PadronProgramado(datos=DATOS)
    caso, _ = await _armar(padron)

    datos = await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)

    assert datos is not None
    assert datos.condicion_iva is CondicionIVA.RESPONSABLE_INSCRIPTO


async def test_el_ticket_que_se_usa_es_el_del_padron_no_el_de_facturacion() -> None:
    """Caso 10. Un TA vale para un servicio y ARCA rechaza el que no corresponde.

    Además el ticket llega al adaptador ya descifrado: el texto cifrado nunca sale del
    contexto (ADR-0003 punto 3), y tampoco entra al adaptador de ARCA.
    """
    padron = PadronProgramado(datos=DATOS)
    caso, emisor = await _armar(padron)

    await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)

    assert emisor.llamadas == 1
    assert padron.ultimo_ticket == b"token\nfirma"


async def test_el_cuit_representada_es_el_de_la_plataforma() -> None:
    """ADR-0014: el padrón se consulta como CheatSheet, con su propio certificado."""
    padron = PadronProgramado(datos=DATOS)
    caso, _ = await _armar(padron)

    await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)

    assert padron.ultimos_parametros is not None
    assert padron.ultimos_parametros[CLAVE_CUIT] == CUIT_DE_PLATAFORMA
    assert padron.ultimo_cuit == CUIT_CONSULTADO


async def test_un_cuit_que_arca_no_conoce_devuelve_none() -> None:
    """Y `None`, no una excepción: es la respuesta que después bloquea el guardado."""
    padron = PadronProgramado(datos=None)
    caso, _ = await _armar(padron)

    assert await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO) is None


async def test_una_empresa_sin_arca_conectada_igual_puede_consultar() -> None:
    """ADR-0014. Antes era el caso 12 (no se podía); ahora el paso 2 del onboarding valida
    el CUIT antes de que la empresa delegue nada (diferencia D-08 del guion)."""
    padron = PadronProgramado(datos=DATOS)
    caso, _ = await _armar(padron)

    assert await caso.ejecutar(empresa_id=OTRA_EMPRESA, cuit=CUIT_CONSULTADO) is not None


async def test_dos_empresas_comparten_el_mismo_ticket_de_plataforma() -> None:
    """WSAA da un ticket por certificado y servicio: pedir otro fallaria durante 12 horas."""
    padron = PadronProgramado(datos=DATOS)
    caso, emisor = await _armar(padron)

    await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)
    await caso.ejecutar(empresa_id=OTRA_EMPRESA, cuit=CUIT_CONSULTADO)

    assert emisor.llamadas == 1


async def test_arca_caida_no_se_convierte_en_un_cuit_inexistente() -> None:
    """La regla del módulo, dicha por el test que más importa de este archivo."""
    padron = PadronProgramado(excepcion=ProveedorNoDisponible("ARCA no responde"))
    caso, _ = await _armar(padron)

    with pytest.raises(ConsultaDePadronNoDisponible):
        await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)


async def test_un_rechazo_del_pedido_tampoco_niega_el_cuit() -> None:
    """`ConexionRechazada` contra una consulta habla del pedido, no del CUIT preguntado."""
    padron = PadronProgramado(excepcion=ConexionRechazada("el certificado no autoriza el padron"))
    caso, _ = await _armar(padron)

    with pytest.raises(ConsultaDePadronNoDisponible):
        await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)


async def test_si_no_se_puede_emitir_el_ticket_la_consulta_no_esta_disponible() -> None:
    padron = PadronProgramado(datos=DATOS)
    caso, _ = await _armar(padron, emisor=EmisorProgramado(excepcion=ConexionRechazada("revocado")))

    with pytest.raises(ConsultaDePadronNoDisponible):
        await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)

    assert padron.llamadas == 0
