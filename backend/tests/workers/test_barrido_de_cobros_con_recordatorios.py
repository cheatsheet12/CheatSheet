"""El reparto del barrido de cobros incluye las empresas con recordatorios en espera (U7, N3).

Una empresa cuyo único cobro se pagó mientras su recordatorio esperaba el reintento no tiene nada
«abierto» por el lado de los cobros: si el reparto solo mirara cobros abiertos, esa fila no se
descartaría ni se resolvería nunca.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers import tasks_payments

pytestmark = pytest.mark.asyncio


def _empresa() -> EmpresaId:
    return EmpresaId(uuid4())


def _preparar(
    monkeypatch: pytest.MonkeyPatch,
    *,
    con_cobros: list[EmpresaId],
    con_recordatorios: list[EmpresaId],
) -> list[EmpresaId]:
    encoladas: list[EmpresaId] = []

    @asynccontextmanager
    async def sesion_sin_empresa(_: object) -> AsyncIterator[object]:
        yield object()

    async def cobros(_: object) -> list[EmpresaId]:
        return con_cobros

    async def recordatorios(_: object) -> list[EmpresaId]:
        return con_recordatorios

    monkeypatch.setattr(tasks_payments, "sesion_sin_empresa", sesion_sin_empresa)
    monkeypatch.setattr(tasks_payments, "empresas_con_cobros_abiertos", cobros)
    monkeypatch.setattr(tasks_payments, "empresas_con_recordatorios_en_espera", recordatorios)
    monkeypatch.setattr(
        tasks_payments, "_encolar_empresa", lambda _settings, empresa: encoladas.append(empresa)
    )
    return encoladas


def _recursos() -> Recursos:
    return cast(Recursos, SimpleNamespace(sesiones=object(), settings=object()))


async def test_una_empresa_con_solo_un_recordatorio_en_espera_recibe_su_tarea(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    con_cobro, solo_recordatorio = _empresa(), _empresa()
    encoladas = _preparar(
        monkeypatch, con_cobros=[con_cobro], con_recordatorios=[solo_recordatorio]
    )

    repartidas = await tasks_payments.barrer_cobros(_recursos())

    assert repartidas == 2
    assert encoladas == [con_cobro, solo_recordatorio]


async def test_una_empresa_en_las_dos_listas_recibe_una_sola_tarea(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambas, otra = _empresa(), _empresa()
    encoladas = _preparar(monkeypatch, con_cobros=[ambas], con_recordatorios=[otra, ambas])

    repartidas = await tasks_payments.barrer_cobros(_recursos())

    assert repartidas == 2
    assert encoladas == [ambas, otra]


async def test_sin_nada_abierto_no_se_reparte_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    encoladas = _preparar(monkeypatch, con_cobros=[], con_recordatorios=[])

    assert await tasks_payments.barrer_cobros(_recursos()) == 0
    assert encoladas == []
