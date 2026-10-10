"""Reading the published legal documents (HU-E1-03 RN-04, HU-E1-08 RN-06).

Public reads: nothing here touches the database or needs a session. The catalogue is loaded
once at start-up, so answering is a lookup in memory.

"Today" is the calendar day in `America/Argentina/Buenos_Aires`, not in UTC: a version that
takes effect on the 1st must not appear three hours early for the people it is addressed to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from cheatsheet.contexts.identity.application.ports import PortCatalogoLegal
from cheatsheet.contexts.identity.domain.legal import (
    CatalogoLegal,
    DocumentoLegal,
    VersionDeDocumento,
)
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA


@dataclass(frozen=True, slots=True)
class DocumentoPublicado:
    """The current version of one document, with its text."""

    documento: DocumentoLegal
    version: str
    vigente_desde: date
    #: Still pending legal validation (HU-E1-08 RN-07).
    borrador: bool
    texto: str


@dataclass(frozen=True, slots=True)
class VersionesVigentes:
    """What a form shows and later sends back as the consent (a later slice)."""

    terminos: VersionDeDocumento
    privacidad: VersionDeDocumento


def vigente_a(
    catalogo: PortCatalogoLegal, instante: datetime, documento: DocumentoLegal
) -> VersionDeDocumento:
    """The version of `documento` in force at `instante`, reading the day in Argentina."""
    hoy = instante.astimezone(ZONA_ARGENTINA).date()
    return CatalogoLegal(catalogo.versiones()).vigente(documento, hoy)


def _vigente(
    catalogo: PortCatalogoLegal, reloj: Reloj, documento: DocumentoLegal
) -> VersionDeDocumento:
    return vigente_a(catalogo, reloj.ahora(), documento)


class ConsultarDocumentoVigente:
    """One document, in the version in force today."""

    def __init__(self, *, catalogo: PortCatalogoLegal, reloj: Reloj) -> None:
        self._catalogo = catalogo
        self._reloj = reloj

    async def ejecutar(self, documento: DocumentoLegal) -> DocumentoPublicado:
        version = _vigente(self._catalogo, self._reloj, documento)
        return DocumentoPublicado(
            documento=documento,
            version=version.version,
            vigente_desde=version.vigente_desde,
            borrador=version.borrador,
            texto=self._catalogo.texto(documento, version.version),
        )


class ConsultarVersionesVigentes:
    """The version in force of each document, without the texts."""

    def __init__(self, *, catalogo: PortCatalogoLegal, reloj: Reloj) -> None:
        self._catalogo = catalogo
        self._reloj = reloj

    async def ejecutar(self) -> VersionesVigentes:
        return VersionesVigentes(
            terminos=_vigente(self._catalogo, self._reloj, DocumentoLegal.TERMINOS),
            privacidad=_vigente(self._catalogo, self._reloj, DocumentoLegal.PRIVACIDAD),
        )
