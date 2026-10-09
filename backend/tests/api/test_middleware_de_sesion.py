"""The middleware's per-request session check, through the real ASGI app (cases 6 to 8, 10 to 13).

The verifier is a fake injected through `create_app(..., verificador=...)`, so what is under
test is the middleware's *translation*: which outcome becomes which status, what reaches
`request.state`, and what never reaches a response or a log. The decision itself is
`VerificarSesionVigente`, tested in `tests/contexts/identity/application`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.api.middleware import empresa
from cheatsheet.contexts.identity.application.errors import MotivoDeRevocacion, SesionRevocada
from cheatsheet.contexts.identity.application.verificacion_de_sesion import IdentidadVigente
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from fastapi import APIRouter, FastAPI, Request
from redis.asyncio import Redis
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.api.verificador_falso import VerificadorDeSesionFalso, token_firmado
from tests.conftest import INSTANTE_FIJO, settings_de_prueba
from tests.contexts.identity.base_falsa import EscenarioDeBase, fabrica_de_sesiones, fila

_RUTA = "/prueba/yo"
_SIN_SESION = {"error": "NoAutenticado", "detalle": "Se requiere iniciar sesion."}
_NO_DISPONIBLE = {
    "error": "ServicioNoDisponible",
    "detalle": "No pudimos verificar tu sesion. Reintenta en unos segundos.",
}


class _LoggerEspia:
    """Records what the middleware logs.

    `structlog` is configured with `cache_logger_on_first_use` and a level filter fixed the
    first time a logger is used, so capturing from the real one depends on which test ran
    before. Replacing the module's logger makes the assertion about the middleware only.
    """

    def __init__(self) -> None:
        self.registros: list[tuple[str, str, dict[str, Any]]] = []

    def info(self, evento: str, **campos: Any) -> None:
        self.registros.append(("info", evento, campos))

    def error(self, evento: str, **campos: Any) -> None:
        self.registros.append(("error", evento, campos))


class _RedisQueFalla:
    """Any use at all is a failure: if the session check ever touches Redis, it shows."""

    def __init__(self) -> None:
        self.usos = 0

    def __getattr__(self, nombre: str) -> Any:
        self.usos += 1
        raise ConnectionError("Redis no responde")


def _recursos(
    settings: Settings,
    *,
    redis: object | None = None,
    sesiones: async_sessionmaker[AsyncSession] | None = None,
) -> Recursos:
    return Recursos(
        settings=settings,
        engine=cast(AsyncEngine, None),
        sesiones=sesiones or cast("async_sessionmaker[AsyncSession]", None),
        redis=cast(Redis, redis),
        reloj=RelojFijo(INSTANTE_FIJO),
    )


def _router() -> tuple[APIRouter, list[str]]:
    """A protected route that reports what the middleware put on `request.state`."""
    router = APIRouter(prefix="/prueba")
    ejecuciones: list[str] = []

    @router.get("/yo")
    async def yo(request: Request) -> dict[str, str]:
        ejecuciones.append("corrio")
        return {
            "rol": request.state.rol,
            "usuario_id": str(request.state.usuario_id),
            "empresa_id": str(request.state.empresa_id),
        }

    return router, ejecuciones


def _app(
    verificador: VerificadorDeSesionFalso | None, settings: Settings | None = None
) -> tuple[FastAPI, Settings, list[str]]:
    settings = settings or settings_de_prueba()
    app = create_app(settings, _recursos(settings), verificador)
    router, ejecuciones = _router()
    app.include_router(router)
    return app, settings, ejecuciones


def _cliente(app: FastAPI, *, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    transporte = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return httpx.AsyncClient(transport=transporte, base_url="http://test")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------- caso 6: revocada es un 401 indistinguible


@pytest.mark.asyncio
@pytest.mark.parametrize("motivo", list(MotivoDeRevocacion))
async def test_una_sesion_revocada_da_el_mismo_401_que_una_sin_token(motivo: MotivoDeRevocacion):
    verificador = VerificadorDeSesionFalso(error=SesionRevocada(motivo))
    app, settings, ejecuciones = _app(verificador)

    async with _cliente(app) as cliente:
        sin_token = await cliente.get(_RUTA)
        revocada = await cliente.get(_RUTA, headers=_bearer(token_firmado(settings)))

    assert revocada.status_code == 401
    assert revocada.json() == sin_token.json() == _SIN_SESION
    assert motivo.value not in revocada.text, "the reason must never reach the caller"
    assert ejecuciones == []


# ------------------------------- caso 7: el rol (y la identidad) son los de la base, no los del token


@pytest.mark.asyncio
async def test_la_ruta_ve_el_rol_de_la_base_y_no_el_del_token():
    verificador = VerificadorDeSesionFalso(rol=RolUsuario.OPERADOR)
    app, settings, _ = _app(verificador)

    async with _cliente(app) as cliente:
        respuesta = await cliente.get(
            _RUTA, headers=_bearer(token_firmado(settings, rol="ADMINISTRADOR"))
        )

    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "OPERADOR"


@pytest.mark.asyncio
async def test_la_empresa_y_el_usuario_tambien_salen_del_verificador():
    de_la_base = IdentidadVigente(
        empresa_id=EmpresaId(uuid4()), usuario_id=UsuarioId(uuid4()), rol=RolUsuario.SOLO_LECTURA
    )
    app, settings, _ = _app(VerificadorDeSesionFalso(devuelve=de_la_base))

    async with _cliente(app) as cliente:
        respuesta = await cliente.get(_RUTA, headers=_bearer(token_firmado(settings)))

    assert respuesta.json() == {
        "rol": "SOLO_LECTURA",
        "usuario_id": str(de_la_base.usuario_id),
        "empresa_id": str(de_la_base.empresa_id),
    }


@pytest.mark.asyncio
async def test_el_verificador_recibe_las_reclamaciones_firmadas_del_token():
    usuario_id, empresa_id = UsuarioId(uuid4()), EmpresaId(uuid4())
    verificador = VerificadorDeSesionFalso()
    app, settings, _ = _app(verificador)
    token = token_firmado(settings, usuario_id=usuario_id, empresa_id=empresa_id)

    async with _cliente(app) as cliente:
        await cliente.get(_RUTA, headers=_bearer(token))

    assert verificador.llamadas == [(usuario_id, empresa_id)]


# --------------------------------------- caso 8: si no se puede verificar, cerrado y con 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [OSError("conexion rechazada"), SQLAlchemyError("base caida"), TimeoutError()],
    ids=["OSError", "SQLAlchemyError", "TimeoutError"],
)
async def test_si_la_verificacion_no_puede_correr_es_un_503_y_la_ruta_no_corre(error: Exception):
    app, settings, ejecuciones = _app(VerificadorDeSesionFalso(error=error))

    async with _cliente(app) as cliente:
        respuesta = await cliente.get(_RUTA, headers=_bearer(token_firmado(settings)))

    assert respuesta.status_code == 503
    assert respuesta.json() == _NO_DISPONIBLE
    assert ejecuciones == [], "fail-closed: the route must not run when the check could not"


@pytest.mark.asyncio
async def test_un_error_inesperado_del_verificador_no_se_disfraza_de_200():
    """Only infrastructure errors are listed. Anything else is a bug, and a bug answers 500."""
    app, settings, ejecuciones = _app(VerificadorDeSesionFalso(error=RuntimeError("bug")))

    async with _cliente(app, raise_app_exceptions=False) as cliente:
        respuesta = await cliente.get(_RUTA, headers=_bearer(token_firmado(settings)))

    assert respuesta.status_code == 500
    assert ejecuciones == []


# ----------------------------------------- caso 10: las rutas públicas no pasan por la base


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("GET", "/health"),
        ("POST", "/auth/login"),
        ("POST", f"/webhooks/mercadopago/{uuid4()}"),
        ("GET", "/contador/un-token"),
    ],
)
async def test_las_rutas_publicas_no_invocan_al_verificador(
    metodo: str, ruta: str, monkeypatch: pytest.MonkeyPatch
):
    async def sonda(_: object) -> bool:
        return True

    monkeypatch.setattr("cheatsheet.api.routers.health.verificar_conexion", sonda)
    monkeypatch.setattr("cheatsheet.api.routers.health.verificar_redis", sonda)
    verificador = VerificadorDeSesionFalso()
    app, settings, _ = _app(verificador)

    # The routes behind these have no database to talk to here, so what they answer is
    # irrelevant: the point is that the session check never ran, even holding a valid token.
    async with _cliente(app, raise_app_exceptions=False) as cliente:
        await cliente.request(metodo, ruta, headers=_bearer(token_firmado(settings)), json={})

    assert verificador.llamadas == []


# ------------------------- caso 11: un token que ni siquiera es válido no llega a la base


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caso", ["firma_mala", "vencido", "sin_bearer", "sin_cabecera"], ids=lambda c: c
)
async def test_un_token_invalido_es_401_sin_invocar_al_verificador(caso: str):
    verificador = VerificadorDeSesionFalso()
    app, settings, ejecuciones = _app(verificador)
    cabeceras: dict[str, str] = {}
    if caso == "firma_mala":
        cabeceras = _bearer(token_firmado(settings, secreto="fake-secret-of-another-issuer"))
    elif caso == "vencido":
        hace_una_hora = datetime.now(UTC) - timedelta(hours=1)
        cabeceras = _bearer(token_firmado(settings, ahora=hace_una_hora))
    elif caso == "sin_bearer":
        cabeceras = {"Authorization": token_firmado(settings)}

    async with _cliente(app) as cliente:
        respuesta = await cliente.get(_RUTA, headers=cabeceras)

    assert respuesta.status_code == 401
    assert respuesta.json() == _SIN_SESION
    assert verificador.llamadas == []
    assert ejecuciones == []


# ------------------------------------------ caso 12: Redis no interviene en la verificación


@pytest.mark.asyncio
async def test_con_redis_caido_una_sesion_valida_sigue_autenticando():
    """The check reads PostgreSQL and nothing else. This is the guard against someone adding a
    cache later: with Redis down the session would stop authenticating, or worse, open up."""
    settings = settings_de_prueba()
    redis = _RedisQueFalla()
    empresa_id, usuario_id = EmpresaId(uuid4()), UsuarioId(uuid4())
    escenario = EscenarioDeBase(fila=fila(empresa_id, rol="OPERADOR"))
    # No verifier injected: the real wiring of `create_app`, over a fake session factory.
    recursos = _recursos(settings, redis=redis, sesiones=fabrica_de_sesiones(escenario))
    app = create_app(settings, recursos)
    router, _ = _router()
    app.include_router(router)
    token = token_firmado(settings, usuario_id=usuario_id, empresa_id=empresa_id)

    async with _cliente(app) as cliente:
        respuesta = await cliente.get(_RUTA, headers=_bearer(token))

    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "OPERADOR"
    assert redis.usos == 0
    assert escenario.empresas_anunciadas == [str(empresa_id)]
    assert (escenario.abiertas, escenario.cerradas) == (0, 1), "the check kept its connection"


@pytest.mark.asyncio
async def test_por_defecto_create_app_arma_el_verificador_de_postgres_y_revoca():
    """Wired for real: the stored user is not `ACTIVO`, so the token no longer authorizes."""
    settings = settings_de_prueba()
    empresa_id = EmpresaId(uuid4())
    escenario = EscenarioDeBase(fila=fila(empresa_id, estado="INACTIVO"))
    app = create_app(settings, _recursos(settings, sesiones=fabrica_de_sesiones(escenario)))
    router, ejecuciones = _router()
    app.include_router(router)

    async with _cliente(app) as cliente:
        respuesta = await cliente.get(
            _RUTA, headers=_bearer(token_firmado(settings, empresa_id=empresa_id))
        )

    assert respuesta.status_code == 401
    assert respuesta.json() == _SIN_SESION
    assert ejecuciones == []


# --------------------------------------------- caso 13: el log lleva el motivo y nada más


@pytest.mark.asyncio
async def test_el_log_de_rechazo_lleva_el_motivo_y_no_el_token_ni_el_email(
    monkeypatch: pytest.MonkeyPatch,
):
    espia = _LoggerEspia()
    monkeypatch.setattr(empresa, "logger", espia)
    verificador = VerificadorDeSesionFalso(
        error=SesionRevocada(MotivoDeRevocacion.USUARIO_INACTIVO)
    )
    app, settings, _ = _app(verificador)
    token = token_firmado(settings)

    async with _cliente(app) as cliente:
        await cliente.get(_RUTA, headers=_bearer(token))

    assert espia.registros == [
        ("info", "sesion_revocada", {"motivo": "usuario_inactivo", "ruta": _RUTA})
    ]
    assert token not in str(espia.registros)
    assert "@" not in str(espia.registros), "no email may reach the log"


@pytest.mark.asyncio
async def test_una_verificacion_que_no_pudo_correr_se_registra_como_error(
    monkeypatch: pytest.MonkeyPatch,
):
    espia = _LoggerEspia()
    monkeypatch.setattr(empresa, "logger", espia)
    error = OSError("conexion rechazada")
    app, settings, _ = _app(VerificadorDeSesionFalso(error=error))
    token = token_firmado(settings)

    async with _cliente(app) as cliente:
        await cliente.get(_RUTA, headers=_bearer(token))

    assert espia.registros == [
        (
            "error",
            "verificacion_de_sesion_no_disponible",
            {"tipo": "OSError", "ruta": _RUTA, "exc_info": error},
        )
    ]
    assert token not in str(espia.registros)
