"""The public legal routes (HU-E1-03 RN-04/05, HU-E1-08 RN-06): cases 5 and 6 of the plan."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.api.middleware.empresa import RUTAS_PUBLICAS
from cheatsheet.contexts.identity.application.errors import MotivoDeRevocacion, SesionRevocada
from cheatsheet.contexts.identity.domain.legal import DocumentoLegal
from cheatsheet.shared.clock import RelojFijo
from fastapi import APIRouter, FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.api.verificador_falso import VerificadorDeSesionFalso, autorizacion
from tests.conftest import settings_de_prueba

#: After the first versions take effect (2026-10-10).
_HOY = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


def _app(verificador: VerificadorDeSesionFalso) -> FastAPI:
    settings = settings_de_prueba()
    recursos = Recursos(
        settings=settings,
        engine=cast(AsyncEngine, None),
        sesiones=cast("async_sessionmaker[AsyncSession]", None),
        redis=cast(Redis, None),
        reloj=RelojFijo(_HOY),
    )
    app = create_app(settings, recursos, verificador)
    interna = APIRouter(prefix="/legal")

    @interna.get("/interna")
    async def interna_de_prueba() -> dict[str, str]:
        return {"ok": "si"}

    app.include_router(interna)
    return app


def _cliente(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ------------------------------------------------------------------------------- case 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ruta", "documento", "version"),
    [("/legal/terminos", "TERMINOS", "1.1"), ("/legal/privacidad", "PRIVACIDAD", "1.0")],
)
async def test_los_textos_se_leen_sin_token(ruta: str, documento: str, version: str):
    verificador = VerificadorDeSesionFalso(
        error=SesionRevocada(MotivoDeRevocacion.USUARIO_INEXISTENTE)
    )

    async with _cliente(_app(verificador)) as cliente:
        respuesta = await cliente.get(ruta)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["documento"] == documento
    assert cuerpo["version"] == version
    assert cuerpo["vigente_desde"] == "2026-10-10"
    assert cuerpo["borrador"] is True
    assert cuerpo["texto"].startswith("## ")
    assert verificador.llamadas == [], "a public route must not ask the session verifier"


@pytest.mark.asyncio
async def test_las_versiones_vigentes_se_leen_sin_token():
    async with _cliente(_app(VerificadorDeSesionFalso())) as cliente:
        respuesta = await cliente.get("/legal/vigentes")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "terminos": {"version": "1.1", "vigente_desde": "2026-10-10", "borrador": True},
        "privacidad": {"version": "1.0", "vigente_desde": "2026-10-10", "borrador": True},
    }


def test_las_rutas_publicas_de_legal_son_exactas_y_no_un_prefijo():
    legales = {ruta for ruta in RUTAS_PUBLICAS if ruta.startswith("/legal")}

    assert legales == {"/legal/terminos", "/legal/privacidad", "/legal/vigentes"}


# ------------------------------------------------------------------------------- case 6


@pytest.mark.asyncio
async def test_otra_ruta_bajo_legal_exige_sesion():
    app = _app(VerificadorDeSesionFalso())

    async with _cliente(app) as cliente:
        sin_token = await cliente.get("/legal/interna")
        con_token = await cliente.get("/legal/interna", headers=autorizacion(settings_de_prueba()))

    assert sin_token.status_code == 401
    assert con_token.status_code == 200


@pytest.mark.asyncio
async def test_una_ruta_legal_inexistente_sin_token_tambien_da_401():
    async with _cliente(_app(VerificadorDeSesionFalso())) as cliente:
        respuesta = await cliente.get("/legal/pendientes")

    assert respuesta.status_code == 401


# ------------------------------------------------------ pending documents (case 27, slice 3)


@pytest.mark.asyncio
async def test_pendientes_dice_que_versiones_debe_aceptar_la_persona():
    verificador = VerificadorDeSesionFalso(pendientes=frozenset(DocumentoLegal))

    async with _cliente(_app(verificador)) as cliente:
        respuesta = await cliente.get(
            "/legal/pendientes", headers=autorizacion(settings_de_prueba())
        )

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "pendientes": [
            {
                "documento": "PRIVACIDAD",
                "version": "1.0",
                "vigente_desde": "2026-10-10",
                "borrador": True,
            },
            {
                "documento": "TERMINOS",
                "version": "1.1",
                "vigente_desde": "2026-10-10",
                "borrador": True,
            },
        ]
    }


@pytest.mark.asyncio
async def test_pendientes_esta_vacio_cuando_la_persona_esta_al_dia():
    async with _cliente(_app(VerificadorDeSesionFalso())) as cliente:
        respuesta = await cliente.get(
            "/legal/pendientes", headers=autorizacion(settings_de_prueba())
        )

    assert respuesta.json() == {"pendientes": []}


@pytest.mark.asyncio
async def test_aceptar_con_un_documento_desconocido_es_422():
    verificador = VerificadorDeSesionFalso(pendientes=frozenset(DocumentoLegal))

    async with _cliente(_app(verificador)) as cliente:
        respuesta = await cliente.post(
            "/legal/aceptaciones",
            json={"documentos": [{"documento": "OTRO", "version": "1.0"}]},
            headers=autorizacion(settings_de_prueba()),
        )

    assert respuesta.status_code == 422
