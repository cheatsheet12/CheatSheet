"""Does this access token still authorize anything? (HU-E1-05, HU-E1-06)

The access token is a signed claim about the past: who the user was, in which company, with
which role, **when it was issued**. It stops being authority on role and status. Every
authenticated request asks the database what is true now, so a deactivation or a role
change takes effect on the user's next request and not when the token happens to expire.

The use case is deliberately tiny and does one thing the middleware must not: it decides.
The middleware only translates the outcome into HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.contexts.identity.application.errors import MotivoDeRevocacion, SesionRevocada
from cheatsheet.contexts.identity.application.ports import PortConsultaDeUsuarioVigente
from cheatsheet.contexts.identity.domain.valores import EstadoUsuario, RolUsuario
from cheatsheet.shared.empresa import EmpresaId, UsuarioId


@dataclass(frozen=True, slots=True)
class IdentidadVigente:
    """Who is asking, as the database says it right now. Never as the token says it."""

    empresa_id: EmpresaId
    usuario_id: UsuarioId
    rol: RolUsuario


class VerificarSesionVigente:
    """Resolves a signed token's claims into the current identity, or refuses.

    Guarantees:

    - the **role comes from the database**; the role in the token is not even an input;
    - only `ACTIVO` operates. An `INVITADO` has not accepted yet and an `INACTIVO` was
      switched off, and neither may act on a token;
    - the stored company must equal the one the token names. The signature already vouches
      for the claim, and the row is compared anyway: if the two ever disagree, trusting
      either one is the wrong answer.
    """

    def __init__(self, *, consulta: PortConsultaDeUsuarioVigente) -> None:
        self._consulta = consulta

    async def ejecutar(
        self, *, usuario_id: UsuarioId, empresa_id_del_token: EmpresaId
    ) -> IdentidadVigente:
        estado = await self._consulta.estado_actual(usuario_id)
        if estado is None:
            raise SesionRevocada(MotivoDeRevocacion.USUARIO_INEXISTENTE)
        if estado.estado is not EstadoUsuario.ACTIVO:
            raise SesionRevocada(MotivoDeRevocacion.USUARIO_INACTIVO)
        if estado.empresa_id != empresa_id_del_token:
            raise SesionRevocada(MotivoDeRevocacion.EMPRESA_NO_COINCIDE)
        return IdentidadVigente(empresa_id=estado.empresa_id, usuario_id=usuario_id, rol=estado.rol)
