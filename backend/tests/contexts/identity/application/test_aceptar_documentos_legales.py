"""Accepting a new version in force from inside the session (HU-E1-03 RN-03, HU-E1-08 RN-05).

Case 28 of the plan, and the unit side of cases 29 and 30.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from cheatsheet.contexts.identity.application.aceptaciones import (
    AceptarDocumentosLegales,
    DocumentoAceptado,
)
from cheatsheet.contexts.identity.application.errors import (
    PermisoDenegado,
    VersionLegalDesactualizada,
)
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.legal import AceptacionLegal, DocumentoLegal
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

from tests.conftest import INSTANTE_FIJO
from tests.contexts.identity.conftest import (
    VERSION_DE_PRIVACIDAD,
    VERSION_DE_TERMINOS,
    RepositorioAceptacionEnMemoria,
)

pytestmark = pytest.mark.asyncio

TERMINOS_NUEVOS = DocumentoAceptado(DocumentoLegal.TERMINOS, VERSION_DE_TERMINOS)
PRIVACIDAD_NUEVA = DocumentoAceptado(DocumentoLegal.PRIVACIDAD, VERSION_DE_PRIVACIDAD)


def _caso(empresas, aceptaciones, registrador) -> AceptarDocumentosLegales:
    return AceptarDocumentosLegales(
        empresas=empresas, aceptaciones=aceptaciones, registrador=registrador
    )


async def _empresa_con_terminos(empresas, version: str) -> EmpresaId:
    empresa = Empresa(id=EmpresaId(uuid4()))
    empresa.aceptar_terminos(version, INSTANTE_FIJO)
    await empresas.agregar(empresa)
    return empresa.id


async def _aceptar(
    caso: AceptarDocumentosLegales,
    empresa_id: EmpresaId,
    rol: RolUsuario,
    *documentos: DocumentoAceptado,
    usuario_id: UsuarioId | None = None,
) -> UsuarioId:
    usuario_id = usuario_id or UsuarioId(uuid4())
    await caso.ejecutar(
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        rol=rol,
        documentos=documentos,
        ahora=INSTANTE_FIJO,
        direccion_ip="203.0.113.7",
    )
    return usuario_id


def _acciones(publicador) -> list[str]:
    return [e.accion for e in publicador.eventos if isinstance(e, EventoAuditable)]


async def test_un_administrador_acepta_los_terminos_nuevos_en_nombre_de_la_empresa(
    empresas, aceptaciones, registrador, publicador
):
    empresa_id = await _empresa_con_terminos(empresas, "1.0")

    usuario_id = await _aceptar(
        _caso(empresas, aceptaciones, registrador),
        empresa_id,
        RolUsuario.ADMINISTRADOR,
        TERMINOS_NUEVOS,
    )

    guardada = await empresas.buscar_por_id(empresa_id)
    assert guardada is not None
    assert guardada.terminos is not None
    assert guardada.terminos.version == VERSION_DE_TERMINOS
    assert guardada.debe_reaceptar_terminos(VERSION_DE_TERMINOS) is False
    [fila] = aceptaciones.aceptaciones
    assert (fila.documento, fila.version, fila.usuario_id) == (
        DocumentoLegal.TERMINOS,
        VERSION_DE_TERMINOS,
        usuario_id,
    )
    [evento] = publicador.eventos
    assert isinstance(evento, EventoAuditable)
    assert evento.accion == "aceptar_terminos"
    assert evento.direccion_ip == "203.0.113.7"
    assert evento.entidad_afectada == f"Empresa:{empresa_id} terminos {VERSION_DE_TERMINOS}"


async def test_un_operador_no_puede_aceptar_los_terminos_y_no_se_escribe_nada(
    empresas, aceptaciones, registrador, publicador
):
    """Case 28. The privacy policy in the same request is not recorded either: all or nothing."""
    empresa_id = await _empresa_con_terminos(empresas, "1.0")

    with pytest.raises(PermisoDenegado):
        await _aceptar(
            _caso(empresas, aceptaciones, registrador),
            empresa_id,
            RolUsuario.OPERADOR,
            PRIVACIDAD_NUEVA,
            TERMINOS_NUEVOS,
        )

    assert not aceptaciones.aceptaciones
    assert not publicador.eventos
    guardada = await empresas.buscar_por_id(empresa_id)
    assert guardada is not None
    assert guardada.terminos is not None
    assert guardada.terminos.version == "1.0"


@pytest.mark.parametrize("rol", list(RolUsuario))
async def test_cualquier_rol_acepta_su_privacidad(
    rol, empresas, aceptaciones, registrador, publicador
):
    empresa_id = await _empresa_con_terminos(empresas, VERSION_DE_TERMINOS)

    usuario_id = await _aceptar(
        _caso(empresas, aceptaciones, registrador), empresa_id, rol, PRIVACIDAD_NUEVA
    )

    [fila] = aceptaciones.aceptaciones
    assert (fila.documento, fila.version, fila.usuario_id) == (
        DocumentoLegal.PRIVACIDAD,
        VERSION_DE_PRIVACIDAD,
        usuario_id,
    )
    assert _acciones(publicador) == ["aceptar_politica_de_privacidad"]


@pytest.mark.parametrize(
    "documento",
    [
        DocumentoAceptado(DocumentoLegal.TERMINOS, "1.0"),
        DocumentoAceptado(DocumentoLegal.TERMINOS, "2.0"),
        DocumentoAceptado(DocumentoLegal.PRIVACIDAD, "9.9"),
    ],
)
async def test_solo_se_acepta_la_version_vigente_hoy(
    documento, empresas, aceptaciones, registrador, publicador
):
    """An old version, one that is not in force yet, and one that never existed: all 409."""
    empresa_id = await _empresa_con_terminos(empresas, "1.0")

    with pytest.raises(VersionLegalDesactualizada):
        await _aceptar(
            _caso(empresas, aceptaciones, registrador),
            empresa_id,
            RolUsuario.ADMINISTRADOR,
            documento,
        )

    assert not aceptaciones.aceptaciones
    assert not publicador.eventos


async def test_aceptar_dos_veces_la_misma_version_no_duplica_la_fila_ni_el_evento(
    empresas, aceptaciones, registrador, publicador
):
    """Case 29, unit side: a double click, or a retry after a lost response."""
    empresa_id = await _empresa_con_terminos(empresas, "1.0")
    caso = _caso(empresas, aceptaciones, registrador)
    usuario_id = await _aceptar(
        caso, empresa_id, RolUsuario.ADMINISTRADOR, TERMINOS_NUEVOS, PRIVACIDAD_NUEVA
    )

    await _aceptar(
        caso,
        empresa_id,
        RolUsuario.ADMINISTRADOR,
        TERMINOS_NUEVOS,
        PRIVACIDAD_NUEVA,
        usuario_id=usuario_id,
    )

    assert len(aceptaciones.aceptaciones) == 2
    assert sorted(_acciones(publicador)) == [
        "aceptar_politica_de_privacidad",
        "aceptar_terminos",
    ]


async def test_los_terminos_que_otro_administrador_ya_acepto_no_se_vuelven_a_registrar(
    empresas, aceptaciones, registrador, publicador
):
    """The terms are the company's: the second Administrador finds them accepted."""
    empresa_id = await _empresa_con_terminos(empresas, "1.0")
    caso = _caso(empresas, aceptaciones, registrador)
    await _aceptar(caso, empresa_id, RolUsuario.ADMINISTRADOR, TERMINOS_NUEVOS)

    await _aceptar(caso, empresa_id, RolUsuario.ADMINISTRADOR, TERMINOS_NUEVOS)

    assert len(aceptaciones.aceptaciones) == 1
    assert _acciones(publicador) == ["aceptar_terminos"]


async def test_la_aceptacion_anterior_sigue_registrada_despues_de_aceptar_la_nueva(
    empresas, aceptaciones, registrador, publicador
):
    """Case 30: history. Accepting 1.1 adds a row; the row of 1.0 stays."""
    empresa_id = await _empresa_con_terminos(empresas, "1.0")
    usuario_id = UsuarioId(uuid4())
    await aceptaciones.agregar(
        AceptacionLegal.registrar(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            documento=DocumentoLegal.TERMINOS,
            version="1.0",
            fecha_aceptacion=INSTANTE_FIJO,
        )
    )

    await _aceptar(
        _caso(empresas, aceptaciones, registrador),
        empresa_id,
        RolUsuario.ADMINISTRADOR,
        TERMINOS_NUEVOS,
        usuario_id=usuario_id,
    )

    assert sorted(a.version for a in aceptaciones.aceptaciones) == ["1.0", "1.1"]


async def test_si_la_base_dice_que_la_fila_ya_estaba_no_se_publica_otro_evento(
    empresas, registrador, publicador
):
    """Two requests racing: both pass the check, the table keeps one row, only one event."""

    class AceptacionesConCarrera(RepositorioAceptacionEnMemoria):
        async def acepto(self, *_: object) -> bool:
            return False  # the other request has not committed yet when this one looks

        async def agregar(self, *_: object) -> bool:
            return False  # ...and has when this one inserts: `ON CONFLICT DO NOTHING`

    empresa_id = await _empresa_con_terminos(empresas, VERSION_DE_TERMINOS)
    aceptaciones = AceptacionesConCarrera()
    registrador._aceptaciones = aceptaciones

    await _aceptar(
        _caso(empresas, aceptaciones, registrador),
        empresa_id,
        RolUsuario.OPERADOR,
        PRIVACIDAD_NUEVA,
    )

    assert not publicador.eventos


async def test_una_lista_vacia_es_una_entrada_invalida(empresas, aceptaciones, registrador):
    empresa_id = await _empresa_con_terminos(empresas, "1.0")

    with pytest.raises(EntradaInvalida):
        await _aceptar(
            _caso(empresas, aceptaciones, registrador), empresa_id, RolUsuario.ADMINISTRADOR
        )


async def test_una_empresa_inexistente_falla_al_aceptar_terminos(
    empresas, aceptaciones, registrador, publicador
):
    with pytest.raises(InvarianteViolada):
        await _aceptar(
            _caso(empresas, aceptaciones, registrador),
            EmpresaId(uuid4()),
            RolUsuario.ADMINISTRADOR,
            TERMINOS_NUEVOS,
        )

    assert not aceptaciones.aceptaciones


@pytest.mark.parametrize(
    "orden", [(TERMINOS_NUEVOS, PRIVACIDAD_NUEVA), (PRIVACIDAD_NUEVA, TERMINOS_NUEVOS)]
)
async def test_el_orden_de_escritura_no_depende_del_orden_en_que_llegan_los_documentos(
    empresas, aceptaciones, registrador, orden
):
    """Two concurrent requests with opposite orders would otherwise lock in opposite orders."""
    empresa_id = await _empresa_con_terminos(empresas, "1.0")
    caso = _caso(empresas, aceptaciones, registrador)

    await _aceptar(caso, empresa_id, RolUsuario.ADMINISTRADOR, *orden)

    assert [a.documento for a in aceptaciones.aceptaciones] == [
        DocumentoLegal.PRIVACIDAD,
        DocumentoLegal.TERMINOS,
    ]
