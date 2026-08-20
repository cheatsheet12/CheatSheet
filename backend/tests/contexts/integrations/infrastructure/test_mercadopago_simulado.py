"""El doble de MercadoPago — caso 22 del plan, y la vuelta completa sin sandbox.

Lo que justifica que exista es que **recorre el redirect**: la mitad más frágil de la
unidad —irse de la app y volver con un código— queda ejercitada en una laptop. Y los
payloads fabricados pasan por el ACL real, así que la traducción que decide qué se guarda
es la misma acá y en producción.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    PedidoDeAutorizacion,
)
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_ETIQUETA,
    CLAVE_VENCIMIENTO,
    CLAVE_VERIFICADOR,
    EstadoDeConexion,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.mapeo import (
    CLAVE_CUENTA_REAL,
    desempaquetar,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.simulado import (
    CODIGO_CUENTA_REAL,
    CODIGO_RECHAZADO,
    CODIGO_REVOCABLE,
    PREFIJO_SIMULADO,
    MercadoPagoSimulado,
)
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.clock import RelojFijo

from tests.conftest import INSTANTE_FIJO

pytestmark = pytest.mark.asyncio

RETORNO = "http://localhost:3000/configuracion/integraciones"


def _simulado(entorno: Entorno = Entorno.TEST) -> MercadoPagoSimulado:
    return MercadoPagoSimulado(
        entorno=entorno, reloj=RelojFijo(INSTANTE_FIJO), redirect_uri=RETORNO
    )


def _material(codigo: str) -> MaterialDeConexion:
    return MaterialDeConexion(
        contenido=codigo.encode(), parametros={}, efimeros={CLAVE_VERIFICADOR: "verificador"}
    )


async def test_construirlo_en_produccion_revienta_al_arrancar() -> None:
    """Caso 22. Una empresa que cree tener MercadoPago conectado cree que puede cobrar."""
    with pytest.raises(RuntimeError, match="produccion"):
        _simulado(Entorno.PRODUCTION)


async def test_la_url_simulada_vuelve_al_panel_con_un_codigo_y_el_estado() -> None:
    """Es lo que hace que el redirect entero se pueda recorrer sin una app de sandbox."""
    url = _simulado().url_de_autorizacion(
        PedidoDeAutorizacion(estado="el-estado", desafio="el-desafio")
    )

    partes = urlparse(url)
    consulta = parse_qs(partes.query)
    assert url.startswith(RETORNO)
    assert consulta["state"][0] == "el-estado"
    assert consulta["code"][0].startswith(PREFIJO_SIMULADO)


async def test_una_conexion_normal_deja_los_dos_tokens_y_una_etiqueta() -> None:
    resultado = await _simulado().conectar(_material("SIMULADO-loquesea"))

    acceso, refresco = desempaquetar(resultado.credencial)
    assert acceso.startswith(PREFIJO_SIMULADO)
    assert refresco.startswith(PREFIJO_SIMULADO)
    assert resultado.estado is EstadoDeConexion.CONECTADO
    assert resultado.parametros[CLAVE_ETIQUETA]
    assert resultado.parametros[CLAVE_VENCIMIENTO] > INSTANTE_FIJO.isoformat()


async def test_el_codigo_reservado_de_rechazo_se_comporta_como_invalid_grant() -> None:
    with pytest.raises(ConexionRechazada, match="Volve a iniciar"):
        await _simulado().conectar(_material(CODIGO_RECHAZADO))


async def test_el_codigo_de_cuenta_real_choca_contra_el_ambiente() -> None:
    """Permite demostrar D-c sin tener una cuenta real de MercadoPago."""
    with pytest.raises(ConexionRechazada, match="cuenta de prueba"):
        await _simulado().conectar(_material(CODIGO_CUENTA_REAL))


async def test_sin_verificador_el_simulado_tambien_rechaza() -> None:
    """Si no, el camino de PKCE quedaría sin ejercitar justo donde más se usa."""
    with pytest.raises(ConexionRechazada):
        await _simulado().conectar(MaterialDeConexion(contenido=b"SIMULADO-x", parametros={}))


async def test_el_codigo_revocable_conecta_y_despues_falla_al_renovar() -> None:
    """RN-03 demostrable sin esperar seis meses."""
    simulado = _simulado()
    conectada = await simulado.conectar(_material(CODIGO_REVOCABLE))

    with pytest.raises(ConexionRechazada, match="revocado"):
        await simulado.renovar(conectada.credencial)


async def test_una_renovacion_normal_devuelve_un_par_nuevo() -> None:
    simulado = _simulado()
    conectada = await simulado.conectar(_material("SIMULADO-x"))

    renovada = await simulado.renovar(conectada.credencial)

    assert renovada.credencial != conectada.credencial
    assert renovada.estado is EstadoDeConexion.CONECTADO


async def test_la_verificacion_respeta_el_ambiente_guardado() -> None:
    simulado = _simulado()
    conectada = await simulado.conectar(_material("SIMULADO-x"))

    resultado = await simulado.verificar(conectada.credencial, {CLAVE_CUENTA_REAL: True})

    # Cuenta real fuera de produccion: se marca, no se desconecta.
    assert resultado.estado is EstadoDeConexion.ATENCION
