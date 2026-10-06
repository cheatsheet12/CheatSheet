"""El pedido explícito de hablar con una persona (HU-E8-05 RN-01).

La derivación se produce cuando el cliente **la solicita explícitamente**. Se decide acá, sin
modelo: es la única intención que no puede depender de un modelo que quizá no entienda, porque
quien la expresa ya se cansó de él.

Pero «sin modelo» no es «por subcadenas»: «soy una persona que quiere un turno» nombra a una
persona y no la pide. La regla pide dos cosas en la **misma cláusula**: un destinatario
(`un asesor`, `con una persona`, `atención humana`) y un verbo de pedido que lo preceda a pocas
palabras (`quiero`, `hablar`, `pasame`…). Un mensaje que es sólo el destinatario (`un asesor`)
también cuenta: es un pedido escrito en telegrama.

Función pura, sin I/O ni framework (R1). El vocabulario es una lista cerrada: agregar una palabra
es una línea más un caso de test. Un pedido muy indirecto no escala por acá; si el modelo
tampoco lo entiende, escala por baja confianza. Un falso positivo (escalar a quien quería un
turno) es peor que un falso negativo que igual termina en una persona.
"""

from __future__ import annotations

import re
import unicodedata

_DESTINATARIO = (
    r"(?:(?:un|una|con)\s+(?:persona|humano|humana|asesor|asesora|operador|operadora)"
    r"|atencion\s+humana)"
)
_VERBO_DE_PEDIDO = (
    r"(?:quiero|necesito|prefiero|hablar|comunicarme|pasame|paseme|pasenme|derivame"
    r"|que\s+me\s+atienda)"
)
#: Cuántas palabras pueden separar al verbo del destinatario («quiero hablar con una persona»).
_PALABRAS_ENTRE = 3

_PEDIDO = re.compile(
    rf"\b{_VERBO_DE_PEDIDO}\b(?:\s+\w+){{0,{_PALABRAS_ENTRE}}}\s+{_DESTINATARIO}\b"
    r"|\bhablar\s+con\s+alguien\b"
)
_SOLO_EL_DESTINATARIO = re.compile(rf"{_DESTINATARIO}")
_CORTESIA = re.compile(r"\b(?:por\s+favor|porfa|porfavor|gracias|hola|buenas)\b")
_SEPARADOR_DE_CLAUSULA = re.compile(r"[.,;:!?¿¡()\n\r]+")


def pide_una_persona(texto: str) -> bool:
    """`True` si el cliente **pide** una persona; nombrarla no alcanza."""
    return any(_pide(clausula) for clausula in _clausulas(texto))


def _clausulas(texto: str) -> list[str]:
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    sin_tildes = "".join(letra for letra in sin_tildes if not unicodedata.combining(letra))
    partes = (" ".join(parte.split()) for parte in _SEPARADOR_DE_CLAUSULA.split(sin_tildes))
    return [parte for parte in partes if parte]


def _pide(clausula: str) -> bool:
    if _PEDIDO.search(clausula) is not None:
        return True
    # Telegrama: lo único que dice la cláusula es el destinatario (más cortesías).
    resto = " ".join(_CORTESIA.sub(" ", clausula).split())
    return _SOLO_EL_DESTINATARIO.fullmatch(resto) is not None


__all__ = ["pide_una_persona"]
