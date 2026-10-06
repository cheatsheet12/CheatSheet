"""`Usuario` — someone who operates the panel (HU-E1-01, HU-E1-04 … HU-E1-07).

Three fields are here that the DER does not have (gap H1): `nombre`, which PAN-USR-01
lists and HU-E1-04 asks for; `hash_de_contrasena`, without which HU-E1-01 RN-01 cannot
exist at all; and `estado`, which replaces the DER's boolean `activo` because the screen
shows three states and the "at least one active Administrator" invariant must not count
somebody who was invited and never accepted (see `EstadoUsuario`).

`hash_de_contrasena` is **optional**, and that is not laxity: a user who signed up with
Google has no password on this platform, and a user who was just invited has not chosen
one yet. Inventing one would be inventing a credential nobody picked. Neither can
authenticate by password until that changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cheatsheet.contexts.identity.domain.valores import (
    Email,
    EstadoUsuario,
    HashDeContrasena,
    PreferenciasDeNotificacion,
    RolUsuario,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

IDIOMA_POR_DEFECTO = "es-AR"
ZONA_HORARIA_POR_DEFECTO = "America/Argentina/Buenos_Aires"

#: The name an invited person has before they accept and tell us theirs. PAN-USR-01 shows
#: it in the list, so the row needs *something*, and the column is NOT NULL.
NOMBRE_PENDIENTE = "(invitación pendiente)"


@dataclass(slots=True)
class Usuario:
    """A person with access to one company's panel."""

    id: UsuarioId
    empresa_id: EmpresaId
    email: Email
    nombre: str
    rol: RolUsuario
    estado: EstadoUsuario = EstadoUsuario.ACTIVO
    hash_de_contrasena: HashDeContrasena | None = None
    pref_idioma: str = IDIOMA_POR_DEFECTO
    pref_zona_horaria: str = ZONA_HORARIA_POR_DEFECTO
    pref_suscripciones: PreferenciasDeNotificacion = field(
        default_factory=PreferenciasDeNotificacion.todas
    )

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise EntradaInvalida("El nombre del usuario es obligatorio")
        self.nombre = self.nombre.strip()

    @property
    def es_administrador(self) -> bool:
        return self.rol is RolUsuario.ADMINISTRADOR

    @property
    def activo(self) -> bool:
        return self.estado is EstadoUsuario.ACTIVO

    @property
    def es_administrador_activo(self) -> bool:
        """The exact condition HU-E1-05 RN-02 and HU-E1-06 RN-03 protect."""
        return self.es_administrador and self.activo

    @property
    def puede_autenticarse_con_contrasena(self) -> bool:
        return self.hash_de_contrasena is not None

    def exigir_activo(self) -> None:
        """HU-E1-06 RN-01: a deactivated user loses access immediately."""
        if not self.activo:
            raise InvarianteViolada("El usuario no esta activo")

    def cambiar_contrasena(self, hash_nuevo: HashDeContrasena) -> None:
        self.hash_de_contrasena = hash_nuevo

    def aceptar_invitacion(self, *, nombre: str, hash_de_contrasena: HashDeContrasena) -> None:
        """HU-E1-04: accepting is what turns an invitation into an account.

        Only from `INVITADO`. Replaying the acceptance of an account that is already
        active would be a password reset with no proof of who is asking, which is a
        different feature and a much more dangerous one.
        """
        if self.estado is not EstadoUsuario.INVITADO:
            raise InvarianteViolada("Solo se puede aceptar una invitacion pendiente")
        if not nombre.strip():
            raise EntradaInvalida("El nombre del usuario es obligatorio")
        self.nombre = nombre.strip()
        self.hash_de_contrasena = hash_de_contrasena
        self.estado = EstadoUsuario.ACTIVO

    def cambiar_rol(self, rol_nuevo: RolUsuario) -> None:
        """HU-E1-05 RN-01: immediate, over the affected user's next actions.

        The invariant about the last Administrator is **not** checked here. It is a rule
        over the whole set of a company's users, and no single aggregate can hold it — see
        `CambiarRolDeUsuario`.
        """
        self.rol = rol_nuevo

    def desactivar(self) -> None:
        """HU-E1-06. The role is deliberately left untouched.

        RN-04 says a reactivated user comes back with the role they had. That works
        because deactivating never erased it — there is nothing to restore, which is the
        only version of "restore the previous role" that cannot lose it.
        """
        if self.estado is EstadoUsuario.INVITADO:
            raise InvarianteViolada("Una invitacion pendiente se revoca, no se desactiva")
        self.estado = EstadoUsuario.INACTIVO

    def reactivar(self) -> None:
        """HU-E1-06 RN-04."""
        if self.estado is not EstadoUsuario.INACTIVO:
            raise InvarianteViolada("Solo se puede reactivar a un usuario inactivo")
        self.estado = EstadoUsuario.ACTIVO

    def actualizar_preferencias(
        self,
        *,
        idioma: str | None = None,
        zona_horaria: str | None = None,
        suscripciones: PreferenciasDeNotificacion | None = None,
    ) -> None:
        """HU-E1-07. Individual to each user, applied immediately.

        `None` means "leave this one alone", so the screen can save one field without
        having to send the other two back exactly as they were.
        """
        if idioma is not None:
            self.pref_idioma = idioma
        if zona_horaria is not None:
            self.pref_zona_horaria = zona_horaria
        if suscripciones is not None:
            self.pref_suscripciones = suscripciones
