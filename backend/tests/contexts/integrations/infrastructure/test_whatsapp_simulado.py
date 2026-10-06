"""El adaptador simulado de WhatsApp — caso 25 del plan, y su valor real.

Lo que se prueba acá no es que el simulado «funcione»: es que **no pueda usarse en
producción** y que recorra la misma capa de traducción que el adaptador real. Ese segundo
punto es la razón de que exista: un simulado con su propia lógica prueba su propia lógica.
"""

from __future__ import annotations

import pytest
from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import MaterialDeConexion
from cheatsheet.contexts.integrations.domain.valores import CLAVE_ETIQUETA, EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.whatsapp.mapeo import (
    CLAVE_PHONE_NUMBER_ID,
    CLAVE_WABA_ID,
)
from cheatsheet.contexts.integrations.infrastructure.whatsapp.simulado import (
    PARAMETRO_CALIDAD,
    PARAMETRO_NAME_STATUS,
    WhatsAppSimulado,
)
from cheatsheet.platform.settings import Entorno

IDENTIFICADORES = {CLAVE_PHONE_NUMBER_ID: "109876543210987", CLAVE_WABA_ID: "102030405060708"}
FAKE_TOKEN_FOR_TESTS = b"fake-token-for-tests"


def _material(**extra: str) -> MaterialDeConexion:
    return MaterialDeConexion(
        contenido=FAKE_TOKEN_FOR_TESTS, parametros={**IDENTIFICADORES, **extra}
    )


def test_el_simulado_de_whatsapp_no_se_puede_construir_en_produccion() -> None:
    """Caso 25. No una advertencia: un `RuntimeError` antes de servir un solo pedido.

    Es lo que impide que una empresa crea que su número está conectado mientras nada
    llegó nunca a Meta.
    """
    with pytest.raises(RuntimeError) as fallo:
        WhatsAppSimulado(Entorno.PRODUCTION)

    assert "produccion" in str(fallo.value)


@pytest.mark.parametrize(
    "entorno", [Entorno.LOCAL, Entorno.TEST, Entorno.STAGING], ids=["local", "test", "staging"]
)
def test_fuera_de_produccion_si_se_construye(entorno: Entorno) -> None:
    assert WhatsAppSimulado(entorno) is not None


@pytest.mark.asyncio
async def test_conectar_deja_el_numero_pendiente_por_defecto() -> None:
    """Que es lo que realmente pasa: Meta acepta y se toma entre 24 y 72 horas."""
    resultado = await WhatsAppSimulado(Entorno.TEST).conectar(_material())

    assert resultado.estado is EstadoDeConexion.PENDIENTE
    assert resultado.credencial == FAKE_TOKEN_FOR_TESTS


@pytest.mark.asyncio
async def test_el_escenario_viaja_a_la_fila_para_que_el_sondeo_lo_encuentre() -> None:
    """El sondeo corre 30 minutos después: tiene que ver el mismo escenario que se armó."""
    resultado = await WhatsAppSimulado(Entorno.TEST).conectar(
        _material(**{PARAMETRO_NAME_STATUS: "APPROVED"})
    )

    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.parametros[PARAMETRO_NAME_STATUS] == "APPROVED"
    assert resultado.parametros[CLAVE_ETIQUETA]


@pytest.mark.asyncio
async def test_el_simulado_recorre_la_misma_traduccion_que_el_adaptador_real() -> None:
    """Un `name_status` que Meta no documenta llega a `ATENCION` también acá.

    Es exactamente el punto del simulado: un bug de mapeo aparece en una laptop y no el
    día que se conecta el primer número real.
    """
    simulado = WhatsAppSimulado(Entorno.TEST)

    resultado = await simulado.verificar(
        FAKE_TOKEN_FOR_TESTS, {PARAMETRO_NAME_STATUS: "ALGO_QUE_META_INVENTO"}
    )

    assert resultado.estado is EstadoDeConexion.ATENCION


@pytest.mark.asyncio
async def test_una_linea_en_rojo_tambien_se_puede_simular() -> None:
    simulado = WhatsAppSimulado(Entorno.TEST)

    resultado = await simulado.verificar(
        FAKE_TOKEN_FOR_TESTS,
        {PARAMETRO_NAME_STATUS: "APPROVED", PARAMETRO_CALIDAD: "RED"},
    )

    assert resultado.estado is EstadoDeConexion.ATENCION


@pytest.mark.asyncio
async def test_el_simulado_exige_los_mismos_tres_campos_que_el_real() -> None:
    """Si aceptara cualquier cosa, un campo faltante del formulario llegaría a produccion."""
    simulado = WhatsAppSimulado(Entorno.TEST)

    with pytest.raises(ConexionRechazada):
        await simulado.conectar(MaterialDeConexion(contenido=FAKE_TOKEN_FOR_TESTS, parametros={}))


@pytest.mark.asyncio
async def test_el_simulado_rechaza_una_credencial_vacia() -> None:
    simulado = WhatsAppSimulado(Entorno.TEST)

    with pytest.raises(ConexionRechazada):
        await simulado.conectar(MaterialDeConexion(contenido=b"  ", parametros=IDENTIFICADORES))


@pytest.mark.asyncio
async def test_un_numero_rechazado_por_meta_tampoco_se_guarda_en_el_simulado() -> None:
    simulado = WhatsAppSimulado(Entorno.TEST)

    with pytest.raises(ConexionRechazada):
        await simulado.conectar(_material(**{PARAMETRO_NAME_STATUS: "DECLINED"}))
