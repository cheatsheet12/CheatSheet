#!/usr/bin/env python3
"""Enforces the hexagonal and bounded-context boundaries of the backend.

The architecture (ADR-001 in the design documents) is a modular monolith whose
DDD boundaries exist *only at the code level*. That ADR states the boundaries
"hold only if the team respects the dependency rules, and this must be verified in
code review". Code review does not catch this reliably. This does.

Four rules, applied to backend/src/cheatsheet/**:

  R1. `domain/` imports nothing from `application/`, `infrastructure/`, or any
      infrastructure framework. The domain is pure Python.
  R2. `application/` imports nothing from `infrastructure/`. It defines ports;
      infrastructure implements them (Dependency Inversion).
  R3. No module imports another bounded context's `domain/` or `infrastructure/`.
      Cross-context communication goes through `application/` or domain events.
  R4. `shared/` (the Shared Kernel) imports nothing from `contexts/`.

Two modes:

    # Hook mode: PreToolUse payload on stdin, blocks the write
    python3 guard_architecture.py

    # Scan mode: walks the tree, used by CI to check files already on disk
    python3 guard_architecture.py --scan [repo_root]

Emergency escape hatch: CHEATSHEET_UNSAFE=1 (see CLAUDE.md §8).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BACKEND_PACKAGE = "backend/src/cheatsheet"
ROOT_MODULE = "cheatsheet"

LAYERS = ("domain", "application", "infrastructure")

# Frameworks and drivers that must never appear inside a domain layer. The domain
# describes the business, not how it is stored, served or transported.
INFRASTRUCTURE_IMPORTS = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "asyncpg",
    "psycopg",
    "psycopg2",
    "redis",
    "celery",
    "httpx",
    "requests",
    "aiohttp",
    "boto3",
    "botocore",
    "zeep",
    "pyafipws",
}

# `from X import ...` / `import X`
IMPORT_LINE = re.compile(
    r"^\s*(?:from\s+(?P<from>[.\w]+)|import\s+(?P<import>[.\w]+))", re.MULTILINE
)


class Violation(str):
    """A single boundary violation, rendered as its explanatory message."""


def _layer_of(rel_path: str) -> tuple[str | None, str | None]:
    """Return (context, layer) for a path under contexts/, else (None, None)."""
    parts = Path(rel_path).parts
    try:
        i = parts.index("contexts")
    except ValueError:
        return None, None
    context = parts[i + 1] if len(parts) > i + 1 else None
    layer = parts[i + 2] if len(parts) > i + 2 and parts[i + 2] in LAYERS else None
    return context, layer


def _imported_modules(content: str) -> list[str]:
    found: list[str] = []
    for match in IMPORT_LINE.finditer(content):
        module = match.group("from") or match.group("import")
        if module:
            found.append(module)
    return found


def _target_of(module: str) -> tuple[str | None, str | None]:
    """Return (context, layer) that an absolute cheatsheet import points at."""
    parts = module.split(".")
    if not parts or parts[0] != ROOT_MODULE:
        return None, None
    if len(parts) < 3 or parts[1] != "contexts":
        return None, None
    context = parts[2]
    layer = parts[3] if len(parts) > 3 and parts[3] in LAYERS else None
    return context, layer


def check(rel_path: str, content: str) -> list[Violation]:
    """Return every boundary violation the given file content introduces."""
    if not rel_path.endswith(".py"):
        return []
    normalized = rel_path.replace(os.sep, "/")
    if not normalized.startswith(BACKEND_PACKAGE):
        return []

    context, layer = _layer_of(normalized)
    in_shared = "/shared/" in f"/{normalized}/"
    violations: list[Violation] = []

    for module in _imported_modules(content):
        root = module.lstrip(".").split(".")[0]
        target_context, target_layer = _target_of(module)

        # R1 — no infrastructure frameworks inside the domain.
        if layer == "domain" and root in INFRASTRUCTURE_IMPORTS:
            violations.append(
                Violation(
                    f"R1  domain layer imports the infrastructure package '{root}'.\n"
                    f"    The domain of '{context}' must be pure Python: it describes the\n"
                    "    business, not how data is stored, served or transported.\n"
                    f"    Move this to contexts/{context}/infrastructure/ and reach it\n"
                    f"    through a port defined in contexts/{context}/application/ports.py."
                )
            )

        # R1 — no domain -> application/infrastructure, in any context.
        if layer == "domain" and target_layer in {"application", "infrastructure"}:
            violations.append(
                Violation(
                    f"R1  domain layer imports '{module}' ({target_layer} layer).\n"
                    "    Dependencies point inwards only: infrastructure -> application -> domain.\n"
                    "    If the domain needs something from outside, it must arrive as an\n"
                    "    argument or through a port, never as an import."
                )
            )

        # R2 — no application -> infrastructure.
        if layer == "application" and target_layer == "infrastructure":
            violations.append(
                Violation(
                    f"R2  application layer imports '{module}' (infrastructure layer).\n"
                    "    Application defines ports; infrastructure implements them.\n"
                    f"    Declare the port in contexts/{context}/application/ports.py and let\n"
                    "    the composition root inject the adapter."
                )
            )

        # R3 — no reaching into another context's internals.
        crosses_context = bool(target_context and context and target_context != context)
        if crosses_context and target_layer in {"domain", "infrastructure"}:
            violations.append(
                Violation(
                    f"R3  context '{context}' imports '{module}', which reaches into the\n"
                    f"    {target_layer} of context '{target_context}'.\n"
                    "    Bounded contexts only talk through the other context's application\n"
                    "    layer (its public API) or through domain events.\n"
                    f"    Allowed:  from {ROOT_MODULE}.contexts.{target_context}.application import ...\n"
                    "    See the Context Map in docs/architecture.md for which contexts may\n"
                    "    depend on which."
                )
            )

        # R4 — the Shared Kernel depends on nobody.
        if in_shared and target_context:
            violations.append(
                Violation(
                    f"R4  shared/ imports '{module}' from a bounded context.\n"
                    "    The Shared Kernel is depended upon by every context, so it must not\n"
                    "    depend on any of them. Move this code into the context that owns it."
                )
            )

    return violations


# --------------------------------------------------------------------------
# Hook mode
# --------------------------------------------------------------------------


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


def incoming_content(tool_input: dict[str, object]) -> str:
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


def run_hook() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path:
        return

    path = Path(raw_path)
    root = Path.cwd()
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            root = candidate
            break

    try:
        rel_path = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return

    violations = check(rel_path, incoming_content(tool_input))
    if violations:
        detail = "\n\n".join(violations)
        deny(
            f"BLOCKED — architecture boundary violation in '{rel_path}'.\n\n{detail}\n\n"
            "These boundaries are what makes the modular monolith modular. Once they\n"
            "erode the system becomes a big ball of mud and no context can ever be\n"
            "extracted into its own service."
        )


# --------------------------------------------------------------------------
# Scan mode (CI)
# --------------------------------------------------------------------------


def run_scan(root: Path) -> int:
    package = root / BACKEND_PACKAGE
    if not package.exists():
        print(f"No backend package at {BACKEND_PACKAGE} — nothing to check.")
        return 0

    total = 0
    offending = 0
    for file in sorted(package.rglob("*.py")):
        total += 1
        rel = str(file.relative_to(root))
        violations = check(rel, file.read_text(encoding="utf-8"))
        if violations:
            offending += 1
            for violation in violations:
                print(f"{rel}: {violation.splitlines()[0]}")
                for line in violation.splitlines()[1:]:
                    print(f"    {line}")

    if offending:
        print(f"\n{offending} of {total} file(s) violate the architecture boundaries.")
        return 1
    print(f"{total} file(s) checked — architecture boundaries intact.")
    return 0


def main() -> int:
    if os.environ.get("CHEATSHEET_UNSAFE") == "1":
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
        return run_scan(root)
    run_hook()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — a broken hook must not stall the team
        print(f"[guard_architecture] internal failure, letting it through: {exc}", file=sys.stderr)
        sys.exit(0)
