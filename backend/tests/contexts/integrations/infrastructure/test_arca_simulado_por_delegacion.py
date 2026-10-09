"""El simulador de ARCA con el modelo de delegación (ADR-0014)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import MaterialDeConexion
from cheatsheet.contexts.integrations.application.ticket import desempaquetar
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.domain.valores import CLAVE_CUIT, EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.arca.simulado import (
    PREFIJO_SIN_DELEGACION,
    ArcaSimuladoPorDelegacion,
)
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.clock import RelojFijo

from tests.conftest import INSTANTE_FIJO

pytestmark = pytest.mark.asyncio


def _simulado() -> ArcaSimuladoPorDelegacion:
    return ArcaSimuladoPorDelegacion(
        entorno=Entorno.LOCAL, reloj=RelojFijo(INSTANTE_FIJO), aviso=timedelta(days=30)
    )


def _material(cuit: str) -> MaterialDeConexion:
    return MaterialDeConexion(contenido=cuit.encode(), parametros={}, efimeros={})


async def test_una_cuit_comun_queda_delegada() -> None:
    resultado = await _simulado().conectar(_material("30000000015"))

    assert resultado.parametros[CLAVE_CUIT] == "30000000015"


async def test_la_cuit_reservada_simula_una_empresa_que_no_delego() -> None:
    with pytest.raises(ConexionRechazada, match="no registra"):
        await _simulado().conectar(_material(f"{PREFIJO_SIN_DELEGACION}001"))


async def test_el_ticket_simulado_se_puede_desempaquetar_sin_certificado() -> None:
    """No hay certificado de plataforma en un despliegue simulado."""
    ticket = await _simulado().emitir(b"", ServicioDeArca.WSFE)

    token, sign = desempaquetar(ticket.contenido)
    assert token
    assert sign


async def test_la_verificacion_simulada_conserva_el_estado() -> None:
    resultado = await _simulado().verificar(b"marca", {CLAVE_CUIT: "30000000015"})

    assert resultado.estado is EstadoDeConexion.CONECTADO


def test_no_se_construye_en_produccion() -> None:
    with pytest.raises(RuntimeError):
        ArcaSimuladoPorDelegacion(
            entorno=Entorno.PRODUCTION, reloj=RelojFijo(INSTANTE_FIJO), aviso=timedelta(days=30)
        )
