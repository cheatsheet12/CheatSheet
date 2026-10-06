"""Dobles en memoria de los puertos de las plantillas (U6)."""

from __future__ import annotations

from copy import copy
from uuid import UUID

from cheatsheet.contexts.business_config.domain.plantilla import PlantillaDeNotificacion


class RepositorioPlantillasEnMemoria:
    """Guarda copias, como una base: mutar lo leído no cambia lo guardado hasta `guardar`."""

    def __init__(self, *plantillas: PlantillaDeNotificacion) -> None:
        self.filas: dict[UUID, PlantillaDeNotificacion] = {una.id: copy(una) for una in plantillas}
        self.guardados = 0

    async def agregar(self, plantilla: PlantillaDeNotificacion) -> None:
        self.filas[plantilla.id] = copy(plantilla)

    async def guardar(self, plantilla: PlantillaDeNotificacion) -> None:
        self.guardados += 1
        self.filas[plantilla.id] = copy(plantilla)

    async def buscar_por_id(self, plantilla_id: UUID) -> PlantillaDeNotificacion | None:
        fila = self.filas.get(plantilla_id)
        return copy(fila) if fila is not None else None

    async def buscar_por_codigo(self, codigo: str) -> PlantillaDeNotificacion | None:
        return next((copy(una) for una in self.filas.values() if una.codigo == codigo), None)

    async def buscar_por_meta_id(self, meta_plantilla_id: str) -> PlantillaDeNotificacion | None:
        return next(
            (
                copy(una)
                for una in self.filas.values()
                if una.meta_plantilla_id == meta_plantilla_id
            ),
            None,
        )

    async def buscar_por_nombre_en_meta(
        self, nombre: str, idioma: str
    ) -> PlantillaDeNotificacion | None:
        return next(
            (
                copy(una)
                for una in self.filas.values()
                if una.nombre_en_meta == nombre and una.idioma == idioma
            ),
            None,
        )

    async def listar(self) -> list[PlantillaDeNotificacion]:
        return sorted((copy(una) for una in self.filas.values()), key=lambda una: una.codigo)


__all__ = ["RepositorioPlantillasEnMemoria"]
