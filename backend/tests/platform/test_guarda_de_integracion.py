"""The guard that keeps the destructive integration suite away from shared databases.

The suite deletes from every table after each test and downgrades migrations to `base`.
Pointed at the staging database it would wipe it, so the destination is checked before
any migration or connection. These tests need no database: the guard is a pure function.
"""

from __future__ import annotations

import pytest

from tests.integracion.guarda import (
    BASE_DEDICADA_REMOTA,
    DestinoDeIntegracionRechazado,
    verificar_destino,
)

HOST_NEON = "ep-abc-123.sa-east-1.aws.neon.tech"


def _urls(host: str, base: str, host_dueno: str | None = None) -> tuple[str, str]:
    app = f"postgresql+asyncpg://cheatsheet_app:x@{host}:5432/{base}"
    dueno = f"postgresql+asyncpg://neondb_owner:y@{host_dueno or host}:5432/{base}"
    return app, dueno


def test_verificar_destino_ci_local_pasa() -> None:
    verificar_destino(*_urls("localhost", "cheatsheet"))


def test_verificar_destino_local_con_otro_nombre_de_base_pasa() -> None:
    verificar_destino(*_urls("127.0.0.1", "otra_base"))


def test_verificar_destino_remoto_con_la_base_dedicada_pasa() -> None:
    verificar_destino(*_urls(HOST_NEON, BASE_DEDICADA_REMOTA))


def test_verificar_destino_remoto_con_la_base_de_staging_se_rechaza() -> None:
    with pytest.raises(DestinoDeIntegracionRechazado, match="neondb"):
        verificar_destino(*_urls(HOST_NEON, "neondb"))


def test_verificar_destino_distinto_host_entre_las_dos_urls_se_rechaza() -> None:
    with pytest.raises(DestinoDeIntegracionRechazado, match="host"):
        verificar_destino(*_urls("localhost", "cheatsheet", host_dueno=HOST_NEON))


def test_verificar_destino_distinta_base_entre_las_dos_urls_se_rechaza() -> None:
    app, _ = _urls("localhost", "cheatsheet")
    _, dueno = _urls("localhost", "otra")
    with pytest.raises(DestinoDeIntegracionRechazado, match="database"):
        verificar_destino(app, dueno)


def test_verificar_destino_distinto_puerto_se_rechaza() -> None:
    app, _ = _urls("localhost", "cheatsheet")
    dueno = "postgresql+asyncpg://o:y@localhost:5433/cheatsheet"
    with pytest.raises(DestinoDeIntegracionRechazado, match="port"):
        verificar_destino(app, dueno)


def test_verificar_destino_el_mensaje_no_filtra_la_password() -> None:
    with pytest.raises(DestinoDeIntegracionRechazado) as error:
        verificar_destino(*_urls(HOST_NEON, "neondb"))
    assert "x@" not in str(error.value)
    assert "y@" not in str(error.value)
    assert "backend/tests/README.md" in str(error.value)
