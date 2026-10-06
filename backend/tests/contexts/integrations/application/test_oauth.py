"""Las dos mitades del OAuth2 — y la regla que sostiene la unidad.

Lo que se prueba acá no es que la URL se arme: es **que un `state` valga una sola vez y
sólo para la empresa que lo pidió**. Si eso se cae, quien consiga que un Administrador
abra un link engancha *su* cuenta de MercadoPago a la empresa ajena, y todos los cobros
del épico 6 caen en la cuenta equivocada.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.errors import (
    AutorizacionInvalida,
    PermisoDenegado,
    SistemaNoConfigurable,
)
from cheatsheet.contexts.integrations.application.integraciones import ConectarIntegracion
from cheatsheet.contexts.integrations.application.oauth import (
    CompletarAutorizacion,
    IniciarAutorizacion,
    desafio_de,
)
from cheatsheet.contexts.integrations.application.ports import AutorizacionPendiente
from cheatsheet.contexts.integrations.domain.valores import CLAVE_VERIFICADOR, SistemaExterno
from cheatsheet.contexts.integrations.infrastructure.autorizaciones import (
    MemoriaDeAutorizacionEnMemoria,
)
from cheatsheet.contexts.integrations.infrastructure.registro import ParDeAdaptadores
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.roles import RolUsuario

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest import (
    AutorizacionProgramada,
    CifradoFalso,
    ConectorProgramado,
    PublicadorFalso,
    RegistroFalso,
    RepositorioIntegracionesEnMemoria,
    VerificadorProgramado,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
OTRA_EMPRESA = EmpresaId(uuid4())


def _registro(*, con_autorizacion: bool = True) -> tuple[RegistroFalso, ConectorProgramado]:
    conector = ConectorProgramado()
    par = ParDeAdaptadores(
        conector=conector,
        verificador=VerificadorProgramado(),
        autorizacion=AutorizacionProgramada() if con_autorizacion else None,
    )
    return RegistroFalso({SistemaExterno.MERCADOPAGO: par}), conector


def _iniciar(
    registro: RegistroFalso, memoria: MemoriaDeAutorizacionEnMemoria
) -> IniciarAutorizacion:
    return IniciarAutorizacion(adaptadores=registro, memoria=memoria, ttl_segundos=600)


def _completar(
    registro: RegistroFalso, memoria: MemoriaDeAutorizacionEnMemoria
) -> CompletarAutorizacion:
    return CompletarAutorizacion(
        memoria=memoria,
        conectar=ConectarIntegracion(
            integraciones=RepositorioIntegracionesEnMemoria(),
            cifrado=CifradoFalso(),
            adaptadores=registro,
            publicador=PublicadorFalso(),
            reloj=RelojFijo(INSTANTE_FIJO),
            es_produccion=False,
        ),
    )


async def test_la_url_lleva_el_estado_y_el_desafio_pkce() -> None:
    """Caso 1. El verificador **no** viaja: eso es lo que PKCE existe para evitar."""
    registro, _ = _registro()
    memoria = MemoriaDeAutorizacionEnMemoria()

    inicio = await _iniciar(registro, memoria).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.ADMINISTRADOR, sistema=SistemaExterno.MERCADOPAGO
    )

    consulta = parse_qs(urlparse(inicio.url).query)
    estado = consulta["state"][0]
    guardada = await memoria.consumir(estado)
    assert guardada is not None
    assert consulta["code_challenge"][0] == desafio_de(guardada.verificador)
    assert guardada.verificador not in inicio.url


async def test_el_desafio_pkce_no_lleva_relleno() -> None:
    """RFC 7636 §4.2: con `=` al final el proveedor calcula otro desafio y rechaza el canje.

    Y rechaza con un mensaje sobre el código, no sobre el relleno — así que si esto se
    rompe, se rompe en el lugar más difícil de diagnosticar.
    """
    desafio = desafio_de("un-verificador-cualquiera")

    assert not desafio.endswith("=")
    assert desafio == desafio_de("un-verificador-cualquiera")


async def test_un_operador_no_puede_iniciar_la_conexion() -> None:
    """Caso 2. Mirar la pantalla es de HU-E2-05; conectar una cuenta que cobra, no."""
    registro, _ = _registro()

    with pytest.raises(PermisoDenegado):
        await _iniciar(registro, MemoriaDeAutorizacionEnMemoria()).ejecutar(
            empresa_id=EMPRESA, rol=RolUsuario.OPERADOR, sistema=SistemaExterno.MERCADOPAGO
        )


async def test_un_sistema_que_no_usa_oauth_lo_dice() -> None:
    registro, _ = _registro(con_autorizacion=False)

    with pytest.raises(SistemaNoConfigurable, match="OAuth2"):
        await _iniciar(registro, MemoriaDeAutorizacionEnMemoria()).ejecutar(
            empresa_id=EMPRESA, rol=RolUsuario.ADMINISTRADOR, sistema=SistemaExterno.MERCADOPAGO
        )


async def test_el_estado_se_consume_una_sola_vez() -> None:
    """Caso 3. El segundo canje con el mismo `state` no conecta nada."""
    registro, conector = _registro()
    memoria = MemoriaDeAutorizacionEnMemoria()
    inicio = await _iniciar(registro, memoria).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.ADMINISTRADOR, sistema=SistemaExterno.MERCADOPAGO
    )
    estado = parse_qs(urlparse(inicio.url).query)["state"][0]
    completar = _completar(registro, memoria)

    await completar.ejecutar(
        empresa_id=EMPRESA,
        rol=RolUsuario.ADMINISTRADOR,
        sistema=SistemaExterno.MERCADOPAGO,
        codigo="codigo-1",
        estado=estado,
    )

    with pytest.raises(AutorizacionInvalida, match="vencio o ya fue usada"):
        await completar.ejecutar(
            empresa_id=EMPRESA,
            rol=RolUsuario.ADMINISTRADOR,
            sistema=SistemaExterno.MERCADOPAGO,
            codigo="codigo-2",
            estado=estado,
        )
    assert conector.recibidos == 1


async def test_el_estado_de_una_empresa_no_sirve_para_otra() -> None:
    """Caso 4. El test que más importa de este archivo.

    Sin esto, un link armado por un tercero conecta **su** cuenta de MercadoPago a la
    empresa que abrió el link, y el épico 6 cobra en la cuenta equivocada.
    """
    registro, conector = _registro()
    memoria = MemoriaDeAutorizacionEnMemoria()
    await memoria.guardar(
        "estado-de-la-otra",
        AutorizacionPendiente(
            empresa_id=OTRA_EMPRESA,
            sistema=SistemaExterno.MERCADOPAGO,
            verificador="verificador",
        ),
        600,
    )

    with pytest.raises(AutorizacionInvalida, match="no corresponde"):
        await _completar(registro, memoria).ejecutar(
            empresa_id=EMPRESA,
            rol=RolUsuario.ADMINISTRADOR,
            sistema=SistemaExterno.MERCADOPAGO,
            codigo="codigo",
            estado="estado-de-la-otra",
        )
    assert conector.recibidos == 0


async def test_un_estado_desconocido_no_llama_al_proveedor() -> None:
    """Caso 5. Vencido o inventado: la misma respuesta, y ninguna llamada."""
    registro, conector = _registro()

    with pytest.raises(AutorizacionInvalida):
        await _completar(registro, MemoriaDeAutorizacionEnMemoria()).ejecutar(
            empresa_id=EMPRESA,
            rol=RolUsuario.ADMINISTRADOR,
            sistema=SistemaExterno.MERCADOPAGO,
            codigo="codigo",
            estado="nunca-emitido",
        )
    assert conector.recibidos == 0


async def test_un_operador_no_quema_un_estado_valido() -> None:
    """El permiso se chequea antes de gastar un token de un solo uso.

    Si no, un pedido que nunca iba a permitirse obliga al Administrador a empezar de cero.
    """
    registro, _ = _registro()
    memoria = MemoriaDeAutorizacionEnMemoria()
    inicio = await _iniciar(registro, memoria).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.ADMINISTRADOR, sistema=SistemaExterno.MERCADOPAGO
    )
    estado = parse_qs(urlparse(inicio.url).query)["state"][0]

    with pytest.raises(PermisoDenegado):
        await _completar(registro, memoria).ejecutar(
            empresa_id=EMPRESA,
            rol=RolUsuario.OPERADOR,
            sistema=SistemaExterno.MERCADOPAGO,
            codigo="codigo",
            estado=estado,
        )

    assert await memoria.consumir(estado) is not None


async def test_el_verificador_llega_al_adaptador_y_no_se_guarda() -> None:
    """Viaja por `efimeros`, que es justamente lo que no sobrevive al handshake.

    Guardarlo dejaría un secreto de un solo uso en una columna JSONB para siempre.
    """
    registro, conector = _registro()
    memoria = MemoriaDeAutorizacionEnMemoria()
    inicio = await _iniciar(registro, memoria).ejecutar(
        empresa_id=EMPRESA, rol=RolUsuario.ADMINISTRADOR, sistema=SistemaExterno.MERCADOPAGO
    )
    estado = parse_qs(urlparse(inicio.url).query)["state"][0]

    vista = await _completar(registro, memoria).ejecutar(
        empresa_id=EMPRESA,
        rol=RolUsuario.ADMINISTRADOR,
        sistema=SistemaExterno.MERCADOPAGO,
        codigo="codigo",
        estado=estado,
    )

    assert conector.efimeros_recibidos.get(CLAVE_VERIFICADOR)
    assert vista.sistema is SistemaExterno.MERCADOPAGO


async def test_una_autorizacion_sin_codigo_es_invalida() -> None:
    registro, _ = _registro()

    with pytest.raises(AutorizacionInvalida, match="sin codigo"):
        await _completar(registro, MemoriaDeAutorizacionEnMemoria()).ejecutar(
            empresa_id=EMPRESA,
            rol=RolUsuario.ADMINISTRADOR,
            sistema=SistemaExterno.MERCADOPAGO,
            codigo="   ",
            estado="cualquiera",
        )


async def test_una_entrada_ilegible_en_la_memoria_se_trata_como_ausente() -> None:
    """El adaptador de Redis puede leer basura si el formato cambió entre despliegues.

    La respuesta correcta es la misma que para un `state` vencido —«volvé a empezar»— y no
    un 500 que nadie sabe interpretar.
    """
    from cheatsheet.contexts.integrations.infrastructure.autorizaciones import _deserializar

    assert _deserializar("{no es json") is None
    assert _deserializar('{"empresa_id": "no-es-un-uuid"}') is None
