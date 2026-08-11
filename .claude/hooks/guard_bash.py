#!/usr/bin/env python3
"""PreToolUse hook (Bash): blocks commands that break the repository workflow.

Rules enforced (see CLAUDE.md §3 and §4):
  1. No committing while on `main` or `develop`.
  2. No pushing directly to `main` or `develop`; everything goes through a Pull Request.
  3. No rewriting history on protected branches (--force, reset --hard, rebase).
  4. No skipping the checks (--no-verify, pre-commit SKIP).
  5. New branches follow the feature/ · fix/ · hotfix/ naming scheme.

Emergency escape hatch: CHEATSHEET_UNSAFE=1 (see CLAUDE.md §8).
On internal failure it lets the command through and warns on stderr.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

PROTECTED_BRANCHES = {"main", "develop"}

# The module segment may contain underscores (e.g. spreadsheet_sync).
BRANCH_NAMING = re.compile(r"^(feature|fix)/[a-z0-9_]+-[a-z0-9-]+$|^hotfix/[a-z0-9-]+$")

MODULES = "identity, master_data, business_config, integrations, spreadsheet_sync, billing, payments, scheduling, conversational, observability, reporting, reference_data, frontend, infra"

BRANCH_HELP = (
    "Required naming scheme (CLAUDE.md §4):\n"
    "    feature/<module>-<kebab-description>   -> PR to develop\n"
    "    fix/<module>-<kebab-description>       -> PR to develop\n"
    "    hotfix/<kebab-description>             -> PR to main\n\n"
    f"Valid modules: {MODULES}\n"
    "Example: git checkout -b feature/billing-cuit-validation"
)


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def current_branch() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def check_skipped_verification(cmd: str) -> None:
    if "--no-verify" in cmd or re.search(r"\bSKIP=", cmd):
        deny(
            "BLOCKED — the checks are not skipped (CLAUDE.md §3.4).\n\n"
            "The pre-commit hooks exist precisely to catch what you are about to commit. "
            "If they are failing, fix the cause:\n"
            "    ruff format . && ruff check . --fix && mypy . && pytest"
        )


def check_commit(cmd: str) -> None:
    if not re.search(r"\bgit\s+(-C\s+\S+\s+)?commit\b", cmd):
        return
    branch = current_branch()
    if branch in PROTECTED_BRANCHES:
        deny(
            f"BLOCKED — attempt to commit directly onto the protected branch '{branch}'.\n"
            "Every change is born on a working branch and lands through a Pull Request "
            "(CLAUDE.md §3.1).\n\n"
            "Move your work onto a new branch:\n"
            "    git checkout -b feature/<module>-<description>\n\n" + BRANCH_HELP
        )


def check_push(cmd: str) -> None:
    if not re.search(r"\bgit\s+(-C\s+\S+\s+)?push\b", cmd):
        return

    forced = bool(re.search(r"(^|\s)(--force\b|--force-with-lease\b|-f\b)", cmd))
    protected_target = re.search(
        r"\b(origin|upstream)\s+(?:\+?\S+:)?(main|develop)\b", cmd
    ) or re.search(r"\bpush\b[^|;&]*\b(main|develop)\b", cmd)

    if protected_target:
        branch = protected_target.group(protected_target.lastindex or 0)
        deny(
            f"BLOCKED — direct push to the protected branch '{branch}'.\n"
            "Nobody writes directly to main or develop: everything lands through a "
            "reviewed Pull Request with green CI (CLAUDE.md §3.1).\n\n"
            "Push your working branch and open the PR:\n"
            "    git push -u origin <your-branch>\n"
            "    gh pr create --base develop"
        )

    if forced:
        deny(
            "BLOCKED — forced push.\n"
            "Rewriting published history breaks everyone else's work (CLAUDE.md §3.4).\n\n"
            "To correct commits that are already pushed, do it with a new commit. "
            "If the force really is unavoidable, it needs explicit authorization from "
            "the person in charge (CLAUDE.md §8)."
        )


def check_history(cmd: str) -> None:
    dangerous = re.search(r"\bgit\s+(-C\s+\S+\s+)?(reset\s+--hard|rebase)\b", cmd)
    if not dangerous:
        return
    branch = current_branch()
    if branch in PROTECTED_BRANCHES:
        deny(
            f"BLOCKED — '{dangerous.group(0)}' on the protected branch '{branch}'.\n"
            "Rewriting or discarding the history of main/develop destroys integrated "
            "team work (CLAUDE.md §3.4).\n\n"
            "To undo something that is already on main, use:\n"
            "    git revert <sha>\n"
            "which leaves a record of the change instead of erasing it."
        )


def check_new_branch(cmd: str) -> None:
    match = re.search(
        r"\bgit\s+(?:-C\s+\S+\s+)?(?:checkout\s+-b|switch\s+-c)\s+(?P<name>[^\s;|&]+)",
        cmd,
    )
    if not match:
        return
    # `git checkout -b "feature/x"` is legitimate, and the branch name may also be
    # quoted inside a larger string; the quotes are not part of the name.
    name = match.group("name").strip("\"'`,;")
    if BRANCH_NAMING.match(name):
        return
    deny(f"BLOCKED — '{name}' does not follow the project branch naming scheme.\n\n" + BRANCH_HELP)


def check_bulk_delete(cmd: str) -> None:
    if re.search(r"\brm\s+(-\w*[rR]\w*f|-\w*f\w*[rR])\w*\s+(/|~|\.\s*$|\*)", cmd):
        deny(
            "BLOCKED — forced recursive delete over an overly broad path.\n"
            "Narrow the command down to the specific files you want to remove, "
            "or run 'git clean -n' first to see what would be deleted."
        )


def main() -> None:
    if os.environ.get("CHEATSHEET_UNSAFE") == "1":
        return

    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return

    check_skipped_verification(cmd)
    check_bulk_delete(cmd)
    check_new_branch(cmd)
    check_commit(cmd)
    check_push(cmd)
    check_history(cmd)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — a broken hook must not stall the team
        print(f"[guard_bash] internal hook failure, letting it through: {exc}", file=sys.stderr)
    sys.exit(0)
