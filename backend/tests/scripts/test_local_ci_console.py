"""Windows console and process-launch behaviour of the local CI runner, found on its first
real run. No Docker, no network, no subprocesses."""

from __future__ import annotations

import io
import os
from pathlib import Path

from local_ci.context import build_env
from local_ci.execution import resolve_argv, use_utf8_console
from local_ci.steps_frontend import format_args
from local_ci.steps_static import installed_gitleaks_version, pinned_gitleaks_version


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


def test_the_pinned_gitleaks_version_is_read_from_the_workflow() -> None:
    workflow = (
        "      - name: Install gitleaks\n"
        "        run: |\n"
        "          VERSION=8.21.2\n"
        '          curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}"\n'
    )
    assert pinned_gitleaks_version(workflow) == "8.21.2"


def test_the_real_workflow_still_pins_a_gitleaks_version() -> None:
    # If ci.yml stops pinning, the local scan silently stops matching CI.
    workflow = (Path(__file__).resolve().parents[3] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    assert pinned_gitleaks_version(workflow) is not None


def test_the_installed_version_ignores_the_v_prefix_and_newline() -> None:
    assert installed_gitleaks_version("v8.30.1\n") == "8.30.1"
    assert installed_gitleaks_version("8.21.2") == "8.21.2"


def test_an_autocrlf_checkout_lets_prettier_accept_crlf_on_disk() -> None:
    assert format_args("true\n") == ("run", "format:check", "--", "--end-of-line", "auto")


def test_any_other_checkout_runs_the_ci_format_check_unchanged() -> None:
    assert format_args("") == ("run", "format:check")
    assert format_args("input") == ("run", "format:check")
