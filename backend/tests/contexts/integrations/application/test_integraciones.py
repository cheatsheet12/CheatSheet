"""HU-E2-05 and the connection path — cases 6 to 9, 12, 13, 16 and 17 of the plan."""

from __future__ import annotations

import pytest
from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    PermisoDenegado,
    ProveedorNoDisponible,
    SistemaNoConfigurable,
)
from cheatsheet.contexts.integrations.application.integraciones import (
    ConectarIntegracion,
    ListarIntegraciones,
    VerificarConexiones,
)
from cheatsheet.contexts.integrations.application.ports import ResultadoDeVerificacion
from cheatsheet.contexts.integrations.domain.valores import (
    SISTEMAS_EN_PANTALLA,
    Ambiente,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.registro import ParDeAdaptadores
from cheatsheet.shared.auditoria import EventoAuditable, Modulo
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario

from tests.conftest import INSTANTE_FIJO
from tests.contexts.integrations.conftest import (
    CifradoFalso,
    ConectorProgramado,
    PublicadorFalso,
    RegistroFalso,
    RepositorioIntegracionesEnMemoria,
    VerificadorProgramado,
    configuracion_conectada,
)

pytestmark = pytest.mark.asyncio

RELOJ = RelojFijo(INSTANTE_FIJO)


def _registro(
    **pares: tuple[VerificadorProgramado | None, ConectorProgramado | None],
) -> RegistroFalso:
    armado = {}
    for nombre, (verificador, conector) in pares.items():
        armado[SistemaExterno(nombre)] = ParDeAdaptadores(
            conector=conector or ConectorProgramado(),
            verificador=verificador or VerificadorProgramado(),
        )
    return RegistroFalso(armado)


def _verificar(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    registro: RegistroFalso,
    publicador: PublicadorFalso,
    *,
    timeout: int = 1,
) -> VerificarConexiones:
    return VerificarConexiones(
        integraciones=integraciones,
        cifrado=cifrado,
        adaptadores=registro,
        publicador=publicador,
        reloj=RELOJ,
        timeout_segundos=timeout,
    )


async def test_listar_sobre_base_vacia_devuelve_las_cuatro_sin_conectar(
    integraciones: RepositorioIntegracionesEnMemoria, empresa_id: EmpresaId
) -> None:
    """The four cards come from the enum, not from the table."""
    vistas = await ListarIntegraciones(integraciones=integraciones).ejecutar(
        empresa_id=empresa_id, rol=RolUsuario.ADMINISTRADOR
    )

    assert [v.sistema for v in vistas] == list(SISTEMAS_EN_PANTALLA)
    assert all(v.estado is EstadoDeConexion.NO_CONECTADO for v in vistas)
    assert all(not v.configurada for v in vistas)


async def test_un_proveedor_lento_no_arrastra_a_los_otros(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """Case 7 — the reason `VerificarConexiones` gathers instead of awaiting in a row."""
    for sistema in (SistemaExterno.ARCA, SistemaExterno.MERCADOPAGO, SistemaExterno.WHATSAPP):
        await integraciones.agregar(configuracion_conectada(empresa_id, sistema))

    lento = VerificadorProgramado(demora=5.0)
    registro = _registro(
        ARCA=(lento, None),
        MERCADOPAGO=(VerificadorProgramado(), None),
        WHATSAPP=(VerificadorProgramado(), None),
    )

    vistas = await _verificar(integraciones, cifrado, registro, publicador).ejecutar(
        empresa_id=empresa_id, rol=RolUsuario.ADMINISTRADOR
    )

    por_sistema = {v.sistema: v for v in vistas}
    assert por_sistema[SistemaExterno.ARCA].estado is EstadoDeConexion.NO_CONECTADO
    assert "no respondio" in (por_sistema[SistemaExterno.ARCA].detalle or "")
    assert por_sistema[SistemaExterno.MERCADOPAGO].estado is EstadoDeConexion.CONECTADO
    assert por_sistema[SistemaExterno.WHATSAPP].estado is EstadoDeConexion.CONECTADO


async def test_un_proveedor_que_lanza_no_propaga_la_excepcion(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    await integraciones.agregar(configuracion_conectada(empresa_id, SistemaExterno.ARCA))
    await integraciones.agregar(configuracion_conectada(empresa_id, SistemaExterno.MERCADOPAGO))

    registro = _registro(
        ARCA=(VerificadorProgramado(excepcion=ProveedorNoDisponible("host caido")), None),
        MERCADOPAGO=(VerificadorProgramado(), None),
    )

    vistas = await _verificar(integraciones, cifrado, registro, publicador).ejecutar(
        empresa_id=empresa_id, rol=RolUsuario.OPERADOR
    )

    por_sistema = {v.sistema: v for v in vistas}
    assert por_sistema[SistemaExterno.ARCA].detalle == "host caido"
    assert por_sistema[SistemaExterno.MERCADOPAGO].estado is EstadoDeConexion.CONECTADO


async def test_la_verificacion_sella_la_marca_de_tiempo(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """HU-E2-05 RN-03."""
    await integraciones.agregar(configuracion_conectada(empresa_id, SistemaExterno.ARCA))
    registro = _registro(ARCA=(VerificadorProgramado(), None))

    vistas = await _verificar(integraciones, cifrado, registro, publicador).ejecutar(
        empresa_id=empresa_id, rol=RolUsuario.ADMINISTRADOR
    )

    configurada = next(v for v in vistas if v.configurada)
    assert configurada.verificado_en == INSTANTE_FIJO


async def test_el_estado_degradado_llega_con_su_detalle(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """The acceptance criterion the DER's boolean could not express (gap H9)."""
    await integraciones.agregar(configuracion_conectada(empresa_id, SistemaExterno.ARCA))
    registro = _registro(
        ARCA=(
            VerificadorProgramado(
                resultado=ResultadoDeVerificacion(EstadoDeConexion.ATENCION, "Servicio degradado")
            ),
            None,
        )
    )

    vistas = await _verificar(integraciones, cifrado, registro, publicador).ejecutar(
        empresa_id=empresa_id, rol=RolUsuario.ADMINISTRADOR
    )

    vista = next(v for v in vistas if v.sistema is SistemaExterno.ARCA)
    assert vista.estado is EstadoDeConexion.ATENCION
    assert vista.detalle == "Servicio degradado"


async def test_un_cambio_de_estado_escribe_en_la_bitacora(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """Case 10 at the application seam: the module is what HU-E12-01 filters by."""
    await integraciones.agregar(configuracion_conectada(empresa_id, SistemaExterno.ARCA))
    registro = _registro(
        ARCA=(
            VerificadorProgramado(resultado=ResultadoDeVerificacion(EstadoDeConexion.ATENCION)),
            None,
        )
    )
    usuario_id = UsuarioId(empresa_id)

    await _verificar(integraciones, cifrado, registro, publicador).ejecutar(
        empresa_id=empresa_id,
        rol=RolUsuario.ADMINISTRADOR,
        usuario_id=usuario_id,
        direccion_ip="10.0.0.1",
    )

    assert len(publicador.eventos) == 1
    evento = publicador.eventos[0]
    assert isinstance(evento, EventoAuditable)
    assert evento.modulo is Modulo.INTEGRATIONS
    assert evento.usuario_id == usuario_id
    assert evento.direccion_ip == "10.0.0.1"


async def test_una_verificacion_sin_cambios_no_escribe_en_la_bitacora(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """Otherwise the Log de Operaciones becomes a heartbeat."""
    await integraciones.agregar(configuracion_conectada(empresa_id, SistemaExterno.ARCA))
    registro = _registro(ARCA=(VerificadorProgramado(), None))

    await _verificar(integraciones, cifrado, registro, publicador).ejecutar(
        empresa_id=empresa_id, rol=RolUsuario.ADMINISTRADOR
    )

    assert publicador.eventos == []


@pytest.mark.parametrize("rol", [RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR])
async def test_administrador_y_operador_pueden_verificar(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
    rol: RolUsuario,
) -> None:
    """HU-E2-05 names both actors."""
    vistas = await _verificar(integraciones, cifrado, _registro(), publicador).ejecutar(
        empresa_id=empresa_id, rol=rol
    )

    assert len(vistas) == len(SISTEMAS_EN_PANTALLA)


async def test_solo_lectura_no_puede_ver_las_integraciones(
    integraciones: RepositorioIntegracionesEnMemoria, empresa_id: EmpresaId
) -> None:
    with pytest.raises(PermisoDenegado):
        await ListarIntegraciones(integraciones=integraciones).ejecutar(
            empresa_id=empresa_id, rol=RolUsuario.SOLO_LECTURA
        )


async def test_el_operador_no_puede_conectar(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """Reading is shared; writing a credential is the Administrator's."""
    with pytest.raises(PermisoDenegado):
        await _conectar(integraciones, cifrado, publicador).ejecutar(
            empresa_id=empresa_id,
            rol=RolUsuario.OPERADOR,
            sistema=SistemaExterno.ARCA,
            contenido=b"certificado",
        )


def _conectar(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    *,
    registro: RegistroFalso | None = None,
    es_produccion: bool = False,
) -> ConectarIntegracion:
    return ConectarIntegracion(
        integraciones=integraciones,
        cifrado=cifrado,
        adaptadores=registro or _registro(ARCA=(None, None)),
        publicador=publicador,
        reloj=RELOJ,
        es_produccion=es_produccion,
    )


async def test_conectar_cifra_la_credencial_antes_de_persistirla(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    vista = await _conectar(integraciones, cifrado, publicador).ejecutar(
        empresa_id=empresa_id,
        rol=RolUsuario.ADMINISTRADOR,
        sistema=SistemaExterno.ARCA,
        contenido=b"certificado",
    )

    assert vista.estado is EstadoDeConexion.CONECTADO
    guardada = await integraciones.buscar(empresa_id, SistemaExterno.ARCA)
    assert guardada is not None
    # What is persisted went through the cipher port, not around it. The fake cipher is
    # readable on purpose; the real one has its own test.
    assert guardada.credencial.contenido == b"cifrado:certificado"


async def test_conectar_dos_veces_no_crea_una_segunda_fila(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """Case 11 — idempotency by `(empresa_id, sistema)`."""
    caso = _conectar(integraciones, cifrado, publicador)
    for contenido in (b"primera", b"segunda"):
        await caso.ejecutar(
            empresa_id=empresa_id,
            rol=RolUsuario.ADMINISTRADOR,
            sistema=SistemaExterno.ARCA,
            contenido=contenido,
        )

    assert len(integraciones.filas) == 1
    guardada = await integraciones.buscar(empresa_id, SistemaExterno.ARCA)
    assert guardada is not None
    assert guardada.credencial.contenido == b"cifrado:segunda"


async def test_el_ambiente_sale_del_despliegue_y_no_de_la_peticion(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """Decision D-b. There is no parameter for it, which is the point."""
    vista = await _conectar(integraciones, cifrado, publicador, es_produccion=True).ejecutar(
        empresa_id=empresa_id,
        rol=RolUsuario.ADMINISTRADOR,
        sistema=SistemaExterno.ARCA,
        contenido=b"certificado",
    )
    assert vista.ambiente is Ambiente.PRODUCCION

    otra = EmpresaId(empresa_id)
    vista_local = await _conectar(
        RepositorioIntegracionesEnMemoria(), cifrado, publicador, es_produccion=False
    ).ejecutar(
        empresa_id=otra,
        rol=RolUsuario.ADMINISTRADOR,
        sistema=SistemaExterno.ARCA,
        contenido=b"certificado",
    )
    assert vista_local.ambiente is Ambiente.HOMOLOGACION


async def test_un_proveedor_que_rechaza_deja_la_integracion_sin_conectar(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """HU-E2-01 RN-02: validate first, persist after. Nothing is written."""
    registro = _registro(
        ARCA=(None, ConectorProgramado(excepcion=ProveedorNoDisponible("credencial invalida")))
    )

    with pytest.raises(ConexionRechazada, match="credencial invalida"):
        await _conectar(integraciones, cifrado, publicador, registro=registro).ejecutar(
            empresa_id=empresa_id,
            rol=RolUsuario.ADMINISTRADOR,
            sistema=SistemaExterno.ARCA,
            contenido=b"mala",
        )

    assert integraciones.filas == {}
    assert publicador.eventos == []


async def test_un_sistema_sin_conector_registrado_es_rechazado(
    integraciones: RepositorioIntegracionesEnMemoria,
    cifrado: CifradoFalso,
    publicador: PublicadorFalso,
    empresa_id: EmpresaId,
) -> None:
    """Google Sheets is on the screen but its connection is epic 4."""
    with pytest.raises(SistemaNoConfigurable):
        await _conectar(integraciones, cifrado, publicador).ejecutar(
            empresa_id=empresa_id,
            rol=RolUsuario.ADMINISTRADOR,
            sistema=SistemaExterno.GOOGLE_SHEETS,
            contenido=b"x",
        )
