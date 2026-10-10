"""Interval settings become wall-clock-aligned crontab fields, or fail loudly.

Why alignment: Neon suspends compute after five idle minutes. Interval schedules count
from Beat's boot, so each task wakes the database at its own offset and the compute never
sleeps. Anchoring every task to minute 0 of the hour makes them all fire together, and
the database wakes once per period instead of once per task.
"""

from __future__ import annotations

import pytest
from cheatsheet.platform.intervalos import IntervaloNoAlineable, campos_alineados
from cheatsheet.platform.settings import ConfiguracionFaltante, Settings


@pytest.mark.parametrize(
    ("minutos", "esperado"),
    [
        (1, ("*", "*")),
        (5, ("*/5", "*")),
        (15, ("*/15", "*")),
        (30, ("*/30", "*")),
        (60, ("0", "*")),
        (120, ("0", "*/2")),
        (240, ("0", "*/4")),
        (360, ("0", "*/6")),
        (1440, ("0", "0")),
    ],
)
def test_un_intervalo_que_divide_el_periodo_se_ancla_al_minuto_cero(
    minutos: int, esperado: tuple[str, str]
) -> None:
    assert campos_alineados(minutos) == esperado


@pytest.mark.parametrize("minutos", [-5, 0, 7, 45, 90, 61, 150, 420, 1500, 2880])
def test_un_intervalo_que_no_se_alinea_se_rechaza_en_vez_de_redondearse(minutos: int) -> None:
    """Rounding 45 to 30 or 60 would silently change how often a billing sweep runs."""
    with pytest.raises(IntervaloNoAlineable) as error:
        campos_alineados(minutos)

    assert str(minutos) in str(error.value)


@pytest.mark.parametrize(
    "variable",
    [
        "WHATSAPP_SONDEO_MINUTOS",
        "WHATSAPP_PLANTILLAS_MINUTOS",
        "DLQ_BARRIDO_MINUTOS",
        "SYNC_PLANILLAS_MINUTOS",
        "BILLING_RECONCILIACION_MINUTOS",
        "RECORDATORIO_DE_TURNO_MINUTOS",
    ],
)
def test_un_intervalo_mal_configurado_falla_al_arrancar(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "k" * 44)
    monkeypatch.setenv(variable, "45")

    with pytest.raises(ConfiguracionFaltante, match=variable):
        Settings.desde_entorno()


@pytest.mark.parametrize("horas", ["0", "-1", "5", "7", "25", "48"])
def test_las_horas_de_parametros_fiscales_que_no_se_alinean_fallan_al_arrancar(
    monkeypatch: pytest.MonkeyPatch, horas: str
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "k" * 44)
    monkeypatch.setenv("PARAMETROS_FISCALES_HORAS", horas)

    with pytest.raises(ConfiguracionFaltante, match="PARAMETROS_FISCALES_HORAS"):
        Settings.desde_entorno()


def test_las_horas_de_parametros_fiscales_por_defecto_son_validas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "k" * 44)
    monkeypatch.delenv("PARAMETROS_FISCALES_HORAS", raising=False)

    assert Settings.desde_entorno().parametros_fiscales_horas == 24
