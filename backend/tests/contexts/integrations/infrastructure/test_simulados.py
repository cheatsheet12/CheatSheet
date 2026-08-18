"""The stand-ins, and the guard that keeps them out of production — case 16."""

from __future__ import annotations

import pytest
from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.application.ports import MaterialDeConexion
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion, SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.registro import (
    SISTEMAS_DEL_EPICO,
    RegistroDeAdaptadores,
)
from cheatsheet.contexts.integrations.infrastructure.simulados import (
    PARAMETRO_DETALLE,
    PARAMETRO_ESTADO,
    PARAMETRO_FALLA,
    ConectorSimulado,
    VerificadorSimulado,
)
from cheatsheet.platform.settings import Entorno

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("clase", [ConectorSimulado, VerificadorSimulado])
async def test_un_simulado_no_puede_construirse_en_produccion(clase: type) -> None:
    """Not a warning: a `RuntimeError`, before the process can serve a request."""
    with pytest.raises(RuntimeError, match="produccion"):
        clase(sistema=SistemaExterno.ARCA, entorno=Entorno.PRODUCTION)


async def test_el_registro_simulado_tampoco() -> None:
    with pytest.raises(RuntimeError, match="produccion"):
        RegistroDeAdaptadores.simulado(Entorno.PRODUCTION)


async def test_el_registro_cubre_los_tres_sistemas_del_epico() -> None:
    registro = RegistroDeAdaptadores.simulado(Entorno.TEST)

    for sistema in SISTEMAS_DEL_EPICO:
        assert registro.conector(sistema) is not None
        assert registro.verificador(sistema) is not None
    # Epic 4's, deliberately absent.
    assert registro.conector(SistemaExterno.GOOGLE_SHEETS) is None


async def test_el_conector_simulado_devuelve_lo_que_recibe() -> None:
    conector = ConectorSimulado(sistema=SistemaExterno.ARCA, entorno=Entorno.TEST)

    devuelto = await conector.conectar(MaterialDeConexion(contenido=b"cert", parametros={}))

    assert devuelto == b"cert"


async def test_el_conector_simulado_rechaza_una_credencial_vacia() -> None:
    conector = ConectorSimulado(sistema=SistemaExterno.ARCA, entorno=Entorno.TEST)

    with pytest.raises(ProveedorNoDisponible):
        await conector.conectar(MaterialDeConexion(contenido=b"", parametros={}))


async def test_el_verificador_simulado_reporta_el_estado_pedido() -> None:
    """So the three states of RN-02 are reachable from the running app, not only a test."""
    verificador = VerificadorSimulado(sistema=SistemaExterno.ARCA, entorno=Entorno.TEST)

    resultado = await verificador.verificar(
        b"x", {PARAMETRO_ESTADO: "ATENCION", PARAMETRO_DETALLE: "degradado"}
    )

    assert resultado.estado is EstadoDeConexion.ATENCION
    assert resultado.detalle == "degradado"


async def test_el_verificador_simulado_puede_fallar_a_pedido() -> None:
    verificador = VerificadorSimulado(sistema=SistemaExterno.ARCA, entorno=Entorno.TEST)

    with pytest.raises(ProveedorNoDisponible):
        await verificador.verificar(b"x", {PARAMETRO_FALLA: True})


async def test_sin_parametros_el_verificador_reporta_conectado() -> None:
    verificador = VerificadorSimulado(sistema=SistemaExterno.ARCA, entorno=Entorno.TEST)

    resultado = await verificador.verificar(b"x", {})

    assert resultado.estado is EstadoDeConexion.CONECTADO
