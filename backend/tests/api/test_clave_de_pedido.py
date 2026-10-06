"""`X-Idempotency-Key` en el borde HTTP (ADR-0013, caso 8): obligatoria y un UUID.

Corre sin base: una app mínima con la dependencia y los manejadores de errores reales. El 422 sale
de `EntradaInvalida`, igual que en `POST /cobros`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

import httpx
import pytest
from cheatsheet.api.clave_de_pedido import (
    ENCABEZADO,
    MENSAJE_FALTA,
    MENSAJE_INVALIDA,
    exigir_clave_de_pedido,
)
from cheatsheet.api.errors import registrar_manejadores
from fastapi import Depends, FastAPI

pytestmark = pytest.mark.asyncio


def _app() -> FastAPI:
    app = FastAPI()
    registrar_manejadores(app)

    @app.post("/eco")
    async def eco(clave: Annotated[UUID, Depends(exigir_clave_de_pedido)]) -> dict[str, str]:
        return {"clave": str(clave)}

    return app


async def _post(encabezados: dict[str, str]) -> httpx.Response:
    transporte = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        return await cliente.post("/eco", headers=encabezados)


async def test_sin_encabezado_es_422_con_el_texto_del_adr() -> None:
    respuesta = await _post({})

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == MENSAJE_FALTA
    assert respuesta.json()["error"] == "ClaveDeIdempotenciaFaltante"


@pytest.mark.parametrize("valor", ["no-es-un-uuid", "123", "   "])
async def test_un_valor_que_no_es_uuid_es_422(valor: str) -> None:
    respuesta = await _post({ENCABEZADO: valor})

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] in (MENSAJE_INVALIDA, MENSAJE_FALTA)


async def test_un_uuid_valido_pasa_tal_cual() -> None:
    clave = uuid4()

    respuesta = await _post({ENCABEZADO: str(clave)})

    assert respuesta.status_code == 200
    assert respuesta.json() == {"clave": str(clave)}
