"""`POST /reporteria/reportes` must let the transaction commit when generation fails.

D65: a report that could not be built or stored stays in the history as `FALLIDO`.
`GenerarReporte` writes that row and then raises `GeneracionFallida`. `unidad_de_trabajo`
commits only if the request body finishes *without* an exception, so a route that lets the
error escape the `async for` throws the `FALLIDO` row away and no evidence of the failure
remains.

These tests run without a database. They replace the unit of work with a double that
reproduces its one relevant contract (commit if and only if the body ends cleanly) and keep
the real `GenerarReporte`. The double is checked on its own
(`test_el_doble_no_confirma_si_el_cuerpo_levanta`) so the red of the first test is known to
come from the router and not from a broken double. The PostgreSQL proof is in
`tests/integracion/test_api_reporteria.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.contexts.identity.infrastructure.seguridad import EmisorDeTokensJWT
from cheatsheet.contexts.reporting.application.errors import GeneracionFallida
from cheatsheet.contexts.reporting.application.ports import FilaDeReporte
from cheatsheet.contexts.reporting.domain.reporte import MENSAJE_SIN_DATOS, EstadoReporte
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from fastapi import FastAPI

from tests.api.verificador_falso import VerificadorDeSesionFalso
from tests.conftest import INSTANTE_FIJO, settings_de_prueba
from tests.contexts.reporting.application.dobles import (
    ArchivosEnMemoria,
    BitacoraFalsa,
    CobranzasFalsas,
    FacturacionFalsa,
    RepositorioReportesEnMemoria,
)

_RUTA = "/reporteria/reportes"
_CUERPO = {"tipo": "FACTURACION", "formato": "CSV"}
_FILAS = [FilaDeReporte({"fecha": "05/03/2026", "cliente": "Kiosco El Sol", "total": "3000.00"})]


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
    commit line is never reached: exactly the behaviour that loses the `FALLIDO` row.
    """
    estado.abierta += 1
    yield _Unidad(reloj=RelojFijo(INSTANTE_FIJO))
    estado.confirmo = True


@dataclass
class _Escenario:
    transaccion: _Transaccion
    reportes: RepositorioReportesEnMemoria
    settings: Settings
    app: FastAPI
    #: Vouches for the token's user (no database here); `_pedir` sets the role it answers.
    verificador: VerificadorDeSesionFalso


def _armar(monkeypatch: pytest.MonkeyPatch, *, filas: list[FilaDeReporte]) -> _Escenario:
    from cheatsheet.api.routers import reporteria

    estado = _Transaccion()
    reportes = RepositorioReportesEnMemoria()
    archivos = ArchivosEnMemoria()
    archivos.falla = True

    class _Piezas:
        def __init__(self) -> None:
            self.reportes = reportes
            self.archivos = archivos

    def unidad_de_trabajo(*_: Any) -> AsyncIterator[_Unidad]:
        return _unidad_doble(estado)

    class ReporteriaFalsa:
        @staticmethod
        def armar(*_: Any) -> _Piezas:
            return _Piezas()

    monkeypatch.setattr(reporteria, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(reporteria, "Reporteria", ReporteriaFalsa)
    monkeypatch.setattr(reporteria, "armar_facturacion", lambda *_: FacturacionFalsa(filas=filas))
    monkeypatch.setattr(reporteria, "armar_cobranzas", lambda *_: CobranzasFalsas())
    monkeypatch.setattr(reporteria, "armar_bitacora", lambda *_: BitacoraFalsa())

    settings = settings_de_prueba()
    recursos = Recursos(
        settings=settings,
        engine=None,  # type: ignore[arg-type]  # never dereferenced: everything is replaced
        sesiones=None,  # type: ignore[arg-type]
        redis=None,  # type: ignore[arg-type]
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    verificador = VerificadorDeSesionFalso()
    app = create_app(settings, recursos, verificador)
    return _Escenario(estado, reportes, settings, app, verificador)


def _autorizacion(settings: Settings, rol: str) -> dict[str, str]:
    """A genuinely signed token, so `EmpresaMiddleware` fills `request.state`."""
    emisor = EmisorDeTokensJWT(secreto=settings.jwt_secret, vida_acceso=timedelta(minutes=15))
    token = emisor.emitir_acceso(
        usuario_id=UsuarioId(uuid4()),
        empresa_id=EmpresaId(uuid4()),
        rol=rol,
        ahora=datetime.now(UTC),
    )
    return {"Authorization": f"Bearer {token.valor}"}


async def _pedir(escenario: _Escenario, rol: str = "ADMINISTRADOR") -> httpx.Response:
    escenario.verificador.rol = RolUsuario(rol)
    transporte = httpx.ASGITransport(app=escenario.app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        return await cliente.post(
            _RUTA, json=_CUERPO, headers=_autorizacion(escenario.settings, rol)
        )


@pytest.mark.asyncio
async def test_un_fallo_de_generacion_confirma_la_fila_fallida_y_responde_el_error(
    monkeypatch: pytest.MonkeyPatch,
):
    escenario = _armar(monkeypatch, filas=_FILAS)

    respuesta = await _pedir(escenario)

    assert escenario.transaccion.confirmo is True, "the FALLIDO row was thrown away"
    assert respuesta.status_code == 422
    assert respuesta.json()["error"] == GeneracionFallida.__name__
    estados = [uno.estado for uno in escenario.reportes.reportes.values()]
    assert estados == [EstadoReporte.FALLIDO]


@pytest.mark.asyncio
async def test_un_periodo_sin_datos_sigue_descartando_la_transaccion(
    monkeypatch: pytest.MonkeyPatch,
):
    """Only `GeneracionFallida` is caught: an empty period wrote nothing and rolls back."""
    escenario = _armar(monkeypatch, filas=[])

    respuesta = await _pedir(escenario)

    assert escenario.transaccion.confirmo is False
    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == MENSAJE_SIN_DATOS


@pytest.mark.asyncio
async def test_un_rechazo_por_rol_sigue_descartando_la_transaccion(
    monkeypatch: pytest.MonkeyPatch,
):
    escenario = _armar(monkeypatch, filas=_FILAS)

    respuesta = await _pedir(escenario, rol="SOLO_LECTURA")

    assert escenario.transaccion.confirmo is False
    assert respuesta.status_code == 422
    assert escenario.reportes.reportes == {}


async def _cuerpo_que_levanta(estado: _Transaccion) -> None:
    async for _unidad in _unidad_doble(estado):
        raise GeneracionFallida("x")


@pytest.mark.asyncio
async def test_el_doble_no_confirma_si_el_cuerpo_levanta():
    """Guard for the double: a raising body must not commit, or the red above proves nothing."""
    estado = _Transaccion()

    with pytest.raises(GeneracionFallida):
        await _cuerpo_que_levanta(estado)

    assert estado.abierta == 1
    assert estado.confirmo is False
