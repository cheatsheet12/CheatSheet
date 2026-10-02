"""La cadena de migraciones tiene una sola cabeza — HU-E4-05 RN-09, migración 0030.

No necesita base de datos: lee los archivos de `migrations/versions`. Dos cabezas son la
forma en que dos ramas se pisan sin que ninguna prueba lo note, hasta que `alembic upgrade
head` se niega a elegir.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

RAIZ_BACKEND = Path(__file__).resolve().parents[2]


def _scripts() -> ScriptDirectory:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return ScriptDirectory.from_config(config)


def test_alembic_tiene_una_sola_cabeza() -> None:
    assert len(_scripts().get_heads()) == 1
