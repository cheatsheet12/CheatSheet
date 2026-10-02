"""`CategoriaEmpresa` — how a business organises its own catalogue (HU-E4-03, HU-E4-04).

The third aggregate of `master_data`, and the smallest: a name and a scope. What makes it
worth its own module is the rule that governs the scope, because that rule is the whole of
HU-E4-04 RN-01 and it has to hold for callers this screen has never met — the agent of
epic 8 will classify too.

**There is no `Clasificacion` aggregate.** The link between an element and a category is a
relation without identity or lifecycle: it exists or it does not. Modelling it as an entity
would add an id nobody reads and a repository with two methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cheatsheet.contexts.master_data.domain.normalizacion import normalizar_nombre_de_catalogo
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

LARGO_MAXIMO_NOMBRE = 60

#: The exact text of HU-E4-03's second acceptance criterion, without accents like the rest.
MENSAJE_DUPLICADA = "Ya existe una categoria con ese nombre en este ambito."


@dataclass(slots=True)
class CategoriaEmpresa:
    """A label a company invented for itself."""

    id: UUID
    empresa_id: EmpresaId
    nombre: str
    aplica_a: AmbitoDeCategoria
    creado_en: datetime

    @classmethod
    def registrar(
        cls,
        *,
        id: UUID,
        empresa_id: EmpresaId,
        nombre: str,
        aplica_a: AmbitoDeCategoria,
        momento: datetime,
    ) -> CategoriaEmpresa:
        return cls(
            id=id,
            empresa_id=empresa_id,
            nombre=_nombre_valido(nombre),
            aplica_a=aplica_a,
            creado_en=momento,
        )

    def renombrar(self, nombre: str) -> None:
        """The change reaches every classified element for free.

        HU-E4-03's third acceptance criterion — «el cambio se refleja en todos los
        elementos clasificados con ella» — is satisfied by there being one row holding the
        name. With a denormalised copy this method would have to go and update N rows, and
        the criterion would be work rather than a consequence of normalising.
        """
        self.nombre = _nombre_valido(nombre)

    def cambiar_ambito(self, aplica_a: AmbitoDeCategoria) -> None:
        """Narrowing a scope does **not** unassign what no longer fits.

        A category that went from `AMBOS` to `CLIENTE` leaves the services it had already
        classified alone. The story says nothing about it, and silently deleting somebody's
        classifications as a side effect of an edit is the kind of surprise that gets
        discovered months later. New assignments obey the new scope; the old ones stay
        until somebody removes them on purpose.
        """
        self.aplica_a = aplica_a

    @property
    def admite_clientes(self) -> bool:
        return self.aplica_a in (AmbitoDeCategoria.CLIENTE, AmbitoDeCategoria.AMBOS)

    @property
    def admite_servicios(self) -> bool:
        return self.aplica_a in (AmbitoDeCategoria.SERVICIO, AmbitoDeCategoria.AMBOS)

    def exigir_admite_cliente(self) -> None:
        """HU-E4-04 RN-01, on the client side.

        Lives here rather than in the form's dropdown because the screen only hides what
        does not fit — the acceptance criterion is «el sistema no ofrece esa categoría» —
        and hiding is not refusing. Epic 8's agent will assign categories through no form
        at all.
        """
        if not self.admite_clientes:
            raise AmbitoIncompatible(
                f"La categoria '{self.nombre}' no se puede asignar a un cliente"
            )

    def exigir_admite_servicio(self) -> None:
        if not self.admite_servicios:
            raise AmbitoIncompatible(
                f"La categoria '{self.nombre}' no se puede asignar a un servicio"
            )


class AmbitoIncompatible(InvarianteViolada):
    """The category's scope does not admit the element it was pointed at (RN-01)."""


def _nombre_valido(nombre: str) -> str:
    limpio = normalizar_nombre_de_catalogo(nombre)
    if not limpio:
        raise EntradaInvalida("El nombre de la categoria es obligatorio")
    if len(limpio) > LARGO_MAXIMO_NOMBRE:
        raise EntradaInvalida(f"El nombre de la categoria excede {LARGO_MAXIMO_NOMBRE} caracteres")
    return limpio


def clave_de_unicidad(nombre: str) -> str:
    """How RN-02 compares two names: normalized (HU-E4-05) and lowercased.

    «VIP» and «vip» are the same name to anybody reading the list, and allowing both
    produces two rows that look identical. The database enforces the same rule with a
    functional unique index over `lower(nombre)`, so the two cannot drift apart.
    """
    return normalizar_nombre_de_catalogo(nombre).lower()
