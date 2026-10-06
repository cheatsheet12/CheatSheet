"""`RevisarVencimientos` — casos 23, 24 y 25 del plan.

RN-04 pide que **el sistema** marque la integración inactiva y notifique. Eso quiere decir
que algo mira solo, y lo que se prueba acá es qué reporta cuando mira: sólo transiciones
reales, porque un barrido diario que dice «sigue válido» durante dos años es un barrido que
todo el mundo aprende a ignorar.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.ports import ResultadoDeVerificacion
from cheatsheet.contexts.integrations.application.vencimientos import RevisarVencimientos
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.registro import ParDeAdaptadores
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest import (
    CifradoFalso,
    ConectorProgramado,
    PublicadorFalso,
    RegistroFalso,
    RepositorioIntegracionesEnMemoria,
    VerificadorProgramado,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
CREDENCIAL = CredencialCifrada(contenido=b"cifrado:cert", algoritmo="FALSO/v1")


def _configuracion(sistema: SistemaExterno = SistemaExterno.ARCA) -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion.conectar(
        id=uuid4(),
        empresa_id=EMPRESA,
        sistema=sistema,
        credencial=CREDENCIAL,
        ambiente=Ambiente.HOMOLOGACION,
        ahora=INSTANTE_FIJO,
    )


async def _correr(
    verificador: VerificadorProgramado,
    *,
    configuracion: ConfiguracionDeIntegracion | None = None,
) -> tuple[list[object], PublicadorFalso, ConfiguracionDeIntegracion]:
    configuracion = configuracion or _configuracion()
    integraciones = RepositorioIntegracionesEnMemoria()
    await integraciones.agregar(configuracion)
    publicador = PublicadorFalso()
    registro = RegistroFalso(
        {
            SistemaExterno.ARCA: ParDeAdaptadores(
                conector=ConectorProgramado(), verificador=verificador
            )
        }
    )
    desenlaces = await RevisarVencimientos(
        integraciones=integraciones,
        cifrado=CifradoFalso(),
        adaptadores=registro,
        publicador=publicador,
        reloj=RelojFijo(INSTANTE_FIJO),
        timeout_segundos=1,
    ).ejecutar(empresa_id=EMPRESA)
    return list(desenlaces), publicador, configuracion


def _auditorias(publicador: PublicadorFalso) -> list[EventoAuditable]:
    return [e for e in publicador.eventos if isinstance(e, EventoAuditable)]


async def test_un_certificado_por_vencer_pasa_a_atencion_y_se_reporta() -> None:
    """Caso 23. Avisar antes es lo que convierte RN-04 en algo útil."""
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(
            EstadoDeConexion.ATENCION, "El certificado vence en 20 dias"
        )
    )

    desenlaces, publicador, configuracion = await _correr(verificador)

    assert configuracion.estado is EstadoDeConexion.ATENCION
    assert configuracion.detalle_estado == "El certificado vence en 20 dias"
    assert len(desenlaces) == 1
    assert len(_auditorias(publicador)) == 1


async def test_un_certificado_vencido_pasa_a_no_conectado_y_se_reporta() -> None:
    """Caso 24. RN-04 al pie de la letra: marcada inactiva y notificada."""
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(
            EstadoDeConexion.NO_CONECTADO, "El certificado vencio el 2026-08-01"
        )
    )

    desenlaces, publicador, configuracion = await _correr(verificador)

    assert configuracion.estado is EstadoDeConexion.NO_CONECTADO
    assert len(desenlaces) == 1
    assert len(_auditorias(publicador)) == 1


async def test_un_certificado_sano_no_audita_ni_avisa() -> None:
    """Caso 25. Es el desenlace de todos los días durante dos años."""
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(EstadoDeConexion.CONECTADO)
    )

    desenlaces, publicador, _ = await _correr(verificador)

    assert desenlaces == []
    assert _auditorias(publicador) == []


async def test_el_aviso_no_se_repite_al_dia_siguiente() -> None:
    """Caso 25, la otra mitad: 30 días de aviso no pueden ser 30 mails.

    Se apoya en `registrar_verificacion`, que sólo emite evento cuando el estado cambia:
    el primer día que entra en `ATENCION` reporta, y los 29 siguientes no.
    """
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(EstadoDeConexion.ATENCION, "vence en 20 dias")
    )
    configuracion = _configuracion()

    primero, _, _ = await _correr(verificador, configuracion=configuracion)
    segundo, publicador, _ = await _correr(verificador, configuracion=configuracion)

    assert len(primero) == 1
    assert segundo == []
    assert _auditorias(publicador) == []


async def test_los_sistemas_sin_fecha_de_vencimiento_no_se_revisan() -> None:
    """WhatsApp no tiene un `notAfter` que podamos leer; su reloj es otro barrido."""
    verificador = VerificadorProgramado()

    desenlaces, _, _ = await _correr(
        verificador, configuracion=_configuracion(SistemaExterno.WHATSAPP)
    )

    assert desenlaces == []
    assert verificador.llamadas == 0


async def test_una_credencial_ilegible_no_tumba_el_barrido() -> None:
    """El verificador ya lo reporta como `ATENCION`; acá sólo importa que no explote."""
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(EstadoDeConexion.ATENCION, "no se pudo leer")
    )

    desenlaces, _, configuracion = await _correr(verificador)

    assert len(desenlaces) == 1
    assert configuracion.estado is EstadoDeConexion.ATENCION


async def test_el_evento_de_auditoria_no_lleva_usuario() -> None:
    verificador = VerificadorProgramado(
        resultado=ResultadoDeVerificacion(EstadoDeConexion.NO_CONECTADO, "vencio")
    )

    _, publicador, _ = await _correr(verificador)

    evento = _auditorias(publicador)[0]
    assert evento.usuario_id is None
    assert evento.empresa_id == EMPRESA


async def test_el_reloj_de_pendiente_no_interfiere() -> None:
    """Un ARCA jamás queda `PENDIENTE`, pero el barrido comparte código con el sondeo."""
    configuracion = _configuracion()
    configuracion.registrar_verificacion(
        EstadoDeConexion.ATENCION, "vence pronto", INSTANTE_FIJO + timedelta(days=1)
    )

    assert configuracion.pendiente_desde is None
