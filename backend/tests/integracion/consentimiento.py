"""The consent a form sends, built from the versions the application publishes right now.

Sign-up and accepting an invitation require it (HU-E1-03 RN-02, HU-E1-08 RN-03/04), and the
backend rejects a version that is not the one in force. Tests therefore ask the catalogue
instead of hardcoding `1.1`: publishing a new version must not break forty unrelated tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cheatsheet.contexts.identity.application.legal import vigente_a
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal
from cheatsheet.contexts.identity.infrastructure.legal.catalogo import catalogo_publicado


def _vigente(documento: DocumentoLegal) -> str:
    return vigente_a(catalogo_publicado(), datetime.now(UTC), documento).version


VERSION_DE_TERMINOS = _vigente(DocumentoLegal.TERMINOS)
VERSION_DE_PRIVACIDAD = _vigente(DocumentoLegal.PRIVACIDAD)

#: The body of `consentimiento` in `POST /auth/registro` and `POST /auth/google/callback`.
CONSENTIMIENTO = {
    "version_terminos": VERSION_DE_TERMINOS,
    "version_privacidad": VERSION_DE_PRIVACIDAD,
}
