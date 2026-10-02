"""`POST /auth/refresh` must let the transaction commit when it detects token reuse.

ADR-011: presenting a refresh token that was already rotated revokes its whole family.
`RefrescarSesion` writes that revocation and then raises. `unidad_de_trabajo` commits only
if the request body finishes *without* an exception, so a route that lets the error
escape the `async for` throws the revocation away and the thief keeps a live session.

These tests run without a database. They replace the unit of work with a double that
reproduces its one relevant contract — commit if and only if the body ends cleanly — and
`RefrescarSesion` with a double that raises. The double is checked on its own
(`test_el_doble_no_confirma_si_el_cuerpo_levanta`) so the red of the first test is known to
come from the router and not from a broken double. The PostgreSQL proof is in
`tests/integracion/test_api_sesiones.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.identity.application.errors import (
    ReusoDeRefreshDetectado,
    SesionInvalida,
)
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from fastapi import FastAPI

from tests.conftest import INSTANTE_FIJO, settings_de_prueba

_RUTA = "/auth/refresh"
_CUERPO = {"refresh_token": "cualquiera"}


@dataclass
class _Transaccion:
    """What the double observed: did the unit of work commit?"""

    confirmo: bool = False
    abierta: int = 0


@dataclass(frozen=True)
class _Unidad:
    reloj: RelojFijo
    publicador: None = None


async def _unidad_doble(estado: _Transaccion) -> AsyncIterator[_Unidad]:
    """Mimics `sesion_de_empresa`: the commit sits after the `yield`.

    If the consumer's body raises, the generator is never resumed past the `yield`, so the
    commit line is never reached — exactly the behaviour that loses the revocation.
    """
    estado.abierta += 1
    yield _Unidad(reloj=RelojFijo(INSTANTE_FIJO))
    estado.confirmo = True


class _PiezasFalsas:
    """`Identidad.armar` result: only what the refresh route touches before the use case."""

    usuarios = refrescos = tokens = emisor = None


def _armar_app(monkeypatch: pytest.MonkeyPatch, error: Exception) -> tuple[FastAPI, _Transaccion]:
    from cheatsheet.api.routers import auth

    estado = _Transaccion()

    async def empresa_de_refresh(*_: Any) -> EmpresaId:
        return EmpresaId(uuid4())

    def unidad_de_trabajo(*_: Any) -> AsyncIterator[_Unidad]:
        return _unidad_doble(estado)

    class RefrescarSesionQueLevanta:
        def __init__(self, **_: Any) -> None: ...

        async def ejecutar(self, **_: Any) -> None:
            raise error

    class IdentidadFalsa:
        @staticmethod
        def armar(*_: Any) -> _PiezasFalsas:
            return _PiezasFalsas()

    monkeypatch.setattr(auth, "empresa_de_refresh", empresa_de_refresh)
    monkeypatch.setattr(auth, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(auth, "RefrescarSesion", RefrescarSesionQueLevanta)
    monkeypatch.setattr(auth, "Identidad", IdentidadFalsa)

    settings = settings_de_prueba()
    recursos = Recursos(
        settings=settings,
        engine=None,  # type: ignore[arg-type]  # never dereferenced: everything is replaced
        sesiones=None,  # type: ignore[arg-type]
        redis=None,  # type: ignore[arg-type]
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    return create_app(settings, recursos), estado


def _cliente(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_el_reuso_confirma_la_revocacion_y_responde_el_error_de_reuso(
    monkeypatch: pytest.MonkeyPatch,
):
    app, estado = _armar_app(
        monkeypatch, ReusoDeRefreshDetectado("El refresh token ya habia sido usado")
    )

    async with _cliente(app) as cliente:
        respuesta = await cliente.post(_RUTA, json=_CUERPO)

    assert estado.confirmo is True, "the family revocation was thrown away with the transaction"
    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "ReusoDeRefreshDetectado"


@pytest.mark.asyncio
async def test_un_rechazo_que_no_es_reuso_sigue_descartando_la_transaccion(
    monkeypatch: pytest.MonkeyPatch,
):
    """Only reuse is caught: any other refusal wrote nothing and keeps rolling back."""
    app, estado = _armar_app(monkeypatch, SesionInvalida("El refresh token esta vencido"))

    async with _cliente(app) as cliente:
        respuesta = await cliente.post(_RUTA, json=_CUERPO)

    assert estado.confirmo is False
    assert respuesta.json()["error"] == "SesionInvalida"


async def _cuerpo_que_levanta(estado: _Transaccion) -> None:
    async for _unidad in _unidad_doble(estado):
        raise ReusoDeRefreshDetectado("x")


@pytest.mark.asyncio
async def test_el_doble_no_confirma_si_el_cuerpo_levanta():
    """Guard for the double: a raising body must not commit, or the red above proves nothing."""
    estado = _Transaccion()

    with pytest.raises(ReusoDeRefreshDetectado):
        await _cuerpo_que_levanta(estado)

    assert estado.abierta == 1
    assert estado.confirmo is False
