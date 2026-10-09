"""A session verifier for API tests that sit *behind* the middleware and have no database.

`create_app(..., verificador=...)` is the seam. The real verifier reads the user from
PostgreSQL, so a test that signs a token for a user that was never stored would get a 401,
which is correct. A test that only wants to reach a route injects this instead: it vouches
for the claims it is given, with the role the test chooses, and records what it was asked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cheatsheet.contexts.identity.application.verificacion_de_sesion import IdentidadVigente
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.contexts.identity.infrastructure.seguridad import EmisorDeTokensJWT
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId, UsuarioId


class VerificadorDeSesionFalso:
    """Vouches for whoever the token claims to be, with the role set on `rol`.

    `error` makes it raise instead (a revoked session, or an infrastructure failure), and
    `devuelve` makes it answer with an identity that differs from the claims, which is how a
    test shows that `request.state` comes from the verifier and not from the token.
    """

    def __init__(
        self,
        *,
        rol: RolUsuario = RolUsuario.ADMINISTRADOR,
        error: Exception | None = None,
        devuelve: IdentidadVigente | None = None,
    ) -> None:
        self.rol = rol
        self.error = error
        self.devuelve = devuelve
        self.llamadas: list[tuple[UsuarioId, EmpresaId]] = []

    async def verificar(
        self, *, usuario_id: UsuarioId, empresa_id_del_token: EmpresaId
    ) -> IdentidadVigente:
        self.llamadas.append((usuario_id, empresa_id_del_token))
        if self.error is not None:
            raise self.error
        if self.devuelve is not None:
            return self.devuelve
        return IdentidadVigente(
            empresa_id=empresa_id_del_token, usuario_id=usuario_id, rol=self.rol
        )


def token_firmado(
    settings: Settings,
    *,
    rol: str = "ADMINISTRADOR",
    usuario_id: UsuarioId | None = None,
    empresa_id: EmpresaId | None = None,
    secreto: str | None = None,
    ahora: datetime | None = None,
) -> str:
    """A genuinely signed access token, so the middleware is exercised and not bypassed."""
    emisor = EmisorDeTokensJWT(
        secreto=secreto or settings.jwt_secret, vida_acceso=timedelta(minutes=15)
    )
    return emisor.emitir_acceso(
        usuario_id=usuario_id or UsuarioId(uuid4()),
        empresa_id=empresa_id or EmpresaId(uuid4()),
        rol=rol,
        ahora=ahora or datetime.now(UTC),
    ).valor


def autorizacion(settings: Settings, *, rol: str = "ADMINISTRADOR") -> dict[str, str]:
    """The `Authorization` header for a token of a made-up user."""
    return {"Authorization": f"Bearer {token_firmado(settings, rol=rol)}"}
