"""`Usuario` — someone who operates the panel (HU-E1-01, and epic 1's later unit).

Two fields are here that the DER does not have (gap H1): `nombre`, which PAN-USR-01
lists and HU-E1-04 asks for, and `hash_de_contrasena`, without which HU-E1-01 RN-01
cannot exist at all.

`hash_de_contrasena` is **optional**, and that is not laxity: a user who signed up with
Google has no password on this platform, and inventing one would be inventing a
credential nobody chose. Such a user simply cannot authenticate by password.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.contexts.identity.domain.valores import (
    Email,
    HashDeContrasena,
    RolUsuario,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

IDIOMA_POR_DEFECTO = "es-AR"
ZONA_HORARIA_POR_DEFECTO = "America/Argentina/Buenos_Aires"


@dataclass(slots=True)
class Usuario:
    """A person with access to one company's panel."""

    id: UsuarioId
    empresa_id: EmpresaId
    email: Email
    nombre: str
    rol: RolUsuario
    activo: bool = True
    hash_de_contrasena: HashDeContrasena | None = None
    pref_idioma: str = IDIOMA_POR_DEFECTO
    pref_zona_horaria: str = ZONA_HORARIA_POR_DEFECTO

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise EntradaInvalida("El nombre del usuario es obligatorio")
        self.nombre = self.nombre.strip()

    @property
    def es_administrador(self) -> bool:
        return self.rol is RolUsuario.ADMINISTRADOR

    @property
    def puede_autenticarse_con_contrasena(self) -> bool:
        return self.hash_de_contrasena is not None

    def exigir_activo(self) -> None:
        """HU-E1-06 RN-01: a deactivated user loses access immediately."""
        if not self.activo:
            raise InvarianteViolada("El usuario esta desactivado")

    def cambiar_contrasena(self, hash_nuevo: HashDeContrasena) -> None:
        self.hash_de_contrasena = hash_nuevo

    def actualizar_preferencias(self, *, idioma: str | None, zona_horaria: str | None) -> None:
        """HU-E1-07. Individual to each user, applied immediately."""
        if idioma is not None:
            self.pref_idioma = idioma
        if zona_horaria is not None:
            self.pref_zona_horaria = zona_horaria
