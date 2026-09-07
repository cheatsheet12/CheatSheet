"""El barrido mensual del paquete contable (HU-E10-04 RN-01 y RN-02).

Lo que se prueba sin base y sin broker: **el reparto**. Que la tarea por empresa se encole en
la cola que corresponde, que un fallo del broker no aborte el bucle —perder una empresa cuesta
una corrida; dejar escapar la excepción cuesta todas las que venían después— y que la entrada
de Beat exista con el nombre que el worker registra.

El barrido contra datos reales vive en `tests/integracion`: acá lo que importa es la mecánica
del reparto, que es la parte que corre sola a la hora en que nadie mira.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers import tasks_reporting
from cheatsheet.workers.beat import programacion
from cheatsheet.workers.celery_app import Cola
from kombu.exceptions import OperationalError

from tests.conftest import settings_de_prueba


class CeleryFalso:
    def __init__(self, *, falla: bool = False) -> None:
        self.enviadas: list[tuple[str, dict[str, Any], str]] = []
        self.falla = falla

    def send_task(self, nombre: str, *, kwargs: dict[str, Any], queue: str) -> None:
        if self.falla:
            raise OperationalError("el broker no responde")
        self.enviadas.append((nombre, kwargs, queue))


def test_encola_la_tarea_de_la_empresa(monkeypatch: pytest.MonkeyPatch) -> None:
    celery = CeleryFalso()
    monkeypatch.setattr(tasks_reporting, "crear_celery", lambda _: celery)
    empresa_id = EmpresaId(uuid4())

    tasks_reporting._encolar_empresa(settings_de_prueba(), empresa_id)

    assert celery.enviadas == [
        (
            tasks_reporting.NOMBRE_EMPRESA,
            {"empresa_id": str(empresa_id)},
            Cola.NOTIFICATIONS.value,
        )
    ]


def test_un_hipo_del_broker_no_aborta_el_reparto(monkeypatch: pytest.MonkeyPatch) -> None:
    """No levanta: la empresa siguiente del bucle tiene que llegar a encolarse."""
    monkeypatch.setattr(tasks_reporting, "crear_celery", lambda _: CeleryFalso(falla=True))
    tasks_reporting._encolar_empresa(settings_de_prueba(), EmpresaId(uuid4()))


def test_beat_programa_el_barrido() -> None:
    """La entrada existe y apunta al nombre que `registrar` ata.

    Un nombre que no coincide produce un scheduler que despacha una tarea que nadie atiende:
    los paquetes no salen y no hay error en ningún lado.
    """
    entrada = programacion(settings_de_prueba())["armar-paquetes-contables"]
    assert entrada["task"] == tasks_reporting.NOMBRE_BARRIDO
    assert entrada["options"] == {"queue": Cola.NOTIFICATIONS.value}
