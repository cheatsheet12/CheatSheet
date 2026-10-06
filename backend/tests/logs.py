"""Ayuda para los tests que miran los logs de un módulo.

`configurar_logging` activa `cache_logger_on_first_use`: un `logger = obtener_logger(__name__)` de
módulo que ya se usó **antes** de `capture_logs` queda atado a los procesadores de entonces y el
test no ve nada (según el orden en que corra la suite). Un logger nuevo, que todavía no se usó,
se ata recién adentro de `capture_logs`.
"""

from __future__ import annotations

from types import ModuleType

import pytest
import structlog


def logger_nuevo(monkeypatch: pytest.MonkeyPatch, *modulos: ModuleType) -> None:
    """Reemplaza el `logger` de cada módulo por uno que `capture_logs` seguro alcanza."""
    for modulo in modulos:
        monkeypatch.setattr(modulo, "logger", structlog.get_logger(modulo.__name__))
