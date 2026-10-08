"""Destination guard for the destructive PostgreSQL integration suite.

The suite deletes from every table after each test and downgrades the migrations to
`base` and back. Against the shared staging database that is a wipe, and nothing else
stops it: the only gate used to be "are the two URLs set?".

The rule is therefore about *where* the suite may run:

- On this machine (a laptop container, or the CI service) any database name is fine:
  it is disposable by construction.
- On any other host it may only run against a database named exactly
  ``BASE_DEDICADA_REMOTA``, a database that exists for this suite and holds nothing else.
  Staging uses another name, so pointing the suite at it is refused.
- In every case both URLs must name the same host, port and database. They are the
  application role and the owner role of *one* database; if they diverge, the suite
  would migrate one database and exercise another.

The check is a pure function so it can be tested without a database, and the messages
carry host, port and database name only, never credentials.
"""

from __future__ import annotations

from cheatsheet.platform.database import HOSTS_LOCALES
from sqlalchemy.engine import URL, make_url

BASE_DEDICADA_REMOTA = "cheatsheet_integracion"


class DestinoDeIntegracionRechazado(RuntimeError):
    """The integration suite refuses to run against the configured database."""


def _destino(url: URL) -> str:
    return f"{url.host or 'localhost'}:{url.port or 5432}/{url.database}"


def _rechazo(motivo: str, url_app: URL, url_dueno: URL) -> DestinoDeIntegracionRechazado:
    return DestinoDeIntegracionRechazado(
        f"Refusing to run the destructive integration suite: {motivo}.\n"
        f"  DATABASE_URL            -> {_destino(url_app)}\n"
        f"  DATABASE_URL_MIGRATIONS -> {_destino(url_dueno)}\n"
        "The suite deletes every table after each test and downgrades the migrations. "
        f"Outside this machine it only runs against a database named "
        f"'{BASE_DEDICADA_REMOTA}'. See backend/tests/README.md."
    )


def verificar_destino(url_app: str, url_dueno: str) -> None:
    """Raise `DestinoDeIntegracionRechazado` unless it is safe to run against these URLs."""
    app = make_url(url_app)
    dueno = make_url(url_dueno)

    for nombre, valor_app, valor_dueno in (
        ("host", (app.host or "").lower(), (dueno.host or "").lower()),
        ("port", app.port, dueno.port),
        ("database", app.database, dueno.database),
    ):
        if valor_app != valor_dueno:
            raise _rechazo(f"the two URLs name a different {nombre}", app, dueno)

    es_local = (app.host or "").lower() in HOSTS_LOCALES
    if not es_local and app.database != BASE_DEDICADA_REMOTA:
        raise _rechazo(f"the host is not local and the database is '{app.database}'", app, dueno)
