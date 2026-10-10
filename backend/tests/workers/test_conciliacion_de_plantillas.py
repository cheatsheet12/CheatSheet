"""El barrido y la tarea por empresa de la conciliación de plantillas (U6, casos 16 y 17).

Ni Redis ni PostgreSQL: la sesión sin empresa, el fan-out y la unidad de trabajo se inyectan. Lo que
se afirma es lo que la tarea aporta por encima del caso de uso: una tarea por empresa **conectada**,
un broker caído que no rompe el reparto, la conciliación de **una** empresa con **su** cuenta de
Meta, y la entrada de Beat.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.contexts.business_config.application.conciliacion import ResumenDeConciliacion
from cheatsheet.platform.settings import ConfiguracionFaltante, Settings
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers import tasks_business_config
from cheatsheet.workers.beat import programacion
from kombu.exceptions import OperationalError

from tests.conftest import INSTANTE_FIJO, settings_de_prueba

pytestmark = pytest.mark.asyncio


@dataclass
class _Recursos:
    settings: Settings
    sesiones: object = None


async def test_beat_programa_la_conciliacion_con_el_intervalo_configurado() -> None:
    settings = replace(settings_de_prueba(), whatsapp_plantillas_minutos=20)

    entrada = programacion(settings)["conciliar-plantillas-de-whatsapp"]

    assert entrada["task"] == tasks_business_config.NOMBRE_BARRIDO
    # Anchored to the wall clock like every other Beat entry, so the staging database can sleep.
    assert entrada["schedule"].minute == set(range(0, 60, 20))
    assert entrada["options"]["queue"] == "integrations_sync"


async def test_un_intervalo_de_cero_no_llega_a_beat_porque_falla_al_arrancar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before, 0 was floored to one minute at schedule time; now the boot refuses it outright."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "k" * 44)
    monkeypatch.setenv("WHATSAPP_PLANTILLAS_MINUTOS", "0")

    with pytest.raises(ConfiguracionFaltante, match="WHATSAPP_PLANTILLAS_MINUTOS"):
        Settings.desde_entorno()


async def test_el_barrido_encola_una_tarea_por_empresa_con_whatsapp_conectado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conectadas = [EmpresaId(uuid4()), EmpresaId(uuid4())]
    encoladas: list[EmpresaId] = []

    @asynccontextmanager
    async def sesion_sin_empresa(_sesiones: object) -> AsyncIterator[None]:
        yield None

    async def con_whatsapp(_sesion: object) -> list[EmpresaId]:
        return conectadas

    monkeypatch.setattr(tasks_business_config, "sesion_sin_empresa", sesion_sin_empresa)
    monkeypatch.setattr(tasks_business_config, "empresas_con_whatsapp_conectado", con_whatsapp)
    monkeypatch.setattr(
        tasks_business_config, "_encolar_empresa", lambda _s, empresa: encoladas.append(empresa)
    )

    cantidad = await tasks_business_config.conciliar_plantillas(_Recursos(settings_de_prueba()))  # type: ignore[arg-type]

    assert cantidad == 2
    assert encoladas == conectadas


async def test_cada_empresa_se_encola_en_la_cola_de_integraciones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empresa = EmpresaId(uuid4())
    enviados: list[dict[str, Any]] = []

    class DespachadorEspia:
        def send_task(self, nombre: str, **kwargs: Any) -> None:
            enviados.append({"nombre": nombre, **kwargs})

    monkeypatch.setattr(tasks_business_config, "_despachador", lambda _: DespachadorEspia())

    tasks_business_config._encolar_empresa(settings_de_prueba(), empresa)

    assert enviados[0]["nombre"] == tasks_business_config.NOMBRE_EMPRESA
    assert enviados[0]["kwargs"] == {"empresa_id": str(empresa)}
    assert enviados[0]["queue"] == "integrations_sync"


async def test_un_broker_caido_no_rompe_el_reparto(monkeypatch: pytest.MonkeyPatch) -> None:
    """La empresa que no se pudo encolar se reintenta en la próxima corrida."""

    class DespachadorCaido:
        def send_task(self, *_args: Any, **_kwargs: Any) -> None:
            raise OperationalError("no hay broker")

    monkeypatch.setattr(tasks_business_config, "_despachador", lambda _: DespachadorCaido())

    tasks_business_config._encolar_empresa(settings_de_prueba(), EmpresaId(uuid4()))


async def test_la_tarea_de_una_empresa_concilia_con_la_cuenta_de_esa_empresa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 16 (raíz): la conciliación de A usa la revisión que se armó **para A**."""
    empresa = EmpresaId(uuid4())
    armadas: list[EmpresaId] = []
    conciliadas: list[tuple[EmpresaId, datetime]] = []
    revision_de_a = object()

    @dataclass(frozen=True)
    class _Unidad:
        sesion: None
        publicador: None
        reloj: RelojFijo

    async def unidad_de_trabajo(_recursos: object, empresa_id: EmpresaId) -> AsyncIterator[_Unidad]:
        assert empresa_id == empresa
        yield _Unidad(None, None, RelojFijo(INSTANTE_FIJO))

    async def armar_revision(
        _unidad: object, _settings: object, *, empresa_id: EmpresaId
    ) -> object:
        armadas.append(empresa_id)
        return revision_de_a

    class _Conciliacion:
        def __init__(self, plantillas: object, revision: object) -> None:
            del plantillas
            assert revision is revision_de_a

        async def ejecutar(
            self, *, empresa_id: EmpresaId, ahora: datetime
        ) -> ResumenDeConciliacion:
            conciliadas.append((empresa_id, ahora))
            return ResumenDeConciliacion(enviadas=6)

    class _Piezas:
        plantillas = object()

        @classmethod
        def armar(cls, _unidad: object) -> type[_Piezas]:
            return cls

    monkeypatch.setattr(tasks_business_config, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(tasks_business_config, "armar_revision_de_meta", armar_revision)
    monkeypatch.setattr(tasks_business_config, "ConciliarPlantillasConMeta", _Conciliacion)
    monkeypatch.setattr(tasks_business_config, "ConfiguracionDeNegocio", _Piezas)

    resumen = await tasks_business_config.conciliar_empresa(
        _Recursos(settings_de_prueba()),  # type: ignore[arg-type]
        empresa,
    )

    assert armadas == [empresa]
    assert conciliadas == [(empresa, INSTANTE_FIJO)]
    assert resumen.enviadas == 6
