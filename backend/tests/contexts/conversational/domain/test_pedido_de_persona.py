"""HU-E8-05 RN-01: se escala cuando el cliente pide una persona, no cuando la nombra."""

from __future__ import annotations

import pytest
from cheatsheet.contexts.conversational.domain.pedido_de_persona import pide_una_persona


@pytest.mark.parametrize(
    "texto",
    [
        "soy una persona que quiere un turno",
        "mi mamá es una persona mayor, ¿tienen rampa?",
        "el asesor me dijo que viniera el martes",
        "hablé con alguien ayer",
        "necesito asesoramiento contable",
        "¿cuánto sale el personal trainer?",
        "",
    ],
)
def test_nombrar_a_una_persona_no_es_pedirla(texto: str) -> None:
    assert pide_una_persona(texto) is False


@pytest.mark.parametrize(
    "texto",
    [
        "quiero hablar con una persona por favor",
        "hablar con alguien",
        "pasame con un humano",
        "necesito un asesor",
        "Quiero hablar con un ASESOR!",
        "atención humana",
        "ATENCION HUMANA",
        "un asesor",
        "una persona por favor",
        "que me atienda una persona",
        "Hola, buenas tardes. Prefiero hablar con una persona",
    ],
)
def test_pedir_una_persona_se_detecta(texto: str) -> None:
    assert pide_una_persona(texto) is True
