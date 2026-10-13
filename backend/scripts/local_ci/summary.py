"""The Markdown block a developer pastes into the Pull Request. Pure."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from local_ci.model import Status, StepResult, Verdict

VERDICT_TEXT = {
    Verdict.COMPLETE: "COMPLETE - every required step passed",
    Verdict.INCOMPLETE: "INCOMPLETE - a required step was skipped or not run",
    Verdict.FAILED: "FAILED - at least one step failed",
}


@dataclass(frozen=True)
class RunMeta:
    sha: str
    branch: str
    target: str
    date_utc: str
    machine: str


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _row(index: int, r: StepResult) -> str:
    code = "-" if r.exit_code is None else str(r.exit_code)
    required = "yes" if r.required else "no"
    note = f" ({_cell(r.detail)})" if r.detail and r.status is not Status.PASS else ""
    return (
        f"| {index} | `{r.step_id}` | {required} | **{r.status.value}**{note} "
        f"| {code} | {r.duration_s:.1f}s |"
    )


def _failure_blocks(results: Sequence[StepResult]) -> list[str]:
    blocks: list[str] = []
    for r in results:
        if r.status is Status.FAIL and r.excerpt:
            blocks += [
                f"<details><summary>{r.step_id}: last output</summary>",
                "",
                "~~~text",
                r.excerpt,
                "~~~",
                "</details>",
                "",
            ]
    return blocks


def render_summary(results: Sequence[StepResult], verdict: Verdict, meta: RunMeta) -> str:
    lines = [
        "## Local CI summary",
        "",
        f"- **Commit:** `{meta.sha}`",
        f"- **Branch:** `{meta.branch}` -> `{meta.target}`",
        f"- **Date (UTC):** {meta.date_utc}",
        f"- **Machine:** {meta.machine}",
        f"- **Verdict:** **{VERDICT_TEXT[verdict]}**",
        "",
        "| # | Step | Required | Result | Exit | Duration |",
        "|---|---|---|---|---|---|",
    ]
    lines += [_row(i, r) for i, r in enumerate(results, start=1)]
    lines.append("")
    lines += _failure_blocks(results)
    lines.append(
        "Reproduce: `python backend/scripts/run_local_ci.py` "
        "(see docs/adr/0016-local-ci-verification.md)."
    )
    return "\n".join(lines) + "\n"
