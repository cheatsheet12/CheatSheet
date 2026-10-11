"""The consent a form sends, built from the versions the application publishes right now.

Sign-up and accepting an invitation require it (HU-E1-03 RN-02, HU-E1-08 RN-03/04), and the
backend rejects a version that is not the one in force. Tests therefore ask the catalogue
instead of hardcoding `1.1`: publishing a new version must not break forty unrelated tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cheatsheet.contexts.identity.application.legal import vigente_a
from cheatsheet.contexts.identity.domain.legal import CatalogoLegal, DocumentoLegal
from cheatsheet.contexts.identity.infrastructure.consulta_de_sesion import (
    VerificadorDeSesionPostgres,
)
from cheatsheet.contexts.identity.infrastructure.legal.catalogo import catalogo_publicado
from cheatsheet.shared.clock import RelojDelSistema
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker


def _vigente(documento: DocumentoLegal) -> str:
    return vigente_a(catalogo_publicado(), datetime.now(UTC), documento).version


VERSION_DE_TERMINOS = _vigente(DocumentoLegal.TERMINOS)
VERSION_DE_PRIVACIDAD = _vigente(DocumentoLegal.PRIVACIDAD)

#: The body of `consentimiento` in `POST /auth/registro` and `POST /auth/google/callback`.
CONSENTIMIENTO = {
    "version_terminos": VERSION_DE_TERMINOS,
    "version_privacidad": VERSION_DE_PRIVACIDAD,
}


def verificador_de_sesion(
    sesiones: async_sessionmaker[AsyncSession],
) -> VerificadorDeSesionPostgres:
    """The per-request session check wired as `create_app` wires it: real catalogue, real clock.

    The check blocks anyone who owes a legal document in force, so a test that authenticates a
    user must create it with the versions in force (`CONSENTIMIENTO`, or `_crear_cuenta`) rather
    than switch the check off.
    """
    return VerificadorDeSesionPostgres(
        sesiones,
        catalogo=CatalogoLegal(catalogo_publicado().versiones()),
        reloj=RelojDelSistema(),
    )


async def sembrar_privacidad_vigente(
    conexion: AsyncConnection, empresa_id: object, usuario_id: object
) -> None:
    """Records, as the table owner, that a user seeded straight into `usuario` accepted privacy.

    A user created through sign-up already has it. One inserted with SQL (a role the API cannot
    create without the invitation token) would be blocked on every request, so the seed must
    carry the acceptance in force, exactly as a real user does, instead of the check being
    switched off.
    """
    await conexion.execute(
        text(
            "INSERT INTO aceptacion_legal (id, empresa_id, usuario_id, documento, version, "
            "fecha_aceptacion) VALUES (gen_random_uuid(), :empresa_id, :usuario_id, "
            "'PRIVACIDAD', :version, now())"
        ),
        {"empresa_id": empresa_id, "usuario_id": usuario_id, "version": VERSION_DE_PRIVACIDAD},
    )
