"""`ConsultarPadron` — casos 10 y 12 del plan, y la regla que sostiene toda la unidad.

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
from cheatsheet.contexts.integrations.application.tickets import ObtenerTicketDeAcceso
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_CUIT,
    Ambiente,
    CredencialCifrada,
    SistemaExterno,
)
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
    RepositorioIntegracionesEnMemoria,
    RepositorioTicketsEnMemoria,
    VerificadorProgramado,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
OTRA_EMPRESA = EmpresaId(uuid4())
CUIT_DEL_CERTIFICADO = "30111111117"
CUIT_CONSULTADO = "20123456789"

DATOS = DatosDePadron(
    cuit=CUIT_CONSULTADO,
    razon_social="PANADERIA DONA ROSA SRL",
    condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
    activo=True,
)


def _configuracion(
    empresa_id: EmpresaId, *, cuit: str = CUIT_DEL_CERTIFICADO
) -> ConfiguracionDeIntegracion:
    configuracion = ConfiguracionDeIntegracion.conectar(
        id=uuid4(),
        empresa_id=empresa_id,
        sistema=SistemaExterno.ARCA,
        credencial=CredencialCifrada(contenido=b"cifrado:cert", algoritmo="FALSO/v1"),
        ambiente=Ambiente.HOMOLOGACION,
        ahora=INSTANTE_FIJO,
    )
    configuracion.actualizar_parametros({CLAVE_CUIT: cuit})
    return configuracion


async def _armar(
    padron: PadronProgramado,
    *,
    emisor: EmisorProgramado | None = None,
    configuraciones: list[ConfiguracionDeIntegracion] | None = None,
) -> tuple[ConsultarPadron, EmisorProgramado]:
    emisor = emisor or EmisorProgramado()
    integraciones = RepositorioIntegracionesEnMemoria()
    for configuracion in (
        configuraciones if configuraciones is not None else [_configuracion(EMPRESA)]
    ):
        await integraciones.agregar(configuracion)
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
    tickets = ObtenerTicketDeAcceso(
        integraciones=integraciones,
        tickets=RepositorioTicketsEnMemoria(),
        cifrado=CifradoFalso(),
        adaptadores=registro,
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    caso = ConsultarPadron(tickets=tickets, integraciones=integraciones, adaptadores=registro)
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


async def test_el_cuit_representada_sale_de_la_configuracion() -> None:
    """El adaptador recibe los parámetros guardados, no los del pedido."""
    padron = PadronProgramado(datos=DATOS)
    caso, _ = await _armar(padron)

    await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)

    assert padron.ultimos_parametros is not None
    assert padron.ultimos_parametros[CLAVE_CUIT] == CUIT_DEL_CERTIFICADO
    assert padron.ultimo_cuit == CUIT_CONSULTADO


async def test_un_cuit_que_arca_no_conoce_devuelve_none() -> None:
    """Y `None`, no una excepción: es la respuesta que después bloquea el guardado."""
    padron = PadronProgramado(datos=None)
    caso, _ = await _armar(padron)

    assert await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO) is None


async def test_una_empresa_sin_arca_no_consulta_ni_toca_la_red() -> None:
    """Caso 12. Es la situación normal apenas termina el onboarding, no una anomalía."""
    padron = PadronProgramado(datos=DATOS)
    caso, emisor = await _armar(padron, configuraciones=[])

    with pytest.raises(ConsultaDePadronNoDisponible, match="no tiene conectada"):
        await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)

    assert padron.llamadas == 0
    assert emisor.llamadas == 0


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


async def test_la_empresa_a_no_consulta_con_la_credencial_de_la_b() -> None:
    """Caso 22 a nivel de aplicación: el aislamiento no depende sólo de RLS.

    La configuración se busca por `empresa_id`, así que una empresa sin ARCA no hereda la
    credencial de otra que sí la tiene, aunque las dos vivan en el mismo repositorio.
    """
    padron = PadronProgramado(datos=DATOS)
    caso, _ = await _armar(padron, configuraciones=[_configuracion(OTRA_EMPRESA)])

    with pytest.raises(ConsultaDePadronNoDisponible):
        await caso.ejecutar(empresa_id=EMPRESA, cuit=CUIT_CONSULTADO)

    assert padron.llamadas == 0
