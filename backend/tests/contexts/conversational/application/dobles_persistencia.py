"""Los dobles de persistencia de `conversational`: repositorios y usos de FAQ en memoria.

Como en el resto del sistema: implementaciones de verdad de los puertos y no `Mock`, porque un
`Mock` satisface cualquier interfaz, incluida una que ya no existe.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    EstadoConversacion,
    Mensaje,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    ESTADOS_SIN_AGENTE,
    Escalamiento,
)
from cheatsheet.contexts.conversational.domain.faq import FAQ, CoincidenciaDeFAQ
from cheatsheet.contexts.conversational.domain.uso_de_faq import ConteoDeUsos, UsoDeFAQ
from cheatsheet.shared.zona_horaria import MesCalendario


@asynccontextmanager
async def sin_savepoint() -> AsyncIterator[None]:
    """El `aislar` de los tests en memoria: no hay base, así que no hay savepoint que abrir."""
    yield


class RepositorioConversacionEnMemoria:
    def __init__(self, *hilos: Conversacion) -> None:
        self.hilos: dict[UUID, Conversacion] = {uno.id: uno for uno in hilos}
        #: Con qué `bloquear` se pidió el hilo cada vez: el agente lo pide bloqueado (T10).
        self.bloqueos: list[bool] = []

    async def agregar(self, conversacion: Conversacion) -> None:
        self.hilos[conversacion.id] = conversacion

    async def guardar(self, conversacion: Conversacion) -> None:
        self.hilos[conversacion.id] = conversacion

    async def buscar_por_id(self, conversacion_id: UUID) -> Conversacion | None:
        return self.hilos.get(conversacion_id)

    async def abierta_de(self, cliente_id: UUID, *, bloquear: bool = False) -> Conversacion | None:
        self.bloqueos.append(bloquear)
        return next(
            (
                uno
                for uno in self.hilos.values()
                if uno.cliente_id == cliente_id and uno.estado is EstadoConversacion.ACTIVA
            ),
            None,
        )

    async def listar(self, *, solo_escaladas: bool = False) -> list[Conversacion]:
        del solo_escaladas
        return list(self.hilos.values())


class RepositorioMensajeEnMemoria:
    def __init__(self, *mensajes: Mensaje) -> None:
        self.mensajes: dict[UUID, Mensaje] = {uno.id: uno for uno in mensajes}
        #: El `para_actualizar` de cada `buscar_por_externo_id`: si se pidió la fila bloqueada.
        self.busquedas_por_externo_id: list[bool] = []

    async def agregar(self, mensaje: Mensaje) -> None:
        self.mensajes[mensaje.id] = mensaje

    async def guardar(self, mensaje: Mensaje) -> None:
        self.mensajes[mensaje.id] = mensaje

    async def buscar_por_externo_id(
        self, externo_id: str, *, para_actualizar: bool = False
    ) -> Mensaje | None:
        self.busquedas_por_externo_id.append(para_actualizar)
        return next((uno for uno in self.mensajes.values() if uno.externo_id == externo_id), None)

    async def del_hilo(self, conversacion_id: UUID) -> list[Mensaje]:
        del_hilo = [uno for uno in self.mensajes.values() if uno.conversacion_id == conversacion_id]
        return sorted(del_hilo, key=lambda uno: uno.momento)

    @property
    def salientes(self) -> list[Mensaje]:
        return [uno for uno in self.mensajes.values() if uno.origen is not None]


class RepositorioEscalamientoEnMemoria:
    def __init__(self, *escalamientos: Escalamiento) -> None:
        self.escalamientos: dict[UUID, Escalamiento] = {uno.id: uno for uno in escalamientos}

    async def agregar(self, escalamiento: Escalamiento) -> None:
        self.escalamientos[escalamiento.id] = escalamiento

    async def guardar(self, escalamiento: Escalamiento) -> None:
        self.escalamientos[escalamiento.id] = escalamiento

    async def buscar_por_id(self, escalamiento_id: UUID) -> Escalamiento | None:
        return self.escalamientos.get(escalamiento_id)

    async def abierto_de(self, conversacion_id: UUID) -> Escalamiento | None:
        return next(
            (
                uno
                for uno in self.escalamientos.values()
                if uno.conversacion_id == conversacion_id and uno.estado in ESTADOS_SIN_AGENTE
            ),
            None,
        )

    async def listar_abiertos(self) -> list[Escalamiento]:
        return [uno for uno in self.escalamientos.values() if uno.esta_abierto]


class RepositorioFAQEnMemoria:
    """FAQ en un dict, con una búsqueda que **no entiende significados**.

    Devuelve las coincidencias que se le programaron. Fingir una búsqueda semántica en Python
    haría que los tests de HU-E8-03 RN-02 pasaran probando la imitación y no la consulta, que
    corre contra PostgreSQL y se prueba en `tests/integracion/`.
    """

    def __init__(self, *faqs: FAQ) -> None:
        self.faqs: dict[UUID, FAQ] = {una.id: una for una in faqs}
        self.coincidencias: list[CoincidenciaDeFAQ] = []
        self.vectores: dict[UUID, list[float]] = {}
        #: Cuántas veces se pidió `guardar`: el agente no debe escribir la fila de la FAQ.
        self.guardados = 0

    async def agregar(self, faq: FAQ) -> None:
        self.faqs[faq.id] = faq

    async def guardar(self, faq: FAQ) -> None:
        self.guardados += 1
        self.faqs[faq.id] = faq

    async def guardar_vector(self, faq: FAQ, vector: Sequence[float]) -> None:
        self.faqs[faq.id] = faq
        self.vectores[faq.id] = list(vector)

    async def eliminar(self, faq_id: UUID) -> None:
        self.faqs.pop(faq_id, None)
        self.vectores.pop(faq_id, None)

    async def buscar_por_id(self, faq_id: UUID) -> FAQ | None:
        return self.faqs.get(faq_id)

    async def listar(self) -> list[FAQ]:
        return list(self.faqs.values())

    async def buscar_por_significado(
        self, vector: Sequence[float], *, limite: int = 3
    ) -> list[CoincidenciaDeFAQ]:
        del vector
        return self.coincidencias[:limite]

    async def pendientes_de_indexar(self) -> list[FAQ]:
        return [una for una in self.faqs.values() if una.embedding_obsoleto]


class UsosDeFAQEnMemoria:
    """Los usos de FAQ en una lista, con la misma idempotencia por mensaje que la tabla."""

    def __init__(self) -> None:
        self.usos: list[UsoDeFAQ] = []

    async def registrar(self, uso: UsoDeFAQ) -> None:
        if all(otro.mensaje_id != uso.mensaje_id for otro in self.usos):
            self.usos.append(uso)

    async def conteos(self, mes: MesCalendario) -> dict[UUID, ConteoDeUsos]:
        anterior = mes.anterior()
        por_faq: dict[UUID, list[UsoDeFAQ]] = {}
        for uso in self.usos:
            por_faq.setdefault(uso.faq_id, []).append(uso)
        return {
            faq_id: ConteoDeUsos(
                este_mes=sum(mes.inicio <= u.usado_en < mes.fin for u in usos),
                mes_anterior=sum(anterior.inicio <= u.usado_en < anterior.fin for u in usos),
                desde_el_seguimiento=len(usos),
            )
            for faq_id, usos in por_faq.items()
        }

    async def contar(self, *, desde: datetime, hasta: datetime, faq_id: UUID | None) -> int:
        return sum(
            desde <= uso.usado_en < hasta and (faq_id is None or uso.faq_id == faq_id)
            for uso in self.usos
        )


__all__ = [
    "RepositorioConversacionEnMemoria",
    "RepositorioEscalamientoEnMemoria",
    "RepositorioFAQEnMemoria",
    "RepositorioMensajeEnMemoria",
    "UsosDeFAQEnMemoria",
    "sin_savepoint",
]
