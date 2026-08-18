"""Personal preferences (HU-E1-07).

The only use case in `identity` that any role may run, because it is the only one that
acts on the caller themself. There is no `usuario_id` parameter separate from the
authenticated one on purpose: an endpoint that accepted one would be an endpoint for
editing somebody else's preferences, and RN-01 says preferences are individual.

**No audit entry.** HS-T5 logs operations on the company's data; someone changing their
own time zone is neither an administrative act nor something another user could dispute.
Neither HU-E1-07 nor HS-T5 asks for it, and writing a row on every toggle of a checkbox
would bury the entries that matter under noise.
"""

from __future__ import annotations

from cheatsheet.contexts.identity.application.ports import PortRepositorioUsuario
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import PreferenciasDeNotificacion
from cheatsheet.shared.empresa import UsuarioId
from cheatsheet.shared.errors import EntradaInvalida


class VerPreferencias:
    """The first acceptance criterion: see the current ones before changing them."""

    def __init__(self, *, usuarios: PortRepositorioUsuario) -> None:
        self._usuarios = usuarios

    async def ejecutar(self, *, usuario_id: UsuarioId) -> Usuario:
        return await _cargar(self._usuarios, usuario_id)


class ActualizarPreferencias:
    """HU-E1-07 RN-03: applied immediately on save.

    Every field is optional and `None` means "leave this one alone", so the screen can
    save one change without echoing the other two back exactly as they were — the pattern
    where a stale form quietly reverts a setting the user changed in another tab.
    """

    def __init__(self, *, usuarios: PortRepositorioUsuario) -> None:
        self._usuarios = usuarios

    async def ejecutar(
        self,
        *,
        usuario_id: UsuarioId,
        idioma: str | None = None,
        zona_horaria: str | None = None,
        suscripciones: PreferenciasDeNotificacion | None = None,
    ) -> Usuario:
        usuario = await _cargar(self._usuarios, usuario_id)
        usuario.actualizar_preferencias(
            idioma=idioma, zona_horaria=zona_horaria, suscripciones=suscripciones
        )
        await self._usuarios.guardar(usuario)
        return usuario


async def _cargar(usuarios: PortRepositorioUsuario, usuario_id: UsuarioId) -> Usuario:
    usuario = await usuarios.buscar_por_id(usuario_id)
    if usuario is None:  # pragma: no cover — the id comes from a verified access token
        raise EntradaInvalida("El usuario no existe")
    return usuario
