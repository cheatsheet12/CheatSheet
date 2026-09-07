"""Puertos de `business_config`.

Uno solo, y estrecho a propósito: las reglas son filas de una empresa y nada más. No hay
`eliminar` — RN-04 pide **desactivar**, y una regla borrada deja la bitácora apuntando a algo
que ya no existe.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio, TipoRegla


class PortRepositorioReglas(Protocol):
    """Persistencia de reglas, siempre dentro de una empresa.

    Sin parámetro `empresa_id`: cada sentencia corre en una sesión con `app.current_empresa`
    puesto y la política de RLS filtra. Pasarlo también sugeriría que la barrera es
    responsabilidad de este puerto, y el día que alguien se olvidara de pasarlo sería el día
    que la barrera no existe.
    """

    async def agregar(self, regla: ReglaDeNegocio) -> None: ...

    async def guardar(self, regla: ReglaDeNegocio) -> None: ...

    async def buscar_por_id(self, regla_id: UUID) -> ReglaDeNegocio | None: ...

    async def listar(self, tipo: TipoRegla | None = None) -> list[ReglaDeNegocio]:
        """Todas las de la empresa, o las de un tipo. **Incluye las inactivas.**

        La pantalla las muestra con su estado (RN-01), así que filtrarlas acá obligaría a un
        segundo método para lo mismo. Quien necesita sólo las vigentes usa `resolver`, que es
        del dominio y ya sabe qué significa «aplicable».
        """
        ...


__all__ = ["PortRepositorioReglas"]
