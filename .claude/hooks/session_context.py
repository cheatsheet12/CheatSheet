#!/usr/bin/env python3
"""SessionStart hook: injects the real state of the repository at session start.

An agent starting cold does not know which branch it is standing on, nor whether the
development environment is ready. Without that, the first thing it tries to do gets
blocked by a hook. This tells it up front.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROTECTED_BRANCHES = {"main", "develop"}


def git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> None:
    raw_root = git("rev-parse", "--show-toplevel")
    if raw_root is None:
        return
    root = Path(raw_root)

    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    dirty = git("status", "--porcelain") or ""

    lines = [
        "CheatSheet repository state at session start:",
        f"- Current branch: {branch}",
        f"- Uncommitted changes: {len(dirty.splitlines())} file(s)",
    ]

    if branch in PROTECTED_BRANCHES:
        lines.append(
            f"- WARNING: '{branch}' is a protected branch. The hooks will block every "
            "write and every commit until you create a working branch "
            "(feature/… · fix/… · hotfix/…). See CLAUDE.md §4."
        )

    if not (root / ".venv").exists():
        lines.append(
            "- The .venv virtual environment does not exist. Before running the checks: "
            "python -m venv .venv && source .venv/bin/activate && "
            "pip install -r requirements-dev.txt"
        )

    # ADRs are zero-padded (0001-…), so a leading [1-9] never matched one. Match any
    # numbered file and exclude 0000-template.md, which is the template, not a decision.
    adrs = [
        path
        for path in (root / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md")
        if not path.name.startswith("0000-")
    ]
    if not adrs:
        lines.append(
            "- There is no accepted ADR yet, so the architecture is undefined and new "
            "top-level directories are blocked (CLAUDE.md §2)."
        )

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(lines),
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — informational, must never stall the session
        print(f"[session_context] internal failure: {exc}", file=sys.stderr)
    sys.exit(0)
