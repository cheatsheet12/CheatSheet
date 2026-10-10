"""Los dobles que reemplazan al LLM, a la transcripción y a los embeddings.

**`InterpreteProgramado` devuelve lo que se le diga**, incluida una confianza cualquiera. Es lo
que permite probar los dos caminos que importan: el de creerle y el de no creerle. Registra lo
que **recibió** —el texto y el historial— porque es lo que afirma que no se filtran datos
personales ni respuestas a una oferta.
"""

from __future__ import annotations

from collections.abc import Sequence

from cheatsheet.contexts.conversational.application.ports import Lectura, Transcripcion
from cheatsheet.contexts.conversational.domain.conversacion import Intencion


class InterpreteProgramado:
    """Devuelve la lectura que se le puso. Registra qué vio, para poder afirmarlo.

    Con `programar` se le da una secuencia: cada llamada consume la siguiente, y la última se
    repite. Es lo que permite probar una conversación de varios mensajes.
    """

    def __init__(self, lectura: Lectura | None = None) -> None:
        self.cola: list[Lectura] = [
            lectura or Lectura(intencion=Intencion.DESCONOCIDA, confianza=0.0)
        ]
        self.vistos: list[str] = []
        self.historiales: list[list[str]] = []

    @property
    def lectura(self) -> Lectura:
        return self.cola[0]

    @lectura.setter
    def lectura(self, valor: Lectura) -> None:
        self.cola = [valor]

    def programar(self, *lecturas: Lectura) -> None:
        self.cola = list(lecturas)

    async def leer(self, texto: str, *, historial: Sequence[str] = ()) -> Lectura:
        self.vistos.append(texto)
        self.historiales.append(list(historial))
        return self.cola.pop(0) if len(self.cola) > 1 else self.cola[0]


class TranscriptorProgramado:
    def __init__(self, texto: str = "quiero un turno", calidad: float = 0.9) -> None:
        self.texto = texto
        self.calidad = calidad
        self.pedidos: list[str] = []

    async def transcribir(self, audio_id: str) -> Transcripcion:
        self.pedidos.append(audio_id)
        return Transcripcion(texto=self.texto, calidad=self.calidad)


class EmbeddingsEnMemoria:
    def __init__(self, *, cae: bool = False) -> None:
        self.cae = cae
        self.pedidos: list[str] = []

    @property
    def version(self) -> str:
        return "doble-v1"

    async def vectorizar(self, texto: str) -> list[float]:
        if self.cae:
            raise RuntimeError("el proveedor de embeddings no responde")
        self.pedidos.append(texto)
        return [0.1, 0.2, 0.3]


__all__ = ["EmbeddingsEnMemoria", "InterpreteProgramado", "TranscriptorProgramado"]
