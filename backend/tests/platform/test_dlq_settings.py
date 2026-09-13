"""The retry ceiling has two homes, and they must agree.

`platform/settings.py` cannot import `workers/base.py` — `platform/` is the floor every
other layer stands on, and importing a worker into it would invert that. So the default
is written twice, and this test is what keeps the copy honest.

The failure it prevents is quiet and bad: if the sweep judged against a different ceiling
than the one tasks are actually retried under, tasks would be retired either while they
still had attempts left, or never at all. Neither shows up as an error anywhere.
"""

from __future__ import annotations

from cheatsheet.platform.settings import DLQ_MAX_INTENTOS_POR_DEFECTO
from cheatsheet.workers.base import MAX_INTENTOS_POR_DEFECTO


def test_el_techo_de_reintentos_es_el_mismo_en_los_dos_lugares() -> None:
    assert DLQ_MAX_INTENTOS_POR_DEFECTO == MAX_INTENTOS_POR_DEFECTO
