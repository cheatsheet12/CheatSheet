"""Result types and the verdict logic. Pure: no I/O, no subprocesses."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum


class Status(str, Enum):
    """Outcome of one step. `SKIPPED` and `NOT_RUN` are never a pass."""

    PASS = "PASS"  # noqa: S105 - a status label, not a credential
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"  # selected, but could not run (missing tool, failed prerequisite)
    NOT_RUN = "NOT RUN"  # not selected by --only / --skip


class Verdict(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


EXIT_COMPLETE = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_INCOMPLETE = 3


@dataclass(frozen=True)
class Outcome:
    """What a step action reports back to the runner."""

    exit_code: int
    output: str = ""
    command: str = ""


@dataclass(frozen=True)
class StepResult:
    step_id: str
    name: str
    required: bool
    status: Status
    command: str = ""
    exit_code: int | None = None
    duration_s: float = 0.0
    detail: str = ""
    excerpt: str = ""


@dataclass(frozen=True)
class Step:
    """One CI step. `run` receives the execution context and returns an Outcome."""

    step_id: str
    name: str
    required: bool
    run: Callable[..., Outcome]
    command: str
    tools: tuple[str, ...] = ()  # executables that must be on PATH
    modules: tuple[str, ...] = ()  # Python modules that must be importable
    after: tuple[str, ...] = ()  # prerequisites: selected automatically, must PASS


def decide_verdict(results: Sequence[StepResult]) -> Verdict:
    """`complete` only when nothing failed and every required step passed."""
    if any(r.status is Status.FAIL for r in results):
        return Verdict.FAILED
    if any(r.required and r.status is not Status.PASS for r in results):
        return Verdict.INCOMPLETE
    return Verdict.COMPLETE


def exit_code_for(verdict: Verdict) -> int:
    if verdict is Verdict.COMPLETE:
        return EXIT_COMPLETE
    if verdict is Verdict.FAILED:
        return EXIT_FAILED
    return EXIT_INCOMPLETE
