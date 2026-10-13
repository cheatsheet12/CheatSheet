"""Pure parts of the local CI runner. No Docker, no network, no subprocesses."""

from __future__ import annotations

from pathlib import Path

import pytest
from local_ci.catalog import CATALOGUE
from local_ci.context import APP_ROLE, DB_PORT, Context, build_env, find_bash
from local_ci.conventions import branch_error, invalid_commit_subjects
from local_ci.guard import NonLocalTargetError, assert_local
from local_ci.model import (
    EXIT_COMPLETE,
    EXIT_FAILED,
    EXIT_INCOMPLETE,
    Outcome,
    Status,
    Step,
    StepResult,
    Verdict,
    decide_verdict,
    exit_code_for,
)
from local_ci.runner import execute_step, run_steps
from local_ci.selection import UnknownStepError, select_steps
from local_ci.steps_static import python_files
from local_ci.summary import RunMeta, render_summary

META = RunMeta("abc123", "feature/infra-x", "develop", "2026-10-08 12:00:00", "Test OS")


def _res(
    step_id: str,
    status: Status,
    required: bool = True,
    exit_code: int | None = None,
    duration_s: float = 0.0,
    detail: str = "",
    excerpt: str = "",
) -> StepResult:
    return StepResult(
        step_id,
        step_id,
        required,
        status,
        exit_code=exit_code,
        duration_s=duration_s,
        detail=detail,
        excerpt=excerpt,
    )


# --- verdict -----------------------------------------------------------------


def test_verdict_complete_when_all_required_pass_and_optional_skipped() -> None:
    results = [_res("a", Status.PASS), _res("b", Status.SKIPPED, required=False)]
    assert decide_verdict(results) is Verdict.COMPLETE
    assert exit_code_for(Verdict.COMPLETE) == EXIT_COMPLETE


@pytest.mark.parametrize("status", [Status.SKIPPED, Status.NOT_RUN])
def test_verdict_incomplete_when_a_required_step_did_not_pass(status: Status) -> None:
    results = [_res("a", Status.PASS), _res("b", status)]
    assert decide_verdict(results) is Verdict.INCOMPLETE
    assert exit_code_for(Verdict.INCOMPLETE) == EXIT_INCOMPLETE


def test_verdict_failed_beats_skipped_even_for_optional_steps() -> None:
    results = [_res("a", Status.FAIL, required=False), _res("b", Status.SKIPPED)]
    assert decide_verdict(results) is Verdict.FAILED
    assert exit_code_for(Verdict.FAILED) == EXIT_FAILED


def test_exit_codes_are_distinct() -> None:
    assert len({EXIT_COMPLETE, EXIT_FAILED, EXIT_INCOMPLETE}) == 3


# --- selection ---------------------------------------------------------------


def test_select_all_by_default_in_catalogue_order() -> None:
    assert select_steps(CATALOGUE) == [s.step_id for s in CATALOGUE]


def test_select_only_pulls_in_prerequisites() -> None:
    chosen = select_steps(CATALOGUE, only=["db-migrate"])
    assert chosen == ["services-up", "db-provision", "db-migrate"]


def test_select_skip_removes_a_step() -> None:
    assert "secret-scan" not in select_steps(CATALOGUE, skip=["secret-scan"])


def test_select_unknown_step_is_an_error() -> None:
    with pytest.raises(UnknownStepError):
        select_steps(CATALOGUE, only=["nope"])


def test_catalogue_ids_unique_and_prerequisites_come_first() -> None:
    seen: set[str] = set()
    for step in CATALOGUE:
        assert step.step_id not in seen
        assert set(step.after) <= seen, f"{step.step_id} runs before its prerequisite"
        seen.add(step.step_id)


# --- host guard --------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@localhost:5433/db",
        "postgresql+asyncpg://u:p@127.0.0.1/db",
        "redis://[::1]:6380/0",
    ],
)
def test_guard_accepts_loopback(url: str) -> None:
    assert_local(url, "X")


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:secret@ep-x.neon.tech/db", "redis://cache.internal:6379/0", "not a url"],
)
def test_guard_rejects_remote_and_never_echoes_credentials(url: str) -> None:
    with pytest.raises(NonLocalTargetError) as error:
        assert_local(url, "DATABASE_URL")
    assert "secret" not in str(error.value)


def test_build_env_overrides_ambient_service_urls() -> None:
    env = build_env({"DATABASE_URL": "postgresql://u:p@prod.example.com/db", "PATH": "/bin"})
    assert "prod.example.com" not in env["DATABASE_URL"]
    assert f"localhost:{DB_PORT}" in env["DATABASE_URL"]
    assert env["DATABASE_URL"].split("//")[1].startswith(APP_ROLE)
    assert env["APP_ENV"] == "test"
    assert env["PATH"] == "/bin"


# --- conventions -------------------------------------------------------------


@pytest.mark.parametrize(
    ("branch", "target", "ok"),
    [
        ("feature/infra-ci-local", "develop", True),
        ("fix/billing-round-vat", "develop", True),
        ("feature/infra-ci-local", "main", False),
        ("hotfix/arca-outage", "main", True),
        ("hotfix/arca-outage", "develop", False),
        ("develop", "main", True),
        ("random-branch", "develop", False),
    ],
)
def test_branch_rules_match_ci(branch: str, target: str, ok: bool) -> None:
    assert (branch_error(branch, target) is None) is ok


def test_commit_rules_match_ci() -> None:
    subjects = [
        "feat(infra): run the CI steps locally",
        "Merge pull request #1 from x/y",
        "WIP",
        "feat(infra): short",
        "",
    ]
    assert invalid_commit_subjects(subjects) == ["WIP", "feat(infra): short"]


# --- runner ------------------------------------------------------------------


def _ctx(tmp_path_factory: pytest.TempPathFactory) -> Context:
    return Context(root=tmp_path_factory.mktemp("repo"), env={})


def _step(
    step_id: str,
    exit_code: int,
    tools: tuple[str, ...] = (),
    after: tuple[str, ...] = (),
) -> Step:
    def action(_ctx: Context) -> Outcome:
        return Outcome(exit_code, "out\n", "cmd")

    return Step(step_id, step_id, True, action, "cmd", tools=tools, after=after)


def test_missing_tool_is_skipped_never_passed(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path_factory)
    monkeypatch.setattr(ctx, "has_tool", lambda _name: False)
    result = execute_step(ctx, _step("s", 0, tools=("docker",)), {})
    assert result.status is Status.SKIPPED
    assert "docker" in result.detail


def test_failed_prerequisite_skips_dependents(tmp_path_factory: pytest.TempPathFactory) -> None:
    ctx = _ctx(tmp_path_factory)
    results = run_steps(ctx, [_step("a", 1), _step("b", 0, after=("a",))], ["a", "b"])
    assert [r.status for r in results] == [Status.FAIL, Status.SKIPPED]
    assert results[0].excerpt == "out"


def test_unselected_steps_are_reported_not_run(tmp_path_factory: pytest.TempPathFactory) -> None:
    ctx = _ctx(tmp_path_factory)
    results = run_steps(ctx, [_step("a", 0), _step("b", 0)], ["a"])
    assert [r.status for r in results] == [Status.PASS, Status.NOT_RUN]
    assert decide_verdict(results) is Verdict.INCOMPLETE


def test_non_local_target_in_a_step_is_a_failure(tmp_path_factory: pytest.TempPathFactory) -> None:
    def boom(ctx: Context) -> Outcome:
        assert_local("postgresql://u:p@remote.example.com/db", "DATABASE_URL")
        return Outcome(0)

    ctx = _ctx(tmp_path_factory)
    step = Step("g", "g", True, boom, "guard")
    assert execute_step(ctx, step, {}).status is Status.FAIL


# --- summary -----------------------------------------------------------------


def test_summary_is_paste_ready_and_states_the_verdict() -> None:
    results = [
        _res("ruff-check", Status.PASS, exit_code=0, duration_s=1.25),
        _res("secret-scan", Status.SKIPPED, detail="'gitleaks' is not installed"),
        _res("mypy", Status.FAIL, exit_code=1, excerpt="error: bad | pipe"),
    ]
    text = render_summary(results, decide_verdict(results), META)
    assert "`abc123`" in text
    assert "feature/infra-x" in text
    assert "FAILED" in text
    assert "| 1 | `ruff-check` | yes | **PASS** | 0 | 1.2s |" in text or "1.3s" in text
    assert "**SKIPPED** ('gitleaks' is not installed)" in text
    assert "error: bad | pipe" in text


def test_summary_complete_verdict_text() -> None:
    results = [_res("a", Status.PASS, exit_code=0)]
    assert "COMPLETE" in render_summary(results, Verdict.COMPLETE, META)


# --- tooling discovery ---------------------------------------------------------


def test_find_bash_prefers_git_bash_over_the_wsl_launcher(tmp_path: Path) -> None:
    git_bash = tmp_path / "Git" / "bin" / "bash.exe"
    git_bash.parent.mkdir(parents=True)
    git_bash.write_text("")
    (tmp_path / "Git" / "cmd").mkdir()
    found = {
        "git": str(tmp_path / "Git" / "cmd" / "git.exe"),
        "bash": r"C:\Windows\System32\bash.exe",
    }
    assert find_bash(found.get, "win32") == str(git_bash.resolve())


def test_find_bash_rejects_the_wsl_launcher_when_git_bash_is_missing() -> None:
    found = {"bash": r"C:\Windows\System32\bash.exe"}
    assert find_bash(found.get, "win32") is None


def test_find_bash_on_posix_uses_path() -> None:
    assert find_bash({"bash": "/usr/bin/bash"}.get, "linux") == "/usr/bin/bash"


def test_python_files_prunes_excluded_directories(tmp_path: Path) -> None:
    for name in ("a.py", "pkg/b.py", "frontend/node_modules/x/c.py", ".venv/d.py", "e.txt"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("")
    assert python_files(tmp_path) == ["./a.py", "./pkg/b.py"]
