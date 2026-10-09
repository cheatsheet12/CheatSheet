"""Windows console and process-launch behaviour of the local CI runner, found on its first
real run. No Docker, no network, no subprocesses."""

from __future__ import annotations

import io
import os
from pathlib import Path

from local_ci.context import build_env
from local_ci.execution import resolve_argv, use_utf8_console


def test_the_verified_checkout_goes_first_on_pythonpath() -> None:
    # A venv shared between worktrees imports `cheatsheet` from wherever its editable
    # install points; the checkout under test must win.
    root = Path("wt")
    env = build_env({"PYTHONPATH": "elsewhere"}, root)

    assert env["PYTHONPATH"].split(os.pathsep) == [str(root / "backend" / "src"), "elsewhere"]


def test_without_a_root_pythonpath_is_untouched() -> None:
    assert "PYTHONPATH" not in build_env({"PATH": "/bin"})


def test_a_bare_command_is_resolved_to_the_executable_on_path() -> None:
    # On Windows `npm` is `npm.cmd`, and CreateProcess does not apply PATHEXT: launching
    # the bare name fails before npm ever runs.
    def which(name: str) -> str | None:
        return r"C:\Program Files\nodejs\npm.CMD" if name == "npm" else None

    assert resolve_argv(["npm", "ci"], which) == [r"C:\Program Files\nodejs\npm.CMD", "ci"]


def test_an_unknown_command_is_left_as_is_so_the_launch_error_names_it() -> None:
    assert resolve_argv(["no-such-tool", "--x"], lambda _: None) == ["no-such-tool", "--x"]


def test_a_redirected_cp1252_console_accepts_any_character_after_switching_to_utf8() -> None:
    # Redirected output on Windows defaults to the ANSI code page; gitleaks prints U+25CB.
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")

    use_utf8_console(console)
    console.write("\u25cb leaks found: 0\n")
    console.flush()

    assert raw.getvalue().decode("utf-8") == "\u25cb leaks found: 0\n"


def test_a_stream_that_cannot_be_reconfigured_is_left_alone() -> None:
    stream = io.StringIO()

    use_utf8_console(stream)
    stream.write("\u25cb")

    assert stream.getvalue() == "\u25cb"
