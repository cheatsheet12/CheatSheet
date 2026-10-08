"""El barrido de recordatorios de turno: reparto, tarea por empresa y Beat (U8, casos 27 y 31).

Ni Redis ni PostgreSQL: la sesión sin empresa, el fan-out y la unidad de trabajo se inyectan. Lo que se
afirma es lo que la tarea aporta por encima del caso de uso:

1. Una tarea por empresa con algo por recordar, sin repetidas, y un broker caído no rompe el reparto.
2. **Una empresa sin WhatsApp conectado sale con `recordatorios_de_turno_sin_canal` antes de armar el
   caso de uso** (caso 27): ninguna fila, ningún hilo.
3. `recordar-turnos` está en Beat, en la cola `notifications`, con el intervalo de configuración.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import structlog
from cheatsheet.contexts.conversational.infrastructure.canal import SinCanal
from cheatsheet.contexts.scheduling.application.recordatorios import ResultadoDeBarrido
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers import tasks_scheduling
from cheatsheet.workers.beat import programacion
from kombu.exceptions import OperationalError
from structlog.testing import capture_logs

from tests.conftest import INSTANTE_FIJO, settings_de_prueba
from tests.logs import logger_nuevo

pytestmark = pytest.mark.asyncio


@dataclass
class _Recursos:
    settings: Settings
    reloj: RelojFijo
    sesiones: object = None


@dataclass(frozen=True)
class _Unidad:
    sesion: None
    publicador: None
    reloj: RelojFijo


class TestElReparto:
    async def test_una_tarea_por_empresa_sin_repetidas_y_hasta_168_horas_adelante(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a, b = EmpresaId(uuid4()), EmpresaId(uuid4())
        encoladas: list[EmpresaId] = []
        horizontes: list[datetime] = []

        @asynccontextmanager
        async def sesion_sin_empresa(_sesiones: object) -> AsyncIterator[None]:
            yield None

        async def con_algo_por_recordar(_sesion: object, hasta: datetime) -> list[EmpresaId]:
            horizontes.append(hasta)
            return [a, b, a]

        monkeypatch.setattr(tasks_scheduling, "sesion_sin_empresa", sesion_sin_empresa)
        monkeypatch.setattr(
            tasks_scheduling, "empresas_con_turnos_por_recordar", con_algo_por_recordar
        )
        monkeypatch.setattr(
            tasks_scheduling, "_encolar_empresa", lambda _s, empresa: encoladas.append(empresa)
        )

        cantidad = await tasks_scheduling.recordar_turnos(
            _Recursos(settings_de_prueba(), RelojFijo(INSTANTE_FIJO))  # type: ignore[arg-type]
        )

        assert cantidad == 2
        assert encoladas == [a, b]
        assert horizontes == [INSTANTE_FIJO + timedelta(hours=168)]

    async def test_cada_empresa_se_encola_en_la_cola_de_notificaciones(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empresa = EmpresaId(uuid4())
        enviados: list[dict[str, Any]] = []

        class DespachadorEspia:
            def send_task(self, nombre: str, **kwargs: Any) -> None:
                enviados.append({"nombre": nombre, **kwargs})

        monkeypatch.setattr(tasks_scheduling, "crear_celery", lambda _: DespachadorEspia())

        tasks_scheduling._encolar_empresa(settings_de_prueba(), empresa)

        assert enviados[0]["nombre"] == tasks_scheduling.NOMBRE_EMPRESA
        assert enviados[0]["kwargs"] == {"empresa_id": str(empresa)}
        assert enviados[0]["queue"] == "notifications"

    async def test_un_broker_caido_no_rompe_el_reparto(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class DespachadorCaido:
            def send_task(self, *_args: Any, **_kwargs: Any) -> None:
                raise OperationalError("no hay broker")

        monkeypatch.setattr(tasks_scheduling, "crear_celery", lambda _: DespachadorCaido())

        tasks_scheduling._encolar_empresa(settings_de_prueba(), EmpresaId(uuid4()))


class TestLaTareaDeUnaEmpresa:
    @pytest.fixture(autouse=True)
    def _logger(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        """Un logger nuevo y **sin filtro de nivel**: otro test pudo dejar la configuración en WARNING."""
        anterior = structlog.get_config()["wrapper_class"]
        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(0))
        logger_nuevo(monkeypatch, tasks_scheduling)
        yield
        structlog.configure(wrapper_class=anterior)

    def _preparar(
        self, monkeypatch: pytest.MonkeyPatch, empresa: EmpresaId, canal: object
    ) -> list[object]:
        armados: list[object] = []

        async def unidad_de_trabajo(
            _recursos: object, empresa_id: EmpresaId
        ) -> AsyncIterator[_Unidad]:
            assert empresa_id == empresa
            yield _Unidad(None, None, RelojFijo(INSTANTE_FIJO))

        async def armar_mensajeria(
            _unidad: object, _settings: object, *, empresa_id: EmpresaId
        ) -> object:
            assert empresa_id == empresa
            return canal

        class _Barrido:
            async def ejecutar(
                self, *, empresa_id: EmpresaId, ahora: datetime
            ) -> ResultadoDeBarrido:
                assert (empresa_id, ahora) == (empresa, INSTANTE_FIJO)
                return ResultadoDeBarrido(enviados=2, fallidos=1)

        def armar(_unidad: object, *, empresa_id: EmpresaId, canal: object) -> _Barrido:
            armados.append(canal)
            return _Barrido()

        monkeypatch.setattr(tasks_scheduling, "unidad_de_trabajo", unidad_de_trabajo)
        monkeypatch.setattr(tasks_scheduling, "armar_mensajeria", armar_mensajeria)
        monkeypatch.setattr(tasks_scheduling, "armar_recordatorios_de_turno", armar)
        return armados

    async def test_una_empresa_sin_whatsapp_sale_con_su_log_antes_de_armar_nada(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**Caso 27.**"""
        empresa = EmpresaId(uuid4())
        armados = self._preparar(monkeypatch, empresa, SinCanal())

        with capture_logs() as logs:
            enviados = await tasks_scheduling.recordar_empresa(
                _Recursos(settings_de_prueba(), RelojFijo(INSTANTE_FIJO)),  # type: ignore[arg-type]
                empresa,
            )

        assert enviados == 0
        assert armados == []
        (registro,) = [u for u in logs if u["event"] == "recordatorios_de_turno_sin_canal"]
        assert registro["empresa_id"] == str(empresa)

    async def test_con_el_canal_conectado_corre_el_barrido_de_esa_empresa(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empresa = EmpresaId(uuid4())
        canal = object()
        armados = self._preparar(monkeypatch, empresa, canal)

        with capture_logs() as logs:
            enviados = await tasks_scheduling.recordar_empresa(
                _Recursos(settings_de_prueba(), RelojFijo(INSTANTE_FIJO)),  # type: ignore[arg-type]
                empresa,
            )

        assert enviados == 2
        assert armados == [canal]
        (resumen,) = [u for u in logs if u["event"] == "recordatorios_de_turno"]
        assert (resumen["enviados"], resumen["fallidos"]) == (2, 1)
        assert "telefono" not in resumen


class TestBeat:
    async def test_recordar_turnos_va_a_notificaciones_con_el_intervalo_configurado(self) -> None:
        """**Caso 31.**"""
        settings = replace(settings_de_prueba(), recordatorio_de_turno_minutos=10)

        entrada = programacion(settings)["recordar-turnos"]

        assert entrada["task"] == tasks_scheduling.NOMBRE_BARRIDO
        assert entrada["schedule"].total_seconds() == 10 * 60
        assert entrada["options"]["queue"] == "notifications"

    async def test_por_defecto_corre_cada_15_minutos(self) -> None:
        entrada = programacion(settings_de_prueba())["recordar-turnos"]

        assert entrada["schedule"].total_seconds() == 15 * 60

    async def test_un_intervalo_de_cero_no_programa_una_corrida_continua(self) -> None:
        settings = replace(settings_de_prueba(), recordatorio_de_turno_minutos=0)

        entrada = programacion(settings)["recordar-turnos"]

        assert entrada["schedule"].total_seconds() == 60
