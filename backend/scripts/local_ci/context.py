"""Everything a step needs to run, in one object that tests can fake."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from local_ci.execution import CommandResult, run_command
from local_ci.model import Outcome

Runner = Callable[..., CommandResult]

COMPOSE_PROJECT = "cheatsheet-localci"
DB_PORT = 5433  # host ports published by backend/docker-compose.yml
REDIS_PORT = 6380
DB_PASSWORD = "test-only-local-container"  # noqa: S105  # throwaway container, same as docker-compose.yml
OWNER_ROLE = "cheatsheet_owner"
APP_ROLE = "cheatsheet_app"
DB_NAME = "cheatsheet"

# Variables that could point a child process at something that is not our container.
_STRIPPED_PREFIXES = ("DATABASE_URL", "REDIS_URL", "CELERY_")


def find_bash(which: Callable[[str], str | None], platform: str) -> str | None:
    """Locate a real bash. On Windows, `bash` on PATH is often the WSL launcher in
    System32, which is not Git Bash and hangs without a distribution; derive the
    Git for Windows bash from git.exe instead.
    """
    if platform == "win32":
        git = which("git")
        if git:
            candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
        found = which("bash")
        if found and "system32" in found.lower().replace("\\", "/"):
            return None
        return found
    return which("bash")


def build_env(base: Mapping[str, str]) -> dict[str, str]:
    """The child environment: the parent's, minus service URLs, plus CI's test values.

    Nothing is read from or written to any .env file.
    """
    env = {k: v for k, v in base.items() if not k.startswith(_STRIPPED_PREFIXES)}
    host = f"localhost:{DB_PORT}/{DB_NAME}"
    env["DATABASE_URL"] = f"postgresql+asyncpg://{APP_ROLE}:{DB_PASSWORD}@{host}"
    env["DATABASE_URL_MIGRATIONS"] = f"postgresql+asyncpg://{OWNER_ROLE}:{DB_PASSWORD}@{host}"
    env["REDIS_URL"] = f"redis://localhost:{REDIS_PORT}/0"
    env["APP_ENV"] = "test"
    # test_guards.sh commits in throwaway repos; CI sets these through global git
    # config, which a developer machine must not have rewritten.
    env.update(
        GIT_AUTHOR_NAME="CI",
        GIT_AUTHOR_EMAIL="ci@cheatsheet.local",
        GIT_COMMITTER_NAME="CI",
        GIT_COMMITTER_EMAIL="ci@cheatsheet.local",
        PYTHONUTF8="1",
    )
    return env


@dataclass
class Context:
    root: Path
    env: dict[str, str]
    target_branch: str = "develop"
    base_ref: str = "origin/develop"
    python: str = sys.executable
    runner: Runner = run_command
    state: dict[str, bool] = field(default_factory=dict)

    @property
    def compose_file(self) -> Path:
        return self.root / "backend" / "docker-compose.yml"

    def run(
        self, argv: Sequence[str], *, cwd: Path | None = None, stdin_text: str | None = None
    ) -> CommandResult:
        return self.runner(argv, cwd=cwd or self.root, env=self.env, stdin_text=stdin_text)

    def git(self, *args: str) -> CommandResult:
        return self.runner(["git", *args], cwd=self.root, env=self.env, echo=False)

    def tool_path(self, name: str) -> str | None:
        if name == "bash":
            return find_bash(shutil.which, sys.platform)
        return shutil.which(name)

    def has_tool(self, name: str) -> bool:
        return self.tool_path(name) is not None

    @property
    def bash(self) -> str:
        return self.tool_path("bash") or "bash"

    def has_module(self, name: str) -> bool:
        return importlib.util.find_spec(name) is not None


def outcome_of(result: CommandResult, command: str) -> Outcome:
    return Outcome(result.exit_code, result.output, command)
