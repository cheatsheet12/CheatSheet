"""Reading the published legal documents (HU-E1-03 RN-04/05, HU-E1-08 RN-01/06)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

import pytest
from cheatsheet.contexts.identity.application.legal import (
    ConsultarDocumentoVigente,
    ConsultarVersionesVigentes,
)
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal, VersionDeDocumento
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.errors import InvarianteViolada

pytestmark = pytest.mark.asyncio


class CatalogoEnMemoria:
    """Implements `PortCatalogoLegal` without touching the disk."""

    def __init__(self, versiones: Sequence[VersionDeDocumento]) -> None:
        self._versiones = versiones

    def versiones(self) -> Sequence[VersionDeDocumento]:
        return self._versiones

    def texto(self, documento: DocumentoLegal, version: str) -> str:
        return f"## {documento.value} {version}\n"


_VERSIONES = (
    VersionDeDocumento(DocumentoLegal.PRIVACIDAD, "1.0", date(2026, 1, 1)),
    VersionDeDocumento(DocumentoLegal.PRIVACIDAD, "2.0", date(2026, 11, 1), borrador=True),
    VersionDeDocumento(DocumentoLegal.TERMINOS, "1.1", date(2026, 1, 1), borrador=True),
)


def _reloj(instante: datetime) -> RelojFijo:
    return RelojFijo(instante)


async def test_devuelve_la_version_vigente_con_su_texto_y_su_marca_de_borrador():
    caso = ConsultarDocumentoVigente(
        catalogo=CatalogoEnMemoria(_VERSIONES), reloj=_reloj(datetime(2026, 5, 1, 12, tzinfo=UTC))
    )

    publicado = await caso.ejecutar(DocumentoLegal.TERMINOS)

    assert publicado.documento is DocumentoLegal.TERMINOS
    assert publicado.version == "1.1"
    assert publicado.vigente_desde == date(2026, 1, 1)
    assert publicado.borrador is True
    assert publicado.texto == "## TERMINOS 1.1\n"


async def test_una_version_futura_todavia_no_se_publica():
    caso = ConsultarDocumentoVigente(
        catalogo=CatalogoEnMemoria(_VERSIONES), reloj=_reloj(datetime(2026, 5, 1, tzinfo=UTC))
    )

    assert (await caso.ejecutar(DocumentoLegal.PRIVACIDAD)).version == "1.0"


async def test_el_dia_se_cuenta_en_hora_argentina():
    """21:30 in Buenos Aires on Oct 31 is already Nov 1 in UTC: the new version is not yet current."""
    caso = ConsultarDocumentoVigente(
        catalogo=CatalogoEnMemoria(_VERSIONES),
        reloj=_reloj(datetime(2026, 11, 1, 0, 30, tzinfo=UTC)),
    )

    assert (await caso.ejecutar(DocumentoLegal.PRIVACIDAD)).version == "1.0"

    despues = ConsultarDocumentoVigente(
        catalogo=CatalogoEnMemoria(_VERSIONES),
        reloj=_reloj(datetime(2026, 11, 1, 3, 0, tzinfo=UTC)),
    )
    assert (await despues.ejecutar(DocumentoLegal.PRIVACIDAD)).version == "2.0"


async def test_sin_version_vigente_es_una_invariante_violada():
    caso = ConsultarDocumentoVigente(
        catalogo=CatalogoEnMemoria([_VERSIONES[1]]), reloj=_reloj(datetime(2026, 5, 1, tzinfo=UTC))
    )

    with pytest.raises(InvarianteViolada):
        await caso.ejecutar(DocumentoLegal.PRIVACIDAD)


async def test_las_versiones_vigentes_son_una_por_documento():
    caso = ConsultarVersionesVigentes(
        catalogo=CatalogoEnMemoria(_VERSIONES), reloj=_reloj(datetime(2026, 5, 1, tzinfo=UTC))
    )

    vigentes = await caso.ejecutar()

    assert vigentes.terminos.version == "1.1"
    assert vigentes.privacidad.version == "1.0"
