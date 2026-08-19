"""`ObtenerTicketDeAcceso` — casos 18 y 19 del plan, y el respaldo que no estaba planeado.

Es la operación que ADR-0004 publica y de la que va a colgar el épico 5, así que lo que se
prueba acá no es sólo que devuelva algo: es **cuándo llama a ARCA y cuándo no**. Llamar de
más rompe contra la regla del proveedor —un TA vivo por CUIT y servicio— y llamar de menos
entrega un ticket que va a vencer a mitad de una emisión.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
    TicketNoDisponible,
)
from cheatsheet.contexts.integrations.application.tickets import ObtenerTicketDeAcceso
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca, TicketDeAcceso
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.registro import ParDeAdaptadores
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest import (
    CifradoFalso,
    ConectorProgramado,
    EmisorProgramado,
    RegistroFalso,
    RepositorioIntegracionesEnMemoria,
    RepositorioTicketsEnMemoria,
    VerificadorProgramado,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
CREDENCIAL = CredencialCifrada(contenido=b"cifrado:certificado", algoritmo="FALSO/v1")


def _configuracion_de_arca() -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion.conectar(
        id=uuid4(),
        empresa_id=EMPRESA,
        sistema=SistemaExterno.ARCA,
        credencial=CREDENCIAL,
        ambiente=Ambiente.HOMOLOGACION,
        ahora=INSTANTE_FIJO,
    )


def _guardado(horas: float) -> TicketDeAcceso:
    return TicketDeAcceso(
        id=uuid4(),
        empresa_id=EMPRESA,
        servicio=ServicioDeArca.WSFE,
        contenido=CredencialCifrada(contenido=b"cifrado:viejo", algoritmo="FALSO/v1"),
        expira_en=INSTANTE_FIJO + timedelta(hours=horas),
    )


async def _armar(
    emisor: EmisorProgramado,
    *,
    con_configuracion: bool = True,
    guardado: TicketDeAcceso | None = None,
) -> tuple[ObtenerTicketDeAcceso, RepositorioTicketsEnMemoria]:
    integraciones = RepositorioIntegracionesEnMemoria()
    if con_configuracion:
        await integraciones.agregar(_configuracion_de_arca())
    tickets = RepositorioTicketsEnMemoria()
    if guardado is not None:
        await tickets.agregar(guardado)
    registro = RegistroFalso(
        {
            SistemaExterno.ARCA: ParDeAdaptadores(
                conector=ConectorProgramado(),
                verificador=VerificadorProgramado(),
                emisor=emisor,
            )
        }
    )
    caso = ObtenerTicketDeAcceso(
        integraciones=integraciones,
        tickets=tickets,
        cifrado=CifradoFalso(),
        adaptadores=registro,
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    return caso, tickets


async def test_sin_ticket_guardado_se_emite_uno_y_se_persiste() -> None:
    emisor = EmisorProgramado()
    caso, tickets = await _armar(emisor)

    vigente = await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)

    assert vigente.contenido == b"token\nfirma"
    assert emisor.llamadas == 1
    # Persistido, que es la razón de ser de la tabla: ARCA no da un segundo TA.
    guardado = tickets.filas[(EMPRESA, ServicioDeArca.WSFE)]
    assert guardado.expira_en == vigente.expira_en


async def test_el_ticket_se_guarda_cifrado() -> None:
    """Caso 20 a nivel de aplicación: el token en claro no llega al repositorio."""
    emisor = EmisorProgramado()
    caso, tickets = await _armar(emisor)

    await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)

    guardado = tickets.filas[(EMPRESA, ServicioDeArca.WSFE)]
    assert guardado.contenido.contenido.startswith(b"cifrado:")
    assert guardado.contenido.contenido != b"token\nfirma"


async def test_un_ticket_vigente_se_reusa_sin_llamar_a_arca() -> None:
    """Caso 18, y la regla del proveedor: WSAA rechaza un segundo TA mientras viva el primero."""
    emisor = EmisorProgramado()
    caso, _ = await _armar(emisor, guardado=_guardado(horas=12))

    vigente = await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)

    assert emisor.llamadas == 0
    assert vigente.contenido == b"viejo"


async def test_dentro_del_margen_se_renueva_y_se_reemplaza_la_fila() -> None:
    """Caso 19. Y reemplaza: una fila por (empresa, servicio), como dice el índice único."""
    emisor = EmisorProgramado(expira_en=INSTANTE_FIJO + timedelta(hours=24))
    guardado = _guardado(horas=0.25)
    caso, tickets = await _armar(emisor, guardado=guardado)

    vigente = await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)

    assert emisor.llamadas == 1
    assert vigente.expira_en == INSTANTE_FIJO + timedelta(hours=24)
    assert len(tickets.filas) == 1
    assert tickets.filas[(EMPRESA, ServicioDeArca.WSFE)].id == guardado.id


async def test_si_arca_se_cae_al_renovar_se_sigue_con_el_ticket_viejo() -> None:
    """No estaba en el plan y lo pidió el código.

    Un ticket dentro del margen todavía sirve. Si ARCA se cae justo en la renovación,
    fallar sería tirar abajo una emisión que podía haber salido — que es exactamente por
    lo que `vigente` y `hay_que_renovar` son dos preguntas y no una.
    """
    emisor = EmisorProgramado(excepcion=ProveedorNoDisponible("ARCA no responde"))
    caso, tickets = await _armar(emisor, guardado=_guardado(horas=0.25))

    vigente = await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)

    assert vigente.contenido == b"viejo"
    # Y no se pisó la fila con nada: no había nada nuevo que guardar.
    assert tickets.filas[(EMPRESA, ServicioDeArca.WSFE)].contenido.contenido == b"cifrado:viejo"


async def test_si_arca_se_cae_y_el_ticket_ya_vencio_no_hay_nada_que_entregar() -> None:
    emisor = EmisorProgramado(excepcion=ProveedorNoDisponible("ARCA no responde"))
    caso, _ = await _armar(emisor, guardado=_guardado(horas=-1))

    with pytest.raises(TicketNoDisponible):
        await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)


async def test_una_credencial_rechazada_tampoco_deja_ticket() -> None:
    emisor = EmisorProgramado(excepcion=ConexionRechazada("certificado revocado"))
    caso, _ = await _armar(emisor)

    with pytest.raises(TicketNoDisponible) as fallo:
        await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)

    assert "revocado" in str(fallo.value)


async def test_una_empresa_sin_arca_conectada_recibe_un_error_claro() -> None:
    """Lo que `billing` va a ver cuando alguien intente facturar sin haber conectado ARCA."""
    emisor = EmisorProgramado()
    caso, _ = await _armar(emisor, con_configuracion=False)

    with pytest.raises(TicketNoDisponible) as fallo:
        await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)

    assert "no tiene conectada" in str(fallo.value)
    assert emisor.llamadas == 0


async def test_dos_servicios_conviven_como_dos_tickets() -> None:
    """Caso 22. El padrón es la unidad siguiente y usa el mismo mecanismo."""
    emisor = EmisorProgramado()
    caso, tickets = await _armar(emisor)

    await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.WSFE)
    await caso.ejecutar(empresa_id=EMPRESA, servicio=ServicioDeArca.PADRON_A5)

    assert len(tickets.filas) == 2
    assert emisor.llamadas == 2
