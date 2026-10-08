"""Frontend gates (the `lint-frontend` CI job)."""

from __future__ import annotations

from pathlib import Path

from local_ci.context import Context, outcome_of
from local_ci.model import Outcome, Step

_FIXTURE_DIR = Path("src") / "features" / "payments" / "components"
_FIXTURE = _FIXTURE_DIR / "__r5_fixture.tsx"
_FIXTURE_BODY = 'import { x } from "@/features/billing/api/client";\nexport const a = x;\n'


def _npm(ctx: Context, *args: str) -> Outcome:
    result = ctx.run(["npm", *args], cwd=ctx.root / "frontend")
    return outcome_of(result, "npm " + " ".join(args))


def run_install(ctx: Context) -> Outcome:
    return _npm(ctx, "ci")


def run_format(ctx: Context) -> Outcome:
    return _npm(ctx, "run", "format:check")


def run_lint(ctx: Context) -> Outcome:
    return _npm(ctx, "run", "lint")


def run_typecheck(ctx: Context) -> Outcome:
    return _npm(ctx, "run", "typecheck")


def run_tests(ctx: Context) -> Outcome:
    return _npm(ctx, "run", "test:coverage")


def run_build(ctx: Context) -> Outcome:
    return _npm(ctx, "run", "build")


def run_r5_rule(ctx: Context) -> Outcome:
    """Lint must FAIL on a deep cross-feature import; otherwise the R5 rule is dead."""
    frontend = ctx.root / "frontend"
    fixture = frontend / _FIXTURE
    command = "npm run lint with an R5 violation fixture (must fail)"
    (frontend / _FIXTURE_DIR).mkdir(parents=True, exist_ok=True)
    fixture.write_text(_FIXTURE_BODY, encoding="utf-8")
    try:
        lint = ctx.runner(["npm", "run", "lint", "--silent"], cwd=frontend, env=ctx.env, echo=False)
    finally:
        fixture.unlink(missing_ok=True)
    if lint.exit_code == 0:
        msg = "The R5 ESLint rule no longer flags a deep cross-feature import."
        return Outcome(1, msg, command)
    return Outcome(0, "R5 ESLint rule is live.", command)


FRONTEND_STEPS: tuple[Step, ...] = (
    Step(
        "frontend-install", "Frontend: npm ci", True, run_install, "npm ci", tools=("node", "npm")
    ),
    Step(
        "frontend-format",
        "Frontend: prettier --check",
        True,
        run_format,
        "npm run format:check",
        tools=("npm",),
        after=("frontend-install",),
    ),
    Step(
        "frontend-lint",
        "Frontend: ESLint",
        True,
        run_lint,
        "npm run lint",
        tools=("npm",),
        after=("frontend-install",),
    ),
    Step(
        "frontend-typecheck",
        "Frontend: tsc --noEmit",
        True,
        run_typecheck,
        "npm run typecheck",
        tools=("npm",),
        after=("frontend-install",),
    ),
    Step(
        "frontend-r5-rule",
        "Frontend: R5 ESLint rule still fires",
        True,
        run_r5_rule,
        "lint with fixture, must fail",
        tools=("npm",),
        after=("frontend-lint",),
    ),
    Step(
        "frontend-tests",
        "Frontend: vitest with coverage",
        True,
        run_tests,
        "npm run test:coverage",
        tools=("npm",),
        after=("frontend-install",),
    ),
    # Not a CI gate today; an extra because a broken `next build` is cheap to catch.
    Step(
        "frontend-build",
        "Frontend: next build (extra, not in CI)",
        False,
        run_build,
        "npm run build",
        tools=("npm",),
        after=("frontend-install",),
    ),
)
