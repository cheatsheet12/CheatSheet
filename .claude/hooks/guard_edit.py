#!/usr/bin/env python3
"""PreToolUse hook (Write|Edit): blocks writes that violate the repository rules.

Rules enforced (see CLAUDE.md §3):
  1. No writing while standing on `main` or `develop`.
  2. No committing credential files (.env, *.pem, *.key, *.p12, *.crt).
  3. No new top-level directories without an approved ADR.
  4. No hardcoded secrets.
  5. No Decimal built from a float literal (rounding bug in money handling).

Every block returns a message stating exactly how to get unstuck.

Emergency escape hatch: CHEATSHEET_UNSAFE=1 (see CLAUDE.md §8).
If this script fails internally it lets the operation through and warns on stderr:
a broken hook must not leave the team unable to work. CI is the backstop.

Note for maintainers: this file is itself subject to its own rules, so the block
messages below deliberately avoid spelling out the forbidden literals.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

PROTECTED_BRANCHES = {"main", "develop"}

# Directories allowed at the repository root.
# EXTENDING THIS LIST REQUIRES AN APPROVED ADR IN docs/adr/ (see CLAUDE.md §2).
# Current set follows ADR-0001 (repository structure).
ALLOWED_TOPLEVEL = {
    ".claude",
    ".github",
    "backend",
    "frontend",
    "docs",
}

# Files that configure ONE application and therefore belong inside its package,
# never at the repository root. The root is for what governs the whole repository
# (see CLAUDE.md §2.3); a package's own config belongs next to the package.
MISPLACED_AT_ROOT: dict[str, str] = {
    ".env.example": "backend/ and frontend/ each keep their own — an env file lives "
    "next to the process that reads it",
    "package.json": "frontend/",
    "package-lock.json": "frontend/",
    "tsconfig.json": "frontend/",
    "next.config.js": "frontend/",
    "next.config.mjs": "frontend/",
    "next.config.ts": "frontend/",
    "tailwind.config.ts": "frontend/",
    "postcss.config.js": "frontend/",
    "eslint.config.js": "frontend/",
    ".eslintrc.json": "frontend/",
    "requirements.txt": "backend/ — the root only pins the tooling that checks the "
    "whole repository, not the application's dependencies",
    "alembic.ini": "backend/",
    "dockerfile": "backend/ or frontend/ — each application builds its own image",
}

# Credential files that are never committed.
FORBIDDEN_FILES = re.compile(
    r"(^|/)(\.env(\.[\w-]+)?$|.*\.(pem|key|p12|pfx|crt|cer|jks|keystore)$)",
    re.IGNORECASE,
)

# `.env.example` matches the pattern above but is precisely the file the rules require
# you to keep up to date: it is the versioned template, and it holds no real values.
CREDENTIAL_TEMPLATES = {".env.example", ".env.template", ".env.sample"}

# Extensions where scanning for secrets makes no sense (docs and templates).
SCAN_EXEMPT_SUFFIXES = {".md", ".rst", ".txt"}

# Patterns for concrete credentials.
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic API key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}"), "OpenAI API key"),
    (re.compile(r"\b(ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"APP_USR-[0-9a-zA-Z\-]{20,}"), "MercadoPago access token"),
    (re.compile(r"EAA[A-Za-z0-9]{40,}"), "WhatsApp Business / Meta token"),
    (
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
        "private key",
    ),
]

# Generic assignment of a secret to a variable.
SECRET_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b (?: api[_-]?key | secret | token | password | passwd | credential )
    \w* \s* [:=] \s*
    ["'] (?P<value> [^"'\s]{8,}) ["']
    """
)

# Values that look like secrets but are legitimate placeholders.
PLACEHOLDERS = re.compile(
    r"""(?ix)
    ^ (?:
        (?:your|my|the)[-_ ] | < | \{\{ | \$\{ |
        x{4,} | \*{4,} | \.{3,} |
        (?: change[-_ ]?me | replace[-_ ]?me | placeholder | example | sample
          | dummy | fake | test | none | null | todo | pending )
    )
    """
)

# Decimal built from a float literal loses precision before it is ever rounded.
DECIMAL_FROM_FLOAT = re.compile(r"\bDecimal\(\s*-?\d+\.\d+\s*\)")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def deny(reason: str) -> None:
    """Block the operation, emitting the payload the hook protocol expects."""
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


def nearest_existing_dir(path: Path) -> Path:
    """First directory that actually exists, walking up from `path`.

    The file about to be written may live in a directory that does not exist yet;
    without this, `git rev-parse` would run from the cwd and the rules of the wrong
    repository would be evaluated.
    """
    current = path.parent
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def repo_root(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def current_branch(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def incoming_content(tool_input: dict[str, object]) -> str:
    """Text the tool intends to write, whether Write, Edit or MultiEdit."""
    parts: list[str] = []
    for key in ("content", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            parts.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict):
                value = edit.get("new_string")
                if isinstance(value, str):
                    parts.append(value)
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def check_branch(root: Path) -> None:
    branch = current_branch(root)
    if branch is None or branch not in PROTECTED_BRANCHES:
        return
    deny(
        f"BLOCKED — you are standing on the protected branch '{branch}'.\n"
        "Nobody writes directly to main or develop (CLAUDE.md §3.1).\n\n"
        "Create a working branch with a valid name to continue:\n"
        "    git checkout -b feature/<module>-<kebab-description>\n"
        "    git checkout -b fix/<module>-<kebab-description>\n\n"
        "Modules: identity, master_data, business_config, integrations, spreadsheet_sync, billing, payments, scheduling, conversational, observability, reporting, reference_data, frontend, infra.\n"
        "Example:  git checkout -b feature/billing-cuit-validation"
    )


def check_path(rel_path: str) -> None:
    is_template = Path(rel_path).name.lower() in CREDENTIAL_TEMPLATES
    if not is_template and FORBIDDEN_FILES.search(rel_path):
        deny(
            f"BLOCKED — '{rel_path}' is a credential file and is never committed "
            "(CLAUDE.md §3.3).\n\n"
            "To declare a new variable, add it EMPTY to .env.example:\n"
            "    MY_VARIABLE=\n"
            "Real values are distributed over a private, encrypted channel "
            "(docs/configuration-management.md §4.3)."
        )

    parts = Path(rel_path).parts

    # A file sitting loose at the root that only configures one application.
    if len(parts) == 1:
        belongs = MISPLACED_AT_ROOT.get(parts[0].lower())
        if belongs:
            deny(
                f"BLOCKED — '{rel_path}' configures a single application, so it does not "
                "belong at the repository root.\n\n"
                f"    It belongs in: {belongs}\n\n"
                "The root is reserved for what governs the whole repository: the tooling\n"
                "configuration that checks every package (pyproject.toml,\n"
                "requirements-dev.txt), the repo-wide policies (.gitignore, .gitleaks.toml,\n"
                ".pre-commit-config.yaml) and the documentation. See CLAUDE.md §2.3."
            )

    if len(parts) > 1 and parts[0] not in ALLOWED_TOPLEVEL:
        allowed = ", ".join(sorted(ALLOWED_TOPLEVEL))
        deny(
            f"BLOCKED — '{parts[0]}/' is not an allowed top-level directory.\n"
            f"Allowed today: {allowed}\n\n"
            "The system architecture has not been decided yet (CLAUDE.md §2), so "
            "creating structure by hand fragments the repository.\n\n"
            "To enable a new directory:\n"
            "  1. Write the ADR: copy docs/adr/0000-template.md to docs/adr/NNNN-title.md\n"
            "  2. Get it approved through a PR\n"
            "  3. Add the directory to ALLOWED_TOPLEVEL in .claude/hooks/guard_edit.py"
        )


def check_content(rel_path: str, content: str) -> None:
    if not content:
        return

    suffix = Path(rel_path).suffix.lower()
    scan_secrets = suffix not in SCAN_EXEMPT_SUFFIXES and not rel_path.endswith(".env.example")

    if scan_secrets:
        for pattern, description in SECRET_PATTERNS:
            if pattern.search(content):
                deny(
                    f"BLOCKED — the content contains what looks like a {description} "
                    f"(file '{rel_path}').\n"
                    "No credential is ever written into the code (CLAUDE.md §3.2).\n\n"
                    "Do it this way:\n"
                    "    import os\n"
                    '    token = os.environ["MY_TOKEN"]\n\n'
                    "And declare MY_TOKEN empty in .env.example, in the same PR."
                )

        for match in SECRET_ASSIGNMENT.finditer(content):
            value = match.group("value")
            if PLACEHOLDERS.match(value) or "os.environ" in value or "getenv" in value:
                continue
            snippet = match.group(0).split("\n")[0][:60]
            deny(
                f"BLOCKED — hardcoded secret assignment in '{rel_path}':\n"
                f"    {snippet}...\n\n"
                "No key, token or password goes into the code (CLAUDE.md §3.2).\n"
                "Read it from an environment variable and declare it empty in .env.example.\n\n"
                "If this is a test value, name it unambiguously "
                '(for example "fake-token-for-tests") so it does not trip this rule.'
            )

    # Code only: the documentation shows this antipattern on purpose.
    if suffix == ".py" and DECIMAL_FROM_FLOAT.search(content):
        deny(
            f"BLOCKED — '{rel_path}' builds a Decimal from a float literal.\n"
            "A float literal has already lost precision before Decimal ever sees it, "
            "which ends up as miscalculated cents on tax documents "
            "(docs/code-standards.md §2.5).\n\n"
            "    WRONG:   Decimal(<float literal>)\n"
            '    RIGHT:   Decimal("0.1")   <- build it from a string'
        )


# --------------------------------------------------------------------------


def main() -> None:
    if os.environ.get("CHEATSHEET_UNSAFE") == "1":
        return

    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path:
        return

    path = Path(raw_path)
    root = repo_root(nearest_existing_dir(path))
    if root is None:
        return

    try:
        rel_path = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return  # File outside the repository: no project rule applies.

    check_branch(root)
    check_path(rel_path)
    check_content(rel_path, incoming_content(tool_input))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — a broken hook must not stall the team
        print(f"[guard_edit] internal hook failure, letting it through: {exc}", file=sys.stderr)
    sys.exit(0)
