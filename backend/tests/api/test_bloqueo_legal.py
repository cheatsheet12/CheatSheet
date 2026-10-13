"""The block while a legal document is pending (HU-E1-03 RN-03, HU-E1-08 RN-05): case 27.

The decision of *who* owes *what* is `documentos_pendientes`, tested in the domain. What is under
test here is the middleware's translation: with something pending every authenticated route
answers 403 `AceptacionLegalPendiente`, except the short, explicit list that lets the person
read the situation, accept, and sign out.
"""

from __future__ import annotations

import httpx
import pytest
from cheatsheet.api.middleware.empresa import RUTAS_CON_PENDIENTES, EmpresaMiddleware
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal
from fastapi import FastAPI

from tests.api.verificador_falso import VerificadorDeSesionFalso, autorizacion
from tests.conftest import settings_de_prueba

_BLOQUEO = {
    "error": "AceptacionLegalPendiente",
    "detalle": "Debe aceptar los documentos legales vigentes para continuar.",
}


def _app(verificador: VerificadorDeSesionFalso) -> FastAPI:
    """Only the middleware and one stub per route: nothing else can answer in its place."""
    app = FastAPI()
    app.add_middleware(EmpresaMiddleware, settings=settings_de_prueba(), verificador=verificador)
    rutas = (
        ("GET", "/auth/empresa"),
        ("PUT", "/auth/empresa"),
        ("GET", "/legal/pendientes"),
        ("POST", "/legal/aceptaciones"),
        ("GET", "/legal/aceptaciones"),
        ("GET", "/clientes"),
        ("POST", "/comprobantes"),
    )
    for metodo, ruta in rutas:
        app.add_api_route(ruta, _ok, methods=[metodo])
    return app


async def _ok() -> dict[str, str]:
    return {"ok": "si"}


def _cliente(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [("GET", "/clientes"), ("POST", "/comprobantes"), ("PUT", "/auth/empresa")],
)
async def test_con_pendientes_cualquier_ruta_autenticada_responde_403(metodo: str, ruta: str):
    verificador = VerificadorDeSesionFalso(pendientes=frozenset({DocumentoLegal.PRIVACIDAD}))
    app = _app(verificador)

    async with _cliente(app) as cliente:
        respuesta = await cliente.request(metodo, ruta, headers=autorizacion(settings_de_prueba()))

    assert respuesta.status_code == 403
    assert respuesta.json() == {**_BLOQUEO, "pendientes": ["PRIVACIDAD"]}


@pytest.mark.asyncio
async def test_el_403_nombra_todos_los_documentos_pendientes_en_orden_estable():
    app = _app(VerificadorDeSesionFalso(pendientes=frozenset(DocumentoLegal)))

    async with _cliente(app) as cliente:
        respuesta = await cliente.get("/clientes", headers=autorizacion(settings_de_prueba()))

    assert respuesta.json()["pendientes"] == ["PRIVACIDAD", "TERMINOS"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("GET", "/auth/empresa"),
        ("GET", "/legal/pendientes"),
        ("POST", "/legal/aceptaciones"),
    ],
)
async def test_las_tres_rutas_de_la_lista_pasan_con_pendientes(metodo: str, ruta: str):
    app = _app(VerificadorDeSesionFalso(pendientes=frozenset(DocumentoLegal)))

    async with _cliente(app) as cliente:
        respuesta = await cliente.request(metodo, ruta, headers=autorizacion(settings_de_prueba()))

    assert respuesta.status_code == 200


def test_la_lista_es_exactamente_la_del_plan():
    assert {
        ("GET", "/auth/empresa"),
        ("GET", "/legal/pendientes"),
        ("POST", "/legal/aceptaciones"),
    } == RUTAS_CON_PENDIENTES


@pytest.mark.asyncio
async def test_la_lista_es_por_metodo_y_ruta_exactos():
    app = _app(VerificadorDeSesionFalso(pendientes=frozenset({DocumentoLegal.TERMINOS})))

    async with _cliente(app) as cliente:
        otra_ruta = await cliente.get(
            "/legal/aceptaciones", headers=autorizacion(settings_de_prueba())
        )

    assert otra_ruta.status_code == 403


@pytest.mark.asyncio
async def test_sin_pendientes_todo_pasa():
    app = _app(VerificadorDeSesionFalso())

    async with _cliente(app) as cliente:
        respuesta = await cliente.get("/clientes", headers=autorizacion(settings_de_prueba()))

    assert respuesta.status_code == 200


@pytest.mark.asyncio
async def test_sin_sesion_sigue_siendo_401_y_no_403():
    """The block is for a person who is signed in; someone who is not learns nothing of it."""
    app = _app(VerificadorDeSesionFalso(pendientes=frozenset(DocumentoLegal)))

    async with _cliente(app) as cliente:
        respuesta = await cliente.get("/clientes")

    assert respuesta.status_code == 401
