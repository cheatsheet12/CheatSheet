"""Cableado de `conversational` sobre una unidad de trabajo.

Sólo los cinco repositorios. **El intérprete, el canal, los embeddings y los dos ACL no se
arman acá**: el modelo sale de `platform`, el canal necesita el token que administra
`integrations`, y los ACL cruzan a `scheduling` y `master_data` — y la infraestructura de un
contexto no puede meter mano en la de otro (R3). Se arman en `api/conversacional.py`, el
composition root, que es la única capa que puede cablear dos contextos.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.conversational.application.ports import (
    PortRepositorioConversacion,
    PortRepositorioEscalamiento,
    PortRepositorioFAQ,
    PortRepositorioMensaje,
    PortUsosDeFAQ,
)
from cheatsheet.contexts.conversational.infrastructure.repositories import (
    RepositorioConversacionPostgres,
    RepositorioEscalamientoPostgres,
    RepositorioFAQPostgres,
)
from cheatsheet.contexts.conversational.infrastructure.repositorio_mensaje import (
    RepositorioMensajePostgres,
)
from cheatsheet.contexts.conversational.infrastructure.usos_de_faq import (
    RepositorioUsosDeFAQPostgres,
)


@dataclass(frozen=True, slots=True)
class Conversaciones:
    """Las piezas que necesita un request, atadas a una transacción."""

    conversaciones: PortRepositorioConversacion
    mensajes: PortRepositorioMensaje
    escalamientos: PortRepositorioEscalamiento
    faqs: PortRepositorioFAQ
    usos: PortUsosDeFAQ

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> Conversaciones:
        return cls(
            conversaciones=RepositorioConversacionPostgres(unidad.sesion),
            mensajes=RepositorioMensajePostgres(unidad.sesion),
            escalamientos=RepositorioEscalamientoPostgres(unidad.sesion),
            faqs=RepositorioFAQPostgres(unidad.sesion),
            usos=RepositorioUsosDeFAQPostgres(unidad.sesion),
        )


__all__ = ["Conversaciones"]
