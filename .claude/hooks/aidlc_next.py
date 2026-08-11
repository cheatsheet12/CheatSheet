#!/usr/bin/env python3
"""SessionStart hook: tells the developer what comes next in the AI-DLC roadmap.

A developer opening a cold session should not have to reconstruct where the project
stands. This reads the two planning documents — `docs/aidlc/roadmap.md` (the ordered
epics) and `docs/aidlc/units.md` (the units and their state) — and reports the current
epic, the unit in progress, and the next unit whose dependencies are already merged.

State is DERIVED, never stored twice: an epic is finished when all of its units are
`mergeada`, and it has not started when it has no rows in the units map. There is no
epic-level status column to keep in sync.

If anything is missing or malformed this stays quiet rather than guessing: a wrong
"next step" is worse than none.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unicodedata
from pathlib import Path

ROADMAP = Path("docs") / "aidlc" / "roadmap.md"
UNITS = Path("docs") / "aidlc" / "units.md"

DONE = "mergeada"
IN_PROGRESS = "en curso"
IN_REVIEW = "en revision"

Row = dict[str, str]


def norm(text: str) -> str:
    """Lowercase, strip accents and surrounding whitespace, for tolerant matching."""
    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return all(set(cell) <= {"-", ":", " "} and cell for cell in cells)


def read_table(text: str, required: str) -> list[Row]:
    """Return the rows of the first markdown table whose header contains `required`.

    Keys are normalized headers; values are raw cells.
    """
    headers: list[str] | None = None
    rows: list[Row] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            if headers and rows:
                break
            headers = None
            continue
        cells = split_row(line)
        if headers is None:
            candidate = [norm(cell) for cell in cells]
            headers = candidate if any(required in head for head in candidate) else None
            continue
        if is_separator(cells):
            continue
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells, strict=True)))
    return rows


# A hand-written table marks "nothing here" with a hyphen or a dash. Written as escapes
# because the literal characters are visually ambiguous in source (ruff RUF001).
EMPTY_CELLS = {"", "-", "\u2014", "\u2013", "n/a"}  # hyphen, em dash, en dash


def column(row: Row, wanted: str) -> str:
    """Value of the first column whose header contains `wanted`, or "" if the cell is a dash."""
    for head, value in row.items():
        if wanted in head:
            cleaned = value.strip()
            return "" if cleaned.lower() in EMPTY_CELLS else cleaned
    return ""


def epic_names(text: str) -> list[str]:
    return [name for row in read_table(text, "epico") if (name := column(row, "epico"))]


def unit_state(row: Row) -> str:
    return norm(column(row, "estado"))


def dependencies(row: Row) -> list[str]:
    raw = column(row, "depende")
    return [part.strip() for part in raw.split(",") if part.strip()] if raw else []


def units_of(rows: list[Row], epic: str) -> list[Row]:
    """Units belonging to `epic`. A map without an epic column describes one epic only."""
    scoped = [row for row in rows if column(row, "epico")]
    if not scoped:
        return rows
    return [row for row in scoped if norm(column(row, "epico")) == norm(epic)]


def current_user() -> str:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def describe_units(rows: list[Row], epic: str) -> list[str]:
    """Report the in-progress units and the next one that is actually startable."""
    lines: list[str] = []
    me = norm(current_user())
    done = {norm(column(row, "unidad")) for row in rows if unit_state(row) == DONE}

    for row in rows:
        if unit_state(row) not in {IN_PROGRESS, IN_REVIEW}:
            continue
        unit, who = column(row, "unidad"), column(row, "responsable")
        mine = " ← tuya" if me and norm(who) == me else ""
        lines.append(f"    · {unit} — {unit_state(row)} ({who or 'sin responsable'}){mine}")

    ready = [
        row
        for row in rows
        if unit_state(row) not in {IN_PROGRESS, IN_REVIEW, DONE}
        and all(norm(dep) in done for dep in dependencies(row))
    ]
    if ready:
        nxt = ready[0]
        who = column(nxt, "responsable")
        lines.append(
            f"  - Próxima unidad disponible: {column(nxt, 'unidad')} "
            f"({column(nxt, 'contexto') or 'contexto sin declarar'}"
            f"{', asignada a ' + who if who else ', sin asignar'}). "
            "Leé su fila en docs/aidlc/units.md y abrí el Gate 1 con su plan."
        )
    elif not lines:
        lines.append(
            f"  - Todas las unidades restantes de «{epic}» están bloqueadas por dependencias. "
            "Revisá docs/aidlc/units.md."
        )
    return lines


def status(root: Path) -> list[str]:
    roadmap, units_file = root / ROADMAP, root / UNITS
    if not roadmap.exists():
        return [
            "- AI-DLC: todavía no hay roadmap. El primer paso es la sesión de roadmap "
            "(.claude/aidlc/workflow.md, Paso previo)."
        ]
    try:
        epics = epic_names(roadmap.read_text(encoding="utf-8"))
        rows: list[Row] = []
        if units_file.exists():
            rows = read_table(units_file.read_text(encoding="utf-8"), "unidad")
    except OSError:
        return ["- AI-DLC: el roadmap o el mapa de unidades no se pudieron leer."]
    if not epics:
        return ["- AI-DLC: docs/aidlc/roadmap.md no tiene una tabla de épicos legible."]

    for position, epic in enumerate(epics, start=1):
        scoped = units_of(rows, epic)
        if scoped and all(unit_state(row) == DONE for row in scoped):
            continue
        header = f"- AI-DLC — épico {position}/{len(epics)} en curso: «{epic}»"
        if not scoped:
            return [
                header.replace("en curso", "sin mapear"),
                "  - Todavía no tiene unidades. Corresponde la sesión de mapeo "
                "(.claude/aidlc/workflow.md, paso 1a) antes de codear.",
            ]
        return [header, *describe_units(scoped, epic)]

    return [f"- AI-DLC: los {len(epics)} épicos del roadmap están completos."]


def main() -> None:
    root = Path.cwd()
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(status(root)),
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — informational, must never stall the session
        print(f"[aidlc_next] internal failure: {exc}", file=sys.stderr)
    sys.exit(0)
