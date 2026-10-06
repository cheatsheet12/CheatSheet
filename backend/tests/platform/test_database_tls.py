"""The TLS decision, which is made from the host and never from the connection string.

What is being protected here is not "SSL is configured". It is that a database reached
over a network we do not own gets a **verified** context — hostname checked, certificate
required — because asyncpg's string forms do not give that:

- ``?ssl=verify-full`` reads a CA from ``~/.postgresql/root.crt`` or ``PGSSLROOTCERT``
  and raises when neither exists, so it works on one machine and nowhere else.
- ``?ssl=require`` silently degrades to ``CERT_NONE`` when there is no CA file. The
  connection is encrypted and the server is never identified, which is the failure mode
  that looks exactly like success — and therefore the one worth a test.
"""

from __future__ import annotations

import ssl

import pytest
from cheatsheet.platform.database import (
    TIMEOUT_DE_CONEXION_SEGUNDOS,
    ConfiguracionDeConexionInvalida,
    argumentos_de_conexion,
)

NEON = "postgresql+asyncpg://cheatsheet_app:secreto@ep-abc-123.sa-east-1.aws.neon.tech/neondb"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://cheatsheet_app:x@localhost:5433/cheatsheet",
        "postgresql+asyncpg://cheatsheet_app:x@127.0.0.1:5432/cheatsheet",
    ],
)
def test_una_base_local_no_lleva_tls(url: str) -> None:
    """The disposable container of a laptop or a CI job is not on a network."""
    assert "ssl" not in argumentos_de_conexion(url)


def test_una_base_remota_lleva_un_contexto_tls_verificado() -> None:
    argumentos = argumentos_de_conexion(NEON)

    contexto = argumentos["ssl"]
    assert isinstance(contexto, ssl.SSLContext)
    # The two properties that `require` would have thrown away.
    assert contexto.check_hostname is True
    assert contexto.verify_mode is ssl.CERT_REQUIRED


def test_el_contexto_confia_en_alguna_autoridad() -> None:
    """A context with an empty trust store verifies nothing and rejects everything."""
    contexto = argumentos_de_conexion(NEON)["ssl"]

    assert len(contexto.get_ca_certs()) > 0


@pytest.mark.parametrize(
    "parametro",
    ["ssl=verify-full", "sslmode=require", "channel_binding=require", "sslrootcert=ca.pem"],
)
def test_un_parametro_tls_en_la_url_se_rechaza_con_un_mensaje(parametro: str) -> None:
    """The URL Neon hands out to copy carries two of these, and pasting it is the norm.

    Forwarded to `asyncpg.connect()` they become a duplicate `ssl` or an unknown keyword,
    and the `TypeError` surfaces deep inside the driver, naming a string nobody typed on
    purpose. Failing here instead says what to remove.
    """
    with pytest.raises(ConfiguracionDeConexionInvalida, match="TLS se decide"):
        argumentos_de_conexion(f"{NEON}?{parametro}")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://cheatsheet_app:x@localhost:5433/cheatsheet",
        NEON,
    ],
)
def test_toda_conexion_lleva_timeout_explicito(url: str) -> None:
    """`CLAUDE.md` §5: no external call waits on somebody else's default.

    Without it the caller cannot tell "the database is slow" from "the database is not
    there", and a request or a Celery task hangs on asyncpg's own default instead.
    """
    assert argumentos_de_conexion(url)["timeout"] == TIMEOUT_DE_CONEXION_SEGUNDOS


# ---------------------------------------------------------------------------
# The driver, which is the other half of what a pasted URL gets wrong
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        # What the managed provider hands out, and what a person types from memory.
        "postgresql://cheatsheet_app:x@ep-abc-123.sa-east-1.aws.neon.tech/neondb",
        # The synchronous drivers, named on purpose rather than omitted.
        "postgresql+psycopg2://cheatsheet_app:x@ep-abc-123.neon.tech/neondb",
        "postgresql+psycopg://cheatsheet_app:x@ep-abc-123.neon.tech/neondb",
    ],
)
def test_una_url_sin_asyncpg_se_rechaza_nombrando_el_driver(url: str) -> None:
    """Without this, SQLAlchemy resolves the URL to psycopg2 and the error is a lie.

    `postgresql://` is not an omission the driver forgives: it selects the synchronous
    dialect, which imports a package this project does not depend on. What the operator
    sees is `ModuleNotFoundError: No module named 'psycopg2'` raised deep inside
    SQLAlchemy — a package that appears in no requirements file, no lockfile and no
    import in the repository. Nothing in it says "your URL is missing `+asyncpg`".
    """
    with pytest.raises(ConfiguracionDeConexionInvalida, match="postgresql\\+asyncpg"):
        argumentos_de_conexion(url)


def test_los_dos_errores_de_una_url_pegada_se_informan_juntos() -> None:
    """The string the provider offers to copy carries both mistakes at once.

    Reporting only the first would send whoever is fixing it around the loop twice:
    correct the driver, deploy, fail again on the query string. Both are named in one
    message because both are wrong in one paste.
    """
    pegada = (
        "postgresql://cheatsheet_app:x@ep-abc-123.sa-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )

    with pytest.raises(ConfiguracionDeConexionInvalida) as excepcion:
        argumentos_de_conexion(pegada)

    mensaje = str(excepcion.value)
    assert "postgresql+asyncpg" in mensaje
    assert "channel_binding" in mensaje
    assert "sslmode" in mensaje


def test_la_url_correcta_sigue_pasando() -> None:
    """The guard rejects what is broken and nothing else."""
    assert argumentos_de_conexion(NEON)["timeout"] == TIMEOUT_DE_CONEXION_SEGUNDOS
