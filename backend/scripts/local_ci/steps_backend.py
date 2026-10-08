"""Backend steps that need PostgreSQL and Redis (the `tests` CI job)."""

from __future__ import annotations

from local_ci import context as c
from local_ci.context import Context, outcome_of
from local_ci.guard import assert_local
from local_ci.model import Outcome, Step

_PSQL = ("psql", "-U", c.OWNER_ROLE, "-d", c.DB_NAME, "-v", "ON_ERROR_STOP=1")
_VERIFY = "backend/scripts/verify_rls.py"


def compose_argv(ctx: Context, *args: str) -> list[str]:
    return ["docker", "compose", "-p", c.COMPOSE_PROJECT, "-f", str(ctx.compose_file), *args]


def psql_exec(ctx: Context, *psql_args: str, stdin_text: str | None = None) -> Outcome:
    """Run psql inside the postgres container (the host may not have a psql client)."""
    argv = compose_argv(
        ctx, "exec", "-T", "-e", f"PGPASSWORD={c.DB_PASSWORD}", "postgres", *_PSQL, *psql_args
    )
    return outcome_of(ctx.run(argv, stdin_text=stdin_text), "docker compose exec postgres psql")


def assert_targets_local(ctx: Context) -> None:
    for name in ("DATABASE_URL", "DATABASE_URL_MIGRATIONS", "REDIS_URL"):
        assert_local(ctx.env[name], name)


def run_services_up(ctx: Context) -> Outcome:
    assert_targets_local(ctx)
    down = ctx.run(compose_argv(ctx, "down", "-v", "--remove-orphans"))
    ctx.state["services_started"] = True  # tear down even if `up` fails half-way
    up = ctx.run(compose_argv(ctx, "up", "-d", "--wait"))
    return Outcome(up.exit_code, down.output + up.output, "docker compose up -d --wait")


def teardown_services(ctx: Context) -> Outcome:
    argv = compose_argv(ctx, "down", "-v", "--remove-orphans")
    return outcome_of(ctx.run(argv), "docker compose down -v --remove-orphans")


def run_db_provision(ctx: Context) -> Outcome:
    assert_targets_local(ctx)
    sql = (ctx.root / "backend" / "scripts" / "init-db.sql").read_text(encoding="utf-8")
    init = psql_exec(ctx, "-f", "-", stdin_text=sql)
    if init.exit_code != 0:
        return init
    alter = psql_exec(ctx, "-c", f"ALTER ROLE {c.APP_ROLE} PASSWORD '{c.DB_PASSWORD}'")
    return Outcome(alter.exit_code, init.output + alter.output, "init-db.sql + ALTER ROLE")


def run_migrate(ctx: Context) -> Outcome:
    assert_targets_local(ctx)
    argv = [ctx.python, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"]
    return outcome_of(ctx.run(argv), "alembic -c backend/alembic.ini upgrade head")


def run_verify_rls(ctx: Context) -> Outcome:
    assert_targets_local(ctx)
    return outcome_of(ctx.run([ctx.python, _VERIFY]), f"python {_VERIFY}")


def run_rls_negative(ctx: Context) -> Outcome:
    """verify_rls.py must FAIL while the app role has BYPASSRLS, or it checks nothing."""
    assert_targets_local(ctx)
    command = "ALTER ROLE BYPASSRLS; verify_rls.py (must fail); restore"
    raised = psql_exec(ctx, "-c", f"ALTER ROLE {c.APP_ROLE} BYPASSRLS")
    if raised.exit_code != 0:
        return Outcome(raised.exit_code, raised.output, command)
    try:
        check = ctx.run([ctx.python, _VERIFY])
    finally:
        restored = psql_exec(ctx, "-c", f"ALTER ROLE {c.APP_ROLE} NOBYPASSRLS")
    if restored.exit_code != 0:
        return Outcome(1, "Could not restore NOBYPASSRLS:\n" + restored.output, command)
    if check.exit_code == 0:
        msg = f"verify_rls.py passed with {c.APP_ROLE} in BYPASSRLS: it stopped verifying."
        return Outcome(1, msg, command)
    return Outcome(0, "The tenant-barrier verifier is live.", command)


def run_pytest_cov(ctx: Context) -> Outcome:
    assert_targets_local(ctx)
    argv = [ctx.python, "-m", "pytest", "--cov", "--cov-report=term-missing"]
    return outcome_of(ctx.run(argv), "pytest --cov --cov-report=term-missing")


def run_integration_only(ctx: Context) -> Outcome:
    """Integration tests must run, not skip: a skipped isolation suite is a green no-op."""
    assert_targets_local(ctx)
    command = "pytest backend/tests/integracion -q -p no:cacheprovider (no 'skipped')"
    base = [ctx.python, "-m", "pytest", "backend/tests/integracion", "-q", "-p", "no:cacheprovider"]
    collect = ctx.run([*base, "--collect-only"])
    if "no tests ran" in collect.output:
        return Outcome(1, "No integration tests were collected.", command)
    result = ctx.run(base)
    if result.exit_code == 0 and "skipped" in result.output:
        msg = (
            result.output + "\nThe integration tests were skipped: the database is not configured."
        )
        return Outcome(1, msg, command)
    return outcome_of(result, command)


BACKEND_STEPS: tuple[Step, ...] = (
    Step(
        "services-up",
        "Services: PostgreSQL + Redis (docker compose)",
        True,
        run_services_up,
        "docker compose up -d --wait",
        tools=("docker",),
    ),
    Step(
        "db-provision",
        "Provision the application role",
        True,
        run_db_provision,
        "psql init-db.sql + ALTER ROLE",
        tools=("docker",),
        after=("services-up",),
    ),
    Step(
        "db-migrate",
        "Apply migrations",
        True,
        run_migrate,
        "alembic upgrade head",
        modules=("alembic",),
        after=("db-provision",),
    ),
    Step(
        "rls-verify",
        "Verify the tenant barrier",
        True,
        run_verify_rls,
        "verify_rls.py",
        after=("db-migrate",),
    ),
    Step(
        "rls-negative",
        "Verify the barrier check fails when the barrier is down",
        True,
        run_rls_negative,
        "BYPASSRLS negative check",
        tools=("docker",),
        after=("rls-verify",),
    ),
    Step(
        "pytest-cov",
        "Tests with coverage (pytest --cov)",
        True,
        run_pytest_cov,
        "pytest --cov --cov-report=term-missing",
        modules=("pytest", "pytest_cov"),
        after=("rls-negative",),
    ),
    Step(
        "integration-only",
        "Integration tests actually ran (no skips)",
        True,
        run_integration_only,
        "pytest backend/tests/integracion",
        modules=("pytest",),
        after=("rls-negative",),
    ),
)
