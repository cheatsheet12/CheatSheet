#!/usr/bin/env python3
"""Enforces the module boundaries on both sides of the monorepo.

The architecture (ADR-001 in the design documents) is a modular monolith whose
DDD boundaries exist *only at the code level*. That ADR states the boundaries
"hold only if the team respects the dependency rules, and this must be verified in
code review". Code review does not catch this reliably. This does.

Backend — backend/src/cheatsheet/** (ADR-0001):

  R1. `domain/` imports nothing from `application/`, `infrastructure/`, or any
      infrastructure framework. The domain is pure Python.
  R2. `application/` imports nothing from `infrastructure/`. It defines ports;
      infrastructure implements them (Dependency Inversion).
  R3. No module imports another bounded context's `domain/` or `infrastructure/`.
      Cross-context communication goes through `application/` or domain events.
  R4. `shared/` (the Shared Kernel) imports nothing from `contexts/`.

Frontend — dashboard/src/** (ADR-0002):

  R5. A feature never imports another feature's internals, only its `index.ts`;
      `shared/` imports no feature. A screen composing several contexts does so
      in the route, not through a cross-feature import.

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

FRONTEND_PACKAGE = "dashboard/src"

LAYERS = ("domain", "application", "infrastructure")

# The feature's public entry point. Everything else under a feature is internal.
FEATURE_ENTRY_POINT = "index"

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


TS_IMPORT = re.compile(
    r"""(?mx)
    (?: ^\s* import \s+ (?:[^'"]*?\s+from\s+)? | ^\s* export \s+ .*? \s+ from \s+
      | \b (?: import | require ) \s* \( )
    ['"](?P<spec>[^'"]+)['"]
    """
)


def _feature_of(rel_path: str) -> str | None:
    """Feature that a dashboard/src path belongs to, if any."""
    parts = Path(rel_path).parts
    try:
        i = parts.index("features")
    except ValueError:
        return None
    return parts[i + 1] if len(parts) > i + 1 else None


def _resolve_spec(spec: str, from_path: str) -> str | None:
    """Turn an import specifier into a dashboard/src-relative path, if it is internal."""
    if spec.startswith("@/"):
        return f"{FRONTEND_PACKAGE}/{spec[2:]}"
    if spec.startswith("."):
        resolved = (Path(from_path).parent / spec).as_posix()
        # Normalise the .. segments without touching the filesystem.
        stack: list[str] = []
        for part in resolved.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if stack:
                    stack.pop()
                continue
            stack.append(part)
        return "/".join(stack)
    return None  # bare specifier: a node_modules package


def check_frontend(rel_path: str, content: str) -> list[Violation]:
    """R5: features do not reach into each other; shared/ depends on no feature."""
    if not rel_path.endswith((".ts", ".tsx")):
        return []
    normalized = rel_path.replace(os.sep, "/")
    if not normalized.startswith(FRONTEND_PACKAGE):
        return []

    feature = _feature_of(normalized)
    in_shared = normalized.startswith(f"{FRONTEND_PACKAGE}/shared/")
    violations: list[Violation] = []

    for match in TS_IMPORT.finditer(content):
        target = _resolve_spec(match.group("spec"), normalized)
        if target is None:
            continue
        target_feature = _feature_of(target)
        if target_feature is None:
            continue

        if in_shared:
            violations.append(
                Violation(
                    f"R5  shared/ imports '{match.group('spec')}' from feature "
                    f"'{target_feature}'.\n"
                    "    Every feature depends on shared/, so shared/ must depend on none of\n"
                    "    them. Move this code into the feature that owns it."
                )
            )
            continue

        if feature is None or target_feature == feature:
            continue

        # Reaching past the other feature's public entry point.
        tail = target[len(f"{FRONTEND_PACKAGE}/features/{target_feature}") :].strip("/")
        if tail and Path(tail).stem != FEATURE_ENTRY_POINT:
            violations.append(
                Violation(
                    f"R5  feature '{feature}' imports '{match.group('spec')}', reaching into\n"
                    f"    the internals of feature '{target_feature}'.\n"
                    "    Features talk through the other feature's public entry point only.\n"
                    f'    Allowed:  import {{ … }} from "@/features/{target_feature}"\n'
                    "    If the code is genuinely common, it belongs in @/shared instead.\n"
                    "    A screen that composes several contexts does that in the route\n"
                    "    (src/app/…), not through a cross-feature import."
                )
            )

    return violations


def check(rel_path: str, content: str) -> list[Violation]:
    """Return every boundary violation the given file content introduces."""
    if rel_path.endswith((".ts", ".tsx")):
        return check_frontend(rel_path, content)
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


def _files_to_scan(root: Path) -> list[Path]:
    found: list[Path] = []
    backend = root / BACKEND_PACKAGE
    if backend.exists():
        found.extend(sorted(backend.rglob("*.py")))
    frontend = root / FRONTEND_PACKAGE
    if frontend.exists():
        for pattern in ("*.ts", "*.tsx"):
            found.extend(
                f for f in sorted(frontend.rglob(pattern)) if "node_modules" not in f.parts
            )
    return found


def run_scan(root: Path) -> int:
    files = _files_to_scan(root)
    if not files:
        print("Neither package exists yet — nothing to check.")
        return 0

    offending = 0
    for file in files:
        rel = str(file.relative_to(root))
        violations = check(rel, file.read_text(encoding="utf-8"))
        if violations:
            offending += 1
            for violation in violations:
                print(f"{rel}: {violation.splitlines()[0]}")
                for line in violation.splitlines()[1:]:
                    print(f"    {line}")

    if offending:
        print(f"\n{offending} of {len(files)} file(s) violate the architecture boundaries.")
        return 1
    print(f"{len(files)} file(s) checked — architecture boundaries intact.")
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
