"""Who may do what (HU-E1-04, HU-E1-05 RN-03, HU-E1-06).

**This check lives in the application layer on purpose, not only in the router.** The
middleware already refuses a request with no valid token, and the frontend already hides
the buttons a role cannot use — but neither of those is where the decision belongs. A use
case invoked from a Celery task, from a future admin CLI or from another endpoint written
in a hurry has to reach the same answer, and it will only do that if the rule sits next to
the operation it guards.

The three roles are a closed catalogue (HU-E1-04 RN-01) with fixed permissions. There is
no permission table and no per-role configuration, because the story explicitly says there
is not.
"""

from __future__ import annotations

from cheatsheet.contexts.identity.application.errors import PermisoDenegado
from cheatsheet.contexts.identity.domain.valores import RolUsuario

#: What the caller reads when the guard bites and the use case says nothing more precise.
MOTIVO_POR_DEFECTO = "Solo un Administrador puede administrar los usuarios de la empresa"


def exigir_administrador(rol: RolUsuario, motivo: str = MOTIVO_POR_DEFECTO) -> None:
    """Everything that touches somebody else's account.

    `motivo` exists because this guard now protects more than the user list: the message
    reaches the screen, and telling an Operador editing the company's fiscal data that
    they may not "administrar los usuarios" sends them looking for the wrong problem.
    """
    if rol is not RolUsuario.ADMINISTRADOR:
        raise PermisoDenegado(motivo)
