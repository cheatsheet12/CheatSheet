"""Command-line entry point: parse options, run, print the summary, tear down."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from local_ci.catalog import CATALOGUE
from local_ci.context import Context, build_env
from local_ci.execution import emit, use_utf8_console
from local_ci.model import EXIT_USAGE, decide_verdict, exit_code_for
from local_ci.runner import run_steps
from local_ci.selection import UnknownStepError, select_steps
from local_ci.steps_backend import teardown_services
from local_ci.steps_static import current_branch, head_sha
from local_ci.summary import RunMeta, render_summary


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_local_ci.py",
        description="Run, locally, the steps that .github/workflows/ci.yml runs.",
    )
    parser.add_argument(
        "--only", nargs="+", metavar="STEP", help="run just these (+ prerequisites)"
    )
    parser.add_argument("--skip", nargs="+", default=[], metavar="STEP", help="leave these out")
    parser.add_argument("--list", action="store_true", help="list the steps and exit")
    parser.add_argument("--keep-containers", action="store_true", help="do not tear down Docker")
    parser.add_argument("--target-branch", default="develop", help="PR target (default: develop)")
    parser.add_argument("--base-ref", default="origin/develop", help="ref commits are checked from")
    parser.add_argument("--output", type=Path, help="also write the summary to this file")
    parser.add_argument(
        "--root",
        type=Path,
        help="checkout to verify (default: the one this script lives in), e.g. another worktree",
    )
    return parser.parse_args(argv)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def print_catalogue() -> None:
    for step in CATALOGUE:
        flag = "required" if step.required else "optional"
        emit(f"{step.step_id:<22} {flag:<9} {step.command}")


def build_meta(ctx: Context) -> RunMeta:
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S")
    return RunMeta(
        sha=head_sha(ctx),
        branch=current_branch(ctx),
        target=ctx.target_branch,
        date_utc=now,
        machine=f"{platform.system()} {platform.release()}, Python {platform.python_version()}",
    )


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8_console(sys.stdout)
    args = parse_args(argv)
    if args.list:
        print_catalogue()
        return 0
    try:
        selected = select_steps(CATALOGUE, args.only, args.skip)
    except UnknownStepError as error:
        sys.stderr.write(f"error: {error}\n")
        return EXIT_USAGE

    root = args.root.resolve() if args.root else repo_root()
    ctx = Context(
        root=root,
        env=build_env(os.environ, root),
        target_branch=args.target_branch,
        base_ref=args.base_ref,
    )
    try:
        results = run_steps(ctx, CATALOGUE, selected)
    finally:
        if ctx.state.get("services_started") and not args.keep_containers:
            emit("\n==> tearing down containers")
            teardown_services(ctx)

    verdict = decide_verdict(results)
    summary = render_summary(results, verdict, build_meta(ctx))
    emit("\n" + summary)
    if args.output:
        args.output.write_text(summary, encoding="utf-8")
    return exit_code_for(verdict)
