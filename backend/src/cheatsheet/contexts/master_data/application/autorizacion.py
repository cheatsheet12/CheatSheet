"""Who may do what with the master data of a company.

Three guards, and they read `RolUsuario` from the Shared Kernel rather than from
`identity/domain/` — rule R3 forbids the import, and the role already travels on the
request. It is the same arrangement `integrations` uses, for the same reason.

The source is the access matrix of the navigation map (Etapa 5, §5), which grades Datos
Maestros **Admin ● · Operador ● · Solo Lectura RO · Contador —**. HU-E4-01 names only
Administrador and Operador as actors, and that is not a contradiction: the story
describes who *manages* the catalogue, the matrix adds who may look at it.
"""

from __future__ import annotations

from cheatsheet.contexts.master_data.application.errors import PermisoDenegado
from cheatsheet.shared.roles import RolUsuario

ROLES_QUE_PUEDEN_LEER = frozenset(
    {RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR, RolUsuario.SOLO_LECTURA}
)
ROLES_QUE_PUEDEN_ESCRIBIR = frozenset({RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR})


def exigir_lectura(rol: RolUsuario) -> None:
    if rol not in ROLES_QUE_PUEDEN_LEER:
        raise PermisoDenegado("Se requiere rol Administrador, Operador o Solo Lectura")


def exigir_escritura(rol: RolUsuario) -> None:
    if rol not in ROLES_QUE_PUEDEN_ESCRIBIR:
        raise PermisoDenegado("Se requiere rol Administrador u Operador para gestionar el catalogo")


def exigir_administrador(rol: RolUsuario) -> None:
    """The mass correction of existing data (HU-E4-05 RN-09) is for the Administrador only."""
    if rol is not RolUsuario.ADMINISTRADOR:
        raise PermisoDenegado("Se requiere rol Administrador para corregir datos existentes")
