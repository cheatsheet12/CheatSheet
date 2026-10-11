"""Los dobles de `conversational`, escritos a mano: la fachada.

Los cuerpos viven por responsabilidad, y este módulo sólo los reexporta para que los tests
sigan importando desde un único lugar:

- `dobles_persistencia`: repositorios y usos de FAQ en memoria.
- `dobles_modelos`: el intérprete, la transcripción y los embeddings.
- `dobles_colaboradores`: el canal, el directorio y el publicador.
- `dobles_agenda`: `AgendaEnMemoria` y sus datos de prueba (decisión D38).
"""

from __future__ import annotations

from .dobles_agenda import (
    RECURSO_DE_PRUEBA,
    SERVICIO_DE_PRUEBA,
    AgendaEnMemoria,
    grilla_de,
    un_horario,
)
from .dobles_colaboradores import DirectorioEnMemoria, MensajeriaEnMemoria, PublicadorEnMemoria
from .dobles_modelos import EmbeddingsEnMemoria, InterpreteProgramado, TranscriptorProgramado
from .dobles_persistencia import (
    RepositorioConversacionEnMemoria,
    RepositorioEscalamientoEnMemoria,
    RepositorioFAQEnMemoria,
    RepositorioMensajeEnMemoria,
    UsosDeFAQEnMemoria,
    sin_savepoint,
)

__all__ = [
    "RECURSO_DE_PRUEBA",
    "SERVICIO_DE_PRUEBA",
    "AgendaEnMemoria",
    "DirectorioEnMemoria",
    "EmbeddingsEnMemoria",
    "InterpreteProgramado",
    "MensajeriaEnMemoria",
    "PublicadorEnMemoria",
    "RepositorioConversacionEnMemoria",
    "RepositorioEscalamientoEnMemoria",
    "RepositorioFAQEnMemoria",
    "RepositorioMensajeEnMemoria",
    "TranscriptorProgramado",
    "UsosDeFAQEnMemoria",
    "grilla_de",
    "sin_savepoint",
    "un_horario",
]
