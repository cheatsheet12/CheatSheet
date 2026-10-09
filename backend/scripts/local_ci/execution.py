"""Running child processes, with a streamed log and a hard timeout."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

DEFAULT_TIMEOUT_S = 1800.0


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str
    duration_s: float


def use_utf8_console(stream: TextIO) -> None:
    """Make the console accept any character a child prints.

    Redirected output on Windows defaults to the ANSI code page (cp1252), and one
    character it cannot encode (gitleaks prints U+25CB) kills the thread that relays the
    child's output, failing a step that passed.
    """
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(encoding="utf-8", errors="replace")


def resolve_argv(
    argv: Sequence[str], which: Callable[[str], str | None] = shutil.which
) -> list[str]:
    """Replace the command name with the executable PATH resolves it to.

    On Windows `npm` is `npm.cmd`, and CreateProcess does not apply PATHEXT, so the bare
    name never starts. An unknown name is left as is, so the launch error names it.
    """
    found = which(argv[0])
    return [found, *argv[1:]] if found else list(argv)


def emit(text: str = "") -> None:
    """Write one line to the console (this tool's whole output is its console log)."""
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    stdin_text: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    echo: bool = True,
) -> CommandResult:
    """Run `argv`, stream merged stdout/stderr, and return the full output.

    A timeout kills the child and reports exit code 124 (the `timeout(1)` convention).
    """
    started = time.monotonic()
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv is built by this tool, never a shell string
            resolve_argv(argv),
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        return CommandResult(127, f"could not start {argv[0]}: {error}\n", 0.0)

    lines: list[str] = []
    reader = threading.Thread(target=_pump, args=(proc, lines, echo), daemon=True)
    reader.start()
    if stdin_text is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except OSError:
            pass  # the child exited before reading; its exit code tells the story
    try:
        code = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        lines.append(f"\n[local-ci] killed after {timeout_s:.0f}s timeout\n")
        code = 124
    reader.join(timeout=5)
    return CommandResult(code, "".join(lines), time.monotonic() - started)


def _pump(proc: subprocess.Popen[str], sink: list[str], echo: bool) -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        sink.append(line)
        if echo:
            sys.stdout.write("    | " + line)
            sys.stdout.flush()
