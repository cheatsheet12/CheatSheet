"""The legal documents the platform publishes and the versions they go through.

HU-E1-03 (terms and conditions) and HU-E1-08 (privacy policy) both rest on the same idea:
a text is published under a **version**, and the version is what a person accepts. This
module is the catalogue of those versions. It knows nothing about where the texts are kept
(`infrastructure/legal/`); who accepted what is `AceptacionLegal`.

**One current version per document (HU-E1-08 RN-01).** The current one is the version with
the greatest `vigente_desde` that is not in the future. Two versions of the same document
that share an identifier or a date would make "the greatest" ambiguous, so the catalogue
refuses to be built with them. Older versions stay in the catalogue: they are the evidence
of what somebody accepted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: Same shape and width as `empresa.terminos_version` (DER): `N.N`, at most 20 characters.
LARGO_MAXIMO_DE_VERSION = 20
_FORMATO_DE_VERSION = re.compile(r"\d+\.\d+")


def validar_identificador_de_version(version: str) -> str:
    """Shared by the catalogue and by the record of an acceptance, so they cannot drift."""
    if len(version) > LARGO_MAXIMO_DE_VERSION or not _FORMATO_DE_VERSION.fullmatch(version):
        raise EntradaInvalida(f"El identificador de version '{version}' debe tener el formato N.N")
    return version


class DocumentoLegal(StrEnum):
    """The closed set of documents a person can accept."""

    TERMINOS = "TERMINOS"
    PRIVACIDAD = "PRIVACIDAD"


@dataclass(frozen=True, slots=True)
class VersionDeDocumento:
    """One published version of one document. Immutable, like the text behind it."""

    documento: DocumentoLegal
    version: str
    #: The calendar day it takes effect, read in `America/Argentina/Buenos_Aires`.
    vigente_desde: date
    #: `True` while the text is a draft pending legal validation (HU-E1-08 RN-07).
    borrador: bool = False

    def __post_init__(self) -> None:
        validar_identificador_de_version(self.version)


@dataclass(frozen=True, slots=True)
class AceptacionLegal:
    """One person (or company) accepting one version of one document (HU-E1-08 RN-02).

    Evidence, so it is immutable and never edited: the table behind it only takes inserts.
    Lives outside the `Empresa` and `Usuario` aggregates, like `Invitacion`: it has its own
    identity and nothing in either aggregate needs to change to accept it.

    `usuario_id` is mandatory for the privacy policy, which a *person* accepts. It is empty
    only for terms recorded by the backfill of migration 0041, when the audit log could not
    say who registered the company; saying "unknown" beats inventing a name.
    """

    id: UUID
    empresa_id: EmpresaId
    usuario_id: UsuarioId | None
    documento: DocumentoLegal
    version: str
    fecha_aceptacion: datetime

    def __post_init__(self) -> None:
        validar_identificador_de_version(self.version)
        if self.fecha_aceptacion.tzinfo is None:
            raise EntradaInvalida("La fecha de aceptacion debe llevar zona horaria")
        if self.usuario_id is None and self.documento is not DocumentoLegal.TERMINOS:
            raise EntradaInvalida(
                f"La aceptacion de {self.documento.value} requiere el usuario que la dio"
            )

    @classmethod
    def registrar(
        cls,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId | None,
        documento: DocumentoLegal,
        version: str,
        fecha_aceptacion: datetime,
    ) -> AceptacionLegal:
        return cls(
            id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            documento=documento,
            version=version,
            fecha_aceptacion=fecha_aceptacion,
        )


class CatalogoLegal:
    """Every published version, and the rule for which one is current."""

    def __init__(self, versiones: Iterable[VersionDeDocumento]) -> None:
        todas = tuple(versiones)
        self._verificar_unicidad(todas)
        self._por_documento: dict[DocumentoLegal, tuple[VersionDeDocumento, ...]] = {
            documento: tuple(
                sorted(
                    (v for v in todas if v.documento is documento),
                    key=lambda v: v.vigente_desde,
                )
            )
            for documento in DocumentoLegal
        }

    @staticmethod
    def _verificar_unicidad(versiones: tuple[VersionDeDocumento, ...]) -> None:
        identificadores: set[tuple[DocumentoLegal, str]] = set()
        fechas: set[tuple[DocumentoLegal, date]] = set()
        for v in versiones:
            if (v.documento, v.version) in identificadores:
                raise InvarianteViolada(
                    f"La version {v.version} de {v.documento.value} esta repetida"
                )
            if (v.documento, v.vigente_desde) in fechas:
                raise InvarianteViolada(
                    f"Dos versiones de {v.documento.value} entran en vigencia el {v.vigente_desde}"
                )
            identificadores.add((v.documento, v.version))
            fechas.add((v.documento, v.vigente_desde))

    def versiones(self, documento: DocumentoLegal) -> tuple[VersionDeDocumento, ...]:
        """Every version of `documento`, oldest first."""
        return self._por_documento[documento]

    def vigente(self, documento: DocumentoLegal, hoy: date) -> VersionDeDocumento:
        """The current version on `hoy`; a future one is not current yet."""
        alcanzadas = [v for v in self._por_documento[documento] if v.vigente_desde <= hoy]
        if not alcanzadas:
            raise InvarianteViolada(f"No hay una version vigente de {documento.value} al {hoy}")
        return alcanzadas[-1]


def documentos_pendientes(
    *,
    rol: RolUsuario,
    version_de_terminos_de_la_empresa: str | None,
    acepto_privacidad_vigente: bool,
    terminos_vigente: str,
) -> frozenset[DocumentoLegal]:
    """What a person must accept before operating again. The only blocking rule there is.

    - The **privacy policy** is personal: everyone owes the version in force until they accept
      it themselves (HU-E1-08 RN-05).
    - The **terms** are the company's, accepted by an Administrador on its behalf, so only an
      Administrador is blocked by them, and only while the company has not accepted the version
      in force (HU-E1-03 RN-03). A company with no terms recorded owes them too.
    """
    pendientes: set[DocumentoLegal] = set()
    if not acepto_privacidad_vigente:
        pendientes.add(DocumentoLegal.PRIVACIDAD)
    if rol is RolUsuario.ADMINISTRADOR and version_de_terminos_de_la_empresa != terminos_vigente:
        pendientes.add(DocumentoLegal.TERMINOS)
    return frozenset(pendientes)
