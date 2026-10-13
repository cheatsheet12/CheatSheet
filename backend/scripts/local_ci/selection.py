"""Choosing which steps run. Pure."""

from __future__ import annotations

from collections.abc import Sequence

from local_ci.model import Step


class UnknownStepError(ValueError):
    """`--only` or `--skip` named a step that does not exist."""


def select_steps(
    catalogue: Sequence[Step],
    only: Sequence[str] | None = None,
    skip: Sequence[str] = (),
) -> list[str]:
    """Return the ids to run, in catalogue order.

    `only` pulls in the prerequisites of each requested step (a test run needs the
    database up), so a subset still executes correctly. `skip` removes steps after
    that; a skipped prerequisite makes its dependents SKIPPED at run time.
    """
    by_id = {s.step_id: s for s in catalogue}
    for name in [*(only or ()), *skip]:
        if name not in by_id:
            raise UnknownStepError(f"unknown step '{name}'. Known: {', '.join(by_id)}")

    wanted: set[str] = set(by_id) if only is None else set()
    stack = list(only or ())
    while stack:
        current = stack.pop()
        if current in wanted:
            continue
        wanted.add(current)
        stack.extend(by_id[current].after)

    wanted -= set(skip)
    return [s.step_id for s in catalogue if s.step_id in wanted]
