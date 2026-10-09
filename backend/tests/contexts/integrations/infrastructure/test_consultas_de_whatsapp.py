"""Las dos lecturas entre empresas que trae `plantillas-de-whatsapp-en-meta` (U6, caso 29).

Cada una es una función `SECURITY DEFINER` que devuelve **ids de empresa y nada más**. Que la
base las ejecute con el rol de la aplicación lo prueba `tests/integracion/test_migracion_0037.py`;
acá se prueba la forma del pedido: la función que se llama, que el id de la WABA viaje como
**parámetro** (nunca pegado al SQL) y que lo que vuelve se traduzca a `EmpresaId`.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    empresas_con_whatsapp_conectado,
    empresas_de_la_cuenta_de_whatsapp,
)
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio


class _Resultado:
    def __init__(self, filas: list[tuple[Any, ...]]) -> None:
        self._filas = filas

    def all(self) -> list[tuple[Any, ...]]:
        return self._filas


class _Sesion:
    def __init__(self, *filas: tuple[Any, ...]) -> None:
        self._filas = list(filas)
        self.pedidos: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, sentencia: Any, parametros: dict[str, Any] | None = None) -> _Resultado:
        self.pedidos.append((str(sentencia), parametros or {}))
        return _Resultado(self._filas)


async def test_las_empresas_con_whatsapp_conectado_salen_de_la_funcion_sin_argumentos() -> None:
    una, otra = uuid4(), uuid4()
    sesion = _Sesion((una,), (otra,))

    empresas = await empresas_con_whatsapp_conectado(sesion)  # type: ignore[arg-type]

    assert empresas == [EmpresaId(una), EmpresaId(otra)]
    ((sql, parametros),) = sesion.pedidos
    assert "empresas_con_whatsapp_conectado()" in sql
    assert parametros == {}


async def test_la_empresa_de_una_waba_viaja_con_el_id_como_parametro() -> None:
    empresa = uuid4()
    sesion = _Sesion((empresa,))
    waba = "1234'; DROP TABLE empresa; --"

    empresas = await empresas_de_la_cuenta_de_whatsapp(sesion, waba)  # type: ignore[arg-type]

    assert empresas == [EmpresaId(empresa)]
    ((sql, parametros),) = sesion.pedidos
    assert "empresa_de_la_cuenta_de_whatsapp(:waba_id)" in sql
    assert parametros == {"waba_id": waba}
    assert "DROP" not in sql


async def test_una_waba_sin_dueno_devuelve_una_lista_vacia() -> None:
    assert await empresas_de_la_cuenta_de_whatsapp(_Sesion(), "999") == []  # type: ignore[arg-type]
