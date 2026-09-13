"""Puertos de `business_config`.

Uno solo, y estrecho a propósito: las reglas son filas de una empresa y nada más. No hay
`eliminar` — RN-04 pide **desactivar**, y una regla borrada deja la bitácora apuntando a algo
que ya no existe.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.business_config.domain.plantilla import PlantillaDeNotificacion
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


class PortRepositorioPlantillas(Protocol):
    """Persistencia de plantillas de notificacion (HU-E11-02), siempre dentro de una empresa.

    **Sin `eliminar`.** Los codigos los define el sistema: una plantilla borrada volveria a
    sembrarse en el siguiente listado, asi que el borrado no significaria nada. Lo que un
    administrador hace es editar el cuerpo.
    """

    async def agregar(self, plantilla: PlantillaDeNotificacion) -> None: ...

    async def guardar(self, plantilla: PlantillaDeNotificacion) -> None: ...

    async def buscar_por_id(self, plantilla_id: UUID) -> PlantillaDeNotificacion | None: ...

    async def buscar_por_codigo(self, codigo: str) -> PlantillaDeNotificacion | None:
        """La plantilla vigente para ese codigo, o `None`.

        `None` es un camino previsto y no un error: el adaptador que la pedia usa su texto de
        fabrica. Ver `ResolverPlantilla`.
        """
        ...

    async def listar(self) -> list[PlantillaDeNotificacion]: ...
