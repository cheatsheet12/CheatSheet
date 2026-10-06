"""Dobles en memoria de los puertos de las plantillas (U6)."""

from __future__ import annotations

from collections.abc import Mapping
from copy import copy
from uuid import UUID

from cheatsheet.contexts.business_config.application.ports import (
    EstadoEnMeta,
    RespuestaDeMeta,
)
from cheatsheet.contexts.business_config.domain.plantilla import PlantillaDeNotificacion
from cheatsheet.shared.events import EventoDeDominio


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


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


class RevisionDeMetaFalsa:
    """`PortRevisionDeMeta` programable: devuelve o levanta lo que se le diga, y anota los pedidos.

    `creaciones` y `ediciones` guardan lo que se mandó (nombre, cuerpo, ejemplos): son datos de la
    plantilla, nunca de un cliente.
    """

    def __init__(
        self,
        *,
        respuestas: list[RespuestaDeMeta | Exception] | None = None,
        estados: list[EstadoEnMeta] | Exception | None = None,
    ) -> None:
        self.respuestas = list(respuestas or [])
        self._estados = estados if estados is not None else []
        self.creaciones: list[tuple[str, str, str, Mapping[str, str]]] = []
        self.ediciones: list[tuple[str, str, Mapping[str, str]]] = []
        self.lecturas = 0

    def _siguiente(self) -> RespuestaDeMeta:
        """La que se programó; sin programar, una aprobada con un id propio por pedido."""
        if not self.respuestas:
            numero = len(self.creaciones) + len(self.ediciones)
            return RespuestaDeMeta(
                meta_plantilla_id=f"meta-{numero}", estado="APPROVED", categoria="UTILITY"
            )
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    async def crear(
        self, *, nombre: str, idioma: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDeMeta:
        self.creaciones.append((nombre, idioma, cuerpo, dict(ejemplos)))
        return self._siguiente()

    async def editar(
        self, *, meta_plantilla_id: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDeMeta:
        self.ediciones.append((meta_plantilla_id, cuerpo, dict(ejemplos)))
        return self._siguiente()

    async def estados(self) -> list[EstadoEnMeta]:
        self.lecturas += 1
        if isinstance(self._estados, Exception):
            raise self._estados
        return list(self._estados)


__all__ = ["PublicadorFalso", "RepositorioPlantillasEnMemoria", "RevisionDeMetaFalsa"]
