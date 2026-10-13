"""La segunda validación de la respuesta del modelo (ADR-0007, `CLAUDE.md` §5).

Estos son los tests que más importan de la unidad, y no porque el modelo se equivoque
seguido: porque cuando se equivoque, lo va a hacer **una vez** y el resultado se va a
aplicar a cuarenta mil filas. `CLAUDE.md` §5 dice que la salida de un modelo es entrada no
confiable, igual que un formulario, y esto es esa frase escrita como código.

No se llama a la API en ninguno de estos casos: se le pasa a `_interpretar` una respuesta
armada a mano, que es exactamente la forma que tiene una respuesta real.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from cheatsheet.contexts.spreadsheet_sync.infrastructure.modelo import (
    ESQUEMA_DE_MAPEO,
    ConfiguracionDelModelo,
    ModeloDeLenguajeAnthropic,
    _interpretar,
)

COLUMNAS = ("Razon Social", "CUIT")
ATRIBUTOS = ("nombre", "cuit", "contacto_email")


@dataclass(frozen=True)
class BloqueDeTexto:
    text: str
    type: str = "text"


@dataclass(frozen=True)
class RespuestaFalsa:
    """The shape of a real answer: a list of content blocks."""

    content: list[Any]


def _respuesta(cuerpo: str) -> RespuestaFalsa:
    return RespuestaFalsa(content=[BloqueDeTexto(text=cuerpo)])


def test_una_respuesta_valida_se_interpreta() -> None:
    respuesta = _respuesta(
        '{"asignaciones": ['
        '{"columna": "Razon Social", "atributo": "nombre", "confianza": 0.96},'
        '{"columna": "CUIT", "atributo": "cuit", "confianza": 0.99}]}'
    )

    asignaciones = _interpretar(respuesta, columnas=COLUMNAS, atributos=ATRIBUTOS)

    assert len(asignaciones) == 2
    assert asignaciones[0].atributo == "nombre"
    # `Decimal`, no `float`: el score se compara contra los umbrales por igualdad.
    assert asignaciones[0].score == Decimal("0.96")
    assert isinstance(asignaciones[0].score, Decimal)


def test_un_atributo_que_no_existe_se_descarta_en_vez_de_corregirse() -> None:
    """El caso que justifica la segunda validación.

    Si el modelo inventa `telefono_movil`, el esquema no lo detecta —es un string— y el
    procesamiento escribiría en un campo que no existe. Descartarlo cuesta una decisión
    manual; corregirlo por parecido metería un CUIT en el campo que más se le pareciera.
    """
    respuesta = _respuesta(
        '{"asignaciones": ['
        '{"columna": "Razon Social", "atributo": "nombre", "confianza": 0.96},'
        '{"columna": "CUIT", "atributo": "telefono_movil", "confianza": 0.91}]}'
    )

    asignaciones = _interpretar(respuesta, columnas=COLUMNAS, atributos=ATRIBUTOS)

    assert [a.columna for a in asignaciones] == ["Razon Social"]


def test_una_columna_que_no_preguntamos_se_descarta() -> None:
    """Un modelo que devuelve una columna de más está describiendo otra planilla."""
    respuesta = _respuesta(
        '{"asignaciones": [{"columna": "Inventada", "atributo": "nombre", "confianza": 0.99}]}'
    )

    assert _interpretar(respuesta, columnas=COLUMNAS, atributos=ATRIBUTOS) == ()


@pytest.mark.parametrize(
    "cuerpo",
    [
        "no soy json",
        "{}",
        '{"otra_cosa": []}',
        '{"asignaciones": "no es una lista"}',
    ],
)
def test_una_respuesta_que_no_cumple_el_esquema_no_propone_nada(cuerpo: str) -> None:
    """Y no revienta: devolver vacío es lo que deja al usuario mapeando a mano."""
    assert _interpretar(_respuesta(cuerpo), columnas=COLUMNAS, atributos=ATRIBUTOS) == ()


@pytest.mark.parametrize("confianza", ["1.5", "-0.2"])
def test_un_score_fuera_de_rango_se_descarta(confianza: str) -> None:
    respuesta = _respuesta(
        f'{{"asignaciones": [{{"columna": "CUIT", "atributo": "cuit", "confianza": {confianza}}}]}}'
    )

    assert _interpretar(respuesta, columnas=COLUMNAS, atributos=ATRIBUTOS) == ()


def test_una_entrada_malformada_no_se_lleva_puestas_a_las_demas() -> None:
    """Una asignación rota es una asignación menos, no una respuesta perdida."""
    respuesta = _respuesta(
        '{"asignaciones": ['
        '{"columna": "Razon Social"},'
        '{"columna": "CUIT", "atributo": "cuit", "confianza": 0.99}]}'
    )

    asignaciones = _interpretar(respuesta, columnas=COLUMNAS, atributos=ATRIBUTOS)

    assert [a.columna for a in asignaciones] == ["CUIT"]


def test_un_atributo_nulo_es_una_respuesta_valida() -> None:
    """«No sé qué es esta columna» es más útil que adivinar, y RN-03 ya lo dibuja."""
    respuesta = _respuesta(
        '{"asignaciones": [{"columna": "CUIT", "atributo": null, "confianza": 0.2}]}'
    )

    asignaciones = _interpretar(respuesta, columnas=COLUMNAS, atributos=ATRIBUTOS)

    assert len(asignaciones) == 1
    assert asignaciones[0].atributo is None


def test_una_respuesta_sin_bloque_de_texto_no_propone_nada() -> None:
    assert _interpretar(RespuestaFalsa(content=[]), columnas=COLUMNAS, atributos=ATRIBUTOS) == ()


def test_el_esquema_cierra_los_objetos_y_exige_los_tres_campos() -> None:
    """`additionalProperties: false` es lo que impide que el modelo agregue campos.

    Sin eso, una respuesta con un campo de más pasa la validación de la API y llega acá
    con datos que nadie pidió.
    """
    item = ESQUEMA_DE_MAPEO["properties"]["asignaciones"]["items"]

    assert ESQUEMA_DE_MAPEO["additionalProperties"] is False
    assert item["additionalProperties"] is False
    assert set(item["required"]) == {"columna", "atributo", "confianza"}
    # `null` es parte del contrato, no un accidente.
    assert item["properties"]["atributo"]["type"] == ["string", "null"]


@pytest.mark.asyncio
async def test_anthropic_mapping_uses_a_supported_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    class ProviderMessages:
        async def create(self, **kwargs: Any) -> RespuestaFalsa:
            schema = kwargs["output_config"]["format"]["schema"]
            confidence = schema["properties"]["asignaciones"]["items"]["properties"]["confianza"]
            if "minimum" in confidence or "maximum" in confidence:
                raise AssertionError("Anthropic rejects numeric constraints in raw JSON schemas")
            return _respuesta(
                '{"asignaciones": [{"columna": "CUIT", "atributo": "cuit", "confianza": 0.99}]}'
            )

    adapter = ModeloDeLenguajeAnthropic(
        ConfiguracionDelModelo(
            api_key="test-key", modelo="claude-sonnet-5-5", timeout_segundos=1, max_tokens=1024
        )
    )
    monkeypatch.setattr(adapter, "_cliente", SimpleNamespace(messages=ProviderMessages()))

    result = await adapter.proponer_mapeo(columnas=COLUMNAS, atributos=ATRIBUTOS)

    assert len(result) == 1
    assert result[0].columna == "CUIT"
    assert result[0].atributo == "cuit"
    assert result[0].score == Decimal("0.99")
