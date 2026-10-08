"""Executing the selected steps and turning each into a StepResult."""

from __future__ import annotations

import time
from collections.abc import Sequence

from local_ci.context import Context
from local_ci.execution import emit
from local_ci.guard import NonLocalTargetError
from local_ci.model import Outcome, Status, Step, StepResult

EXCERPT_LINES = 40


def tail(text: str, lines: int = EXCERPT_LINES) -> str:
    return "\n".join(text.rstrip().splitlines()[-lines:])


def missing_requirements(ctx: Context, step: Step) -> str | None:
    """Reason the step cannot run on this machine, or None."""
    for tool in step.tools:
        if not ctx.has_tool(tool):
            return f"'{tool}' is not installed or not on PATH"
    for module in step.modules:
        if not ctx.has_module(module):
            return f"Python module '{module}' is not installed"
    return None


def _skipped(step: Step, detail: str) -> StepResult:
    return StepResult(
        step.step_id, step.name, step.required, Status.SKIPPED, command=step.command, detail=detail
    )


def execute_step(ctx: Context, step: Step, results: dict[str, StepResult]) -> StepResult:
    for prerequisite in step.after:
        done = results.get(prerequisite)
        if done is None or done.status is not Status.PASS:
            why = done.status.value if done else "not selected"
            return _skipped(step, f"prerequisite '{prerequisite}': {why}")
    reason = missing_requirements(ctx, step)
    if reason:
        return _skipped(step, reason)

    started = time.monotonic()
    try:
        outcome: Outcome = step.run(ctx)
    except (NonLocalTargetError, OSError) as error:
        outcome = Outcome(1, f"{type(error).__name__}: {error}", step.command)
    elapsed = time.monotonic() - started
    status = Status.PASS if outcome.exit_code == 0 else Status.FAIL
    return StepResult(
        step.step_id,
        step.name,
        step.required,
        status,
        command=outcome.command or step.command,
        exit_code=outcome.exit_code,
        duration_s=elapsed,
        excerpt="" if status is Status.PASS else tail(outcome.output),
    )


def run_steps(ctx: Context, catalogue: Sequence[Step], selected: Sequence[str]) -> list[StepResult]:
    """Run `selected` in catalogue order; unselected steps are reported as NOT RUN."""
    results: dict[str, StepResult] = {}
    ordered: list[StepResult] = []
    for step in catalogue:
        if step.step_id not in selected:
            result = StepResult(
                step.step_id, step.name, step.required, Status.NOT_RUN, detail="not selected"
            )
        else:
            emit(f"\n==> {step.step_id}: {step.name}")
            result = execute_step(ctx, step, results)
            emit(f"<== {step.step_id}: {result.status.value} ({result.duration_s:.1f}s)")
        results[step.step_id] = result
        ordered.append(result)
    return ordered
