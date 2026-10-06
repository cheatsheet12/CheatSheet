"""Puertos de `business_config`.

Uno solo, y estrecho a propósito: las reglas son filas de una empresa y nada más. No hay
`eliminar` — RN-04 pide **desactivar**, y una regla borrada deja la bitácora apuntando a algo
que ya no existe.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class RespuestaDeMeta:
    """Lo que Meta contesta al crear o editar una plantilla. `estado` es su vocabulario."""

    meta_plantilla_id: str
    estado: str
    categoria: str | None = None


@dataclass(frozen=True, slots=True)
class EstadoEnMeta:
    """Una plantilla tal como está en la WABA de la empresa."""

    meta_plantilla_id: str
    nombre: str
    idioma: str
    estado: str
    categoria: str | None = None
    motivo: str | None = None
    cuerpo: str | None = None


class PortRevisionDeMeta(Protocol):
    """La WABA de la empresa, vista desde las plantillas (U6, ADR-0011 §4).

    La forma estrecha que `business_config` necesita de Meta: crear, editar y leer. Quien la
    implementa es la raíz de composición, sobre el cliente de `conversational`, y traduce sus
    errores a los de este contexto: `MetaRechazoLaPlantilla`, `MetaNoDisponible` y
    `MetaNoConectada`. Este contexto no importa `conversational`.
    """

    async def crear(
        self, *, nombre: str, idioma: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDeMeta: ...

    async def editar(
        self, *, meta_plantilla_id: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDeMeta: ...

    async def estados(self) -> list[EstadoEnMeta]:
        """Todas las plantillas de la WABA (paginado del otro lado)."""
        ...


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

    async def buscar_por_meta_id(self, meta_plantilla_id: str) -> PlantillaDeNotificacion | None:
        """La plantilla de esta empresa con ese id de Meta: lo que trae el webhook."""
        ...

    async def buscar_por_nombre_en_meta(
        self, nombre: str, idioma: str
    ) -> PlantillaDeNotificacion | None:
        """La que se llama así en Meta. La conciliación la usa para no crear una dos veces."""
        ...

    async def listar(self) -> list[PlantillaDeNotificacion]: ...
