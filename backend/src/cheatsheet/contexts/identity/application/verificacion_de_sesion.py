"""Does this access token still authorize anything? (HU-E1-05, HU-E1-06)

The access token is a signed claim about the past: who the user was, in which company, with
which role, **when it was issued**. It stops being authority on role and status. Every
authenticated request asks the database what is true now, so a deactivation or a role
change takes effect on the user's next request and not when the token happens to expire.

The use case is deliberately tiny and does one thing the middleware must not: it decides.
The middleware only translates the outcome into HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cheatsheet.contexts.identity.application.errors import MotivoDeRevocacion, SesionRevocada
from cheatsheet.contexts.identity.application.ports import PortConsultaDeUsuarioVigente
from cheatsheet.contexts.identity.domain.legal import (
    CatalogoLegal,
    DocumentoLegal,
    documentos_pendientes,
)
from cheatsheet.contexts.identity.domain.valores import EstadoUsuario, RolUsuario
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA


@dataclass(frozen=True, slots=True)
class IdentidadVigente:
    """Who is asking, as the database says it right now. Never as the token says it."""

    empresa_id: EmpresaId
    usuario_id: UsuarioId
    rol: RolUsuario
    #: Legal documents this person must accept before doing anything but reading the texts
    #: and signing out (HU-E1-03 RN-03, HU-E1-08 RN-05). Empty for almost every request.
    pendientes: frozenset[DocumentoLegal] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class VersionesEnVigor:
    """The version of each document in force today (HU-E1-08 RN-01)."""

    terminos: str
    privacidad: str


def versiones_en_vigor(catalogo: CatalogoLegal, reloj: Reloj) -> VersionesEnVigor:
    """Looks the versions up **before** any database connection exists.

    Pure: it reads the catalogue built with the process and the clock. Raises `InvarianteViolada`
    when a document has none in force, which `create_app` turns into a boot failure; at request
    time it is the same error, but it is raised before the session check takes a connection.
    """
    hoy = reloj.ahora().astimezone(ZONA_ARGENTINA).date()
    return VersionesEnVigor(
        terminos=catalogo.vigente(DocumentoLegal.TERMINOS, hoy).version,
        privacidad=catalogo.vigente(DocumentoLegal.PRIVACIDAD, hoy).version,
    )


class VerificarSesionVigente:
    """Resolves a signed token's claims into the current identity, or refuses.

    Guarantees:

    - the **role comes from the database**; the role in the token is not even an input;
    - only `ACTIVO` operates. An `INVITADO` has not accepted yet and an `INACTIVO` was
      switched off, and neither may act on a token;
    - the stored company must equal the one the token names. The signature already vouches
      for the claim, and the row is compared anyway: if the two ever disagree, trusting
      either one is the wrong answer;
    - the legal documents still owed come out of the **same** read: the caller hands in the
      versions in force (`versiones_en_vigor`, looked up before any connection is taken) and
      the pure rule `documentos_pendientes` decides.
    """

    def __init__(self, *, consulta: PortConsultaDeUsuarioVigente) -> None:
        self._consulta = consulta

    async def ejecutar(
        self, *, usuario_id: UsuarioId, empresa_id_del_token: EmpresaId, versiones: VersionesEnVigor
    ) -> IdentidadVigente:
        estado = await self._consulta.estado_actual(
            usuario_id, version_de_privacidad=versiones.privacidad
        )
        if estado is None:
            raise SesionRevocada(MotivoDeRevocacion.USUARIO_INEXISTENTE)
        if estado.estado is not EstadoUsuario.ACTIVO:
            raise SesionRevocada(MotivoDeRevocacion.USUARIO_INACTIVO)
        if estado.empresa_id != empresa_id_del_token:
            raise SesionRevocada(MotivoDeRevocacion.EMPRESA_NO_COINCIDE)
        return IdentidadVigente(
            empresa_id=estado.empresa_id,
            usuario_id=usuario_id,
            rol=estado.rol,
            pendientes=documentos_pendientes(
                rol=estado.rol,
                version_de_terminos_de_la_empresa=estado.terminos_version,
                acepto_privacidad_vigente=estado.acepto_privacidad_vigente,
                terminos_vigente=versiones.terminos,
            ),
        )
