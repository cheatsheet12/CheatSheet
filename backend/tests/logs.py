"""Ayuda para los tests que miran los logs de un módulo.

`configurar_logging` activa `cache_logger_on_first_use`: un `logger = obtener_logger(__name__)` de
módulo que ya se usó **antes** de `capture_logs` queda atado a los procesadores de entonces y el
test no ve nada (según el orden en que corra la suite). Un logger nuevo, que todavía no se usó,
se ata recién adentro de `capture_logs`.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import ModuleType

import pytest
import structlog


def logger_nuevo(monkeypatch: pytest.MonkeyPatch, *modulos: ModuleType) -> None:
    """Reemplaza el `logger` de cada módulo por uno que `capture_logs` seguro alcanza."""
    for modulo in modulos:
        monkeypatch.setattr(modulo, "logger", structlog.get_logger(modulo.__name__))


def logs_capturables(monkeypatch: pytest.MonkeyPatch, *modulos: ModuleType) -> Iterator[None]:
    """`logger_nuevo` más **sin filtro de nivel**, y restaura la configuración al terminar.

    Un test que arma la app (`configurar_logging`) deja el filtro en el nivel de los settings, y
    ese filtro descarta un `info` antes de que `capture_logs` lo vea. Para usar desde un
    fixture: `yield from logs_capturables(monkeypatch, modulo)`.
    """
    anterior = structlog.get_config()["wrapper_class"]
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(0))
    logger_nuevo(monkeypatch, *modulos)
    try:
        yield
    finally:
        structlog.configure(wrapper_class=anterior)
