"""Steps that need no services: conventions, lint, types, architecture, guards, secrets."""

from __future__ import annotations

import json
import os
import py_compile
from pathlib import Path

from local_ci.context import Context, outcome_of
from local_ci.conventions import branch_error, invalid_commit_subjects
from local_ci.model import Outcome, Step

_EXCLUDED = (".venv", "venv", ".git", "node_modules", ".mypy_cache", ".ruff_cache", ".codegraph")


def current_branch(ctx: Context) -> str:
    return ctx.git("rev-parse", "--abbrev-ref", "HEAD").output.strip()


def head_sha(ctx: Context) -> str:
    return ctx.git("rev-parse", "HEAD").output.strip()


def run_branch_name(ctx: Context) -> Outcome:
    branch = current_branch(ctx)
    error = branch_error(branch, ctx.target_branch)
    command = f"branch '{branch}' -> '{ctx.target_branch}'"
    if error:
        return Outcome(1, error, command)
    return Outcome(0, f"Branch {branch} -> {ctx.target_branch}: OK.", command)


def run_commit_messages(ctx: Context) -> Outcome:
    command = f"git log --format=%s {ctx.base_ref}..HEAD"
    log = ctx.git("log", "--format=%s", f"{ctx.base_ref}..HEAD")
    if log.exit_code != 0:
        return Outcome(1, f"{log.output}\nIs '{ctx.base_ref}' fetched?", command)
    bad = invalid_commit_subjects(log.output.splitlines())
    if bad:
        listing = "\n".join(f"Invalid commit message: '{s}'" for s in bad)
        return Outcome(1, listing + "\nRequired format: <type>(<module>): <description>", command)
    return Outcome(0, "All commit messages follow Conventional Commits.", command)


def run_worktree_clean(ctx: Context) -> Outcome:
    """The summary names a commit SHA; uncommitted edits would make that a lie."""
    command = "git status --porcelain --untracked-files=no"
    status = ctx.git("status", "--porcelain", "--untracked-files=no")
    if status.exit_code != 0 or status.output.strip():
        return Outcome(1, "Tracked files differ from HEAD:\n" + status.output, command)
    return Outcome(0, "Working tree matches HEAD.", command)


def run_ruff_format(ctx: Context) -> Outcome:
    argv = [ctx.python, "-m", "ruff", "format", "--check", "--diff", "."]
    return outcome_of(ctx.run(argv), "ruff format --check --diff .")


def run_ruff_check(ctx: Context) -> Outcome:
    argv = [ctx.python, "-m", "ruff", "check", "."]
    return outcome_of(ctx.run(argv), "ruff check .")


def python_files(root: Path) -> list[str]:
    """Every tracked-or-not .py file CI hands to mypy, as root-relative POSIX paths."""
    found: list[str] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED)  # prune: node_modules is huge
        relative = Path(current).relative_to(root)
        found += ["./" + (relative / n).as_posix() for n in sorted(names) if n.endswith(".py")]
    return found


# CI passes every file on the command line (xargs). Windows caps a command line at ~32k
# characters, so the same list goes through mypy's own entry point on stdin instead.
_MYPY_FROM_STDIN = "import sys; from mypy.main import main; main(args=sys.stdin.read().split())"


def run_mypy(ctx: Context) -> Outcome:
    files = python_files(ctx.root)
    if not files:
        return Outcome(0, "No Python code yet - nothing to check.", "mypy")
    result = ctx.run([ctx.python, "-c", _MYPY_FROM_STDIN], stdin_text="\n".join(files))
    return outcome_of(result, f"mypy <{len(files)} .py files>")


def run_architecture(ctx: Context) -> Outcome:
    argv = [ctx.python, ".claude/hooks/guard_architecture.py", "--scan", "."]
    return outcome_of(ctx.run(argv), "python .claude/hooks/guard_architecture.py --scan .")


def run_guards_settings(ctx: Context) -> Outcome:
    """Equivalent of `jq -e '.hooks.PreToolUse' .claude/settings.json` (jq is not needed)."""
    command = "json: .hooks.PreToolUse of .claude/settings.json"
    try:
        data = json.loads((ctx.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        value = data["hooks"]["PreToolUse"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        return Outcome(
            1, f".claude/settings.json is invalid or lost its hooks ({error!r}).", command
        )
    if value in (None, False):
        return Outcome(1, ".claude/settings.json declares no PreToolUse hooks.", command)
    return Outcome(0, "settings.json is valid and declares its hooks.", command)


def run_guards_compile(ctx: Context) -> Outcome:
    hooks = ctx.root / ".claude" / "hooks"
    lines: list[str] = []
    failed = False
    for script in sorted(hooks.glob("*.py")):
        try:
            py_compile.compile(str(script), doraise=True)
        except py_compile.PyCompileError as error:
            lines.append(f"{script.name} does not compile: {error.msg}")
            failed = True
    for script in sorted(hooks.glob("*.sh")):
        check = ctx.run([ctx.bash, "-n", str(script)])
        if check.exit_code != 0:
            lines.append(f"{script.name} does not compile.")
            failed = True
    if not failed:
        lines.append("All hooks are syntactically valid.")
    return Outcome(1 if failed else 0, "\n".join(lines), "py_compile + bash -n .claude/hooks/*")


def run_guards_behaviour(ctx: Context) -> Outcome:
    return outcome_of(
        ctx.run([ctx.bash, ".claude/hooks/test_guards.sh"]), "bash .claude/hooks/test_guards.sh"
    )


def run_secret_scan(ctx: Context) -> Outcome:
    argv = ["gitleaks", "detect", "--source", ".", "--no-git", "--redact", "-v"]
    return outcome_of(ctx.run(argv), " ".join(argv))


STATIC_STEPS: tuple[Step, ...] = (
    Step(
        "conventions-branch",
        "Conventions: branch name and target",
        True,
        run_branch_name,
        "branch regex (ci.yml: conventions)",
        tools=("git",),
    ),
    Step(
        "conventions-commits",
        "Conventions: commit messages",
        True,
        run_commit_messages,
        "git log base..HEAD vs Conventional Commits",
        tools=("git",),
    ),
    Step(
        "worktree-clean",
        "Working tree matches HEAD (summary honesty)",
        True,
        run_worktree_clean,
        "git status --porcelain",
        tools=("git",),
    ),
    Step(
        "ruff-format",
        "Lint: ruff format --check",
        True,
        run_ruff_format,
        "ruff format --check --diff .",
        modules=("ruff",),
    ),
    Step("ruff-check", "Lint: ruff check", True, run_ruff_check, "ruff check .", modules=("ruff",)),
    Step("mypy", "Types: mypy --strict", True, run_mypy, "mypy <all .py files>", modules=("mypy",)),
    Step(
        "architecture",
        "Architecture boundaries",
        True,
        run_architecture,
        "guard_architecture.py --scan .",
    ),
    Step(
        "guards-settings",
        "Guards: settings.json declares hooks",
        True,
        run_guards_settings,
        ".claude/settings.json .hooks.PreToolUse",
    ),
    Step(
        "guards-compile",
        "Guards: hooks compile",
        True,
        run_guards_compile,
        "py_compile + bash -n",
        tools=("bash",),
    ),
    Step(
        "guards-behaviour",
        "Guards: test_guards.sh still blocks",
        True,
        run_guards_behaviour,
        "bash .claude/hooks/test_guards.sh",
        tools=("bash", "jq"),
    ),
    Step(
        "secret-scan",
        "Credential detection (gitleaks)",
        True,
        run_secret_scan,
        "gitleaks detect --source . --no-git --redact -v",
        tools=("gitleaks",),
    ),
)
