"""The legal texts, published as versioned Markdown files (HU-E1-08 RN-01).

Each published version is a file, `legal/<documento>/<version>.md`, plus a line in
`PUBLICADAS` that declares its effective date, whether it is still a draft, and the
**SHA-256 of its text**. Loading checks every hash, so editing a published text breaks the
application at start-up and a unit test breaks CI: correcting a text means publishing a new
version, never changing an old one. The older files stay in the repository as the evidence
of what somebody accepted.

The texts are read **once**, when the catalogue is built. A request never touches the disk.
The hash is computed over the text with universal newlines, so a checkout with CRLF line
endings (Windows) reads the same bytes as one with LF.

Texts are written in a small Markdown subset (`##` headings, paragraphs and `-` lists);
the frontend draws them as React elements and never as HTML.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from cheatsheet.contexts.identity.domain.legal import DocumentoLegal, VersionDeDocumento
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

RAIZ_DE_TEXTOS = Path(__file__).parent


class TextoLegalAlterado(RuntimeError):
    """A published text no longer matches the hash it was published with."""


@dataclass(frozen=True, slots=True)
class VersionPublicada:
    """A catalogue entry: the version and the digest of its text."""

    version: VersionDeDocumento
    sha256: str


#: Every published version, oldest first. Add a line to publish; never edit an old one.
#:
#: Both entries are **drafts pending legal validation** (HU-E1-08 RN-07): the validated text
#: is published later as a new version. Terms start at `1.1` because the `1.0` recorded on
#: every existing company belongs to an environment variable that never had a text behind it.
PUBLICADAS: tuple[VersionPublicada, ...] = (
    VersionPublicada(
        VersionDeDocumento(DocumentoLegal.PRIVACIDAD, "1.0", date(2026, 10, 10), borrador=True),
        sha256="7b8661332ebebcaf248320a2281a24e06a3876585af89cac2142f1ac7cb2230b",
    ),
    VersionPublicada(
        VersionDeDocumento(DocumentoLegal.TERMINOS, "1.1", date(2026, 10, 10), borrador=True),
        sha256="6199155aded902090c330a8d3a7e71c351574cba5a26e90a7b0e0a046d2b296b",
    ),
)


def _archivo(raiz: Path, version: VersionDeDocumento) -> Path:
    return raiz / version.documento.value.lower() / f"{version.version}.md"


class CatalogoLegalEnArchivos:
    """Implements `PortCatalogoLegal` over the packaged Markdown files."""

    def __init__(
        self,
        publicadas: Sequence[VersionPublicada] = PUBLICADAS,
        raiz: Path = RAIZ_DE_TEXTOS,
    ) -> None:
        self._versiones: tuple[VersionDeDocumento, ...] = tuple(p.version for p in publicadas)
        self._textos: dict[tuple[DocumentoLegal, str], str] = {}
        for publicada in publicadas:
            version = publicada.version
            texto = _archivo(raiz, version).read_text(encoding="utf-8")
            if hashlib.sha256(texto.encode("utf-8")).hexdigest() != publicada.sha256:
                logger.error(
                    "texto_legal_alterado",
                    documento=version.documento.value,
                    version=version.version,
                )
                raise TextoLegalAlterado(
                    f"El texto de {version.documento.value} {version.version} cambio: "
                    "publicar una version nueva en lugar de editarlo"
                )
            self._textos[(version.documento, version.version)] = texto

    def versiones(self) -> Sequence[VersionDeDocumento]:
        return self._versiones

    def texto(self, documento: DocumentoLegal, version: str) -> str:
        return self._textos[(documento, version)]


@cache
def catalogo_publicado() -> CatalogoLegalEnArchivos:
    """The process-wide catalogue: the texts are read and hashed once, not once per consumer."""
    return CatalogoLegalEnArchivos()
