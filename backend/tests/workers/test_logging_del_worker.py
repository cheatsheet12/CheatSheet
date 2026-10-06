"""The worker keeps the logging pipeline `configurar_logging` installed.

Without a receiver on Celery's `setup_logging` signal, a starting worker resets the root
logger to the level of its `-l` option (WARNING when absent) and adds a handler of its own.
Every `logger.info` of every task then disappears. On staging this hid the invitation link
that `EnviadorDeConsola` logs, which is the only way to complete an invitation there.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from celery import Celery
from celery.signals import setup_logging
from cheatsheet.workers.celery_app import IDENTIFICADOR_DEL_LOGGING, conservar_el_logging_propio


@pytest.fixture
def raiz() -> Iterator[logging.Logger]:
    """The root logger, restored afterwards: Celery mutates it when nobody stops it."""
    raiz = logging.getLogger()
    nivel, manejadores = raiz.level, list(raiz.handlers)
    yield raiz
    raiz.setLevel(nivel)
    raiz.handlers[:] = manejadores
    setup_logging.disconnect(dispatch_uid=IDENTIFICADOR_DEL_LOGGING)


def _arrancar_el_logging_de_un_worker() -> None:
    """What `celery worker` does on boot when it is started without `-l`."""
    Celery("prueba").log.setup_logging_subsystem(loglevel="WARNING")


def test_celery_no_cambia_el_nivel_ni_los_manejadores(raiz: logging.Logger) -> None:
    raiz.setLevel(logging.INFO)
    manejadores = list(raiz.handlers)
    conservar_el_logging_propio()

    _arrancar_el_logging_de_un_worker()

    assert raiz.level == logging.INFO
    assert raiz.handlers == manejadores


def test_conectarlo_dos_veces_no_duplica_el_receptor(raiz: logging.Logger) -> None:
    del raiz
    conservar_el_logging_propio()
    conservar_el_logging_propio()

    receptores = [r for r in setup_logging.receivers if r[0][0] == IDENTIFICADOR_DEL_LOGGING]

    assert len(receptores) == 1
