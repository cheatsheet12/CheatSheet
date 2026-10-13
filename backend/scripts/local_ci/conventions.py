"""Branch-name and commit-message rules, copied from the `conventions` CI job."""

from __future__ import annotations

import re
from collections.abc import Iterable

FEATURE_OR_FIX = re.compile(r"^(feature|fix)/[a-z0-9_]+-[a-z0-9-]+$")
HOTFIX = re.compile(r"^hotfix/[a-z0-9-]+$")
COMMIT = re.compile(r"^(feat|fix|docs|refactor|test|chore|perf|ci)(\([a-z_]+\))?: .{10,}")


def branch_error(branch: str, target: str) -> str | None:
    """Return why `branch` -> `target` is invalid, or None when it is fine."""
    if FEATURE_OR_FIX.match(branch):
        if target != "develop":
            return f"feature/ and fix/ branches may only target develop (got: {target})."
        return None
    if HOTFIX.match(branch):
        if target != "main":
            return f"hotfix/ branches may only target main (got: {target})."
        return None
    if branch == "develop" and target == "main":
        return None
    return (
        f"'{branch}' does not follow the project naming scheme. "
        "Valid formats: feature/<module>-<desc>, fix/<module>-<desc>, hotfix/<desc>"
    )


def invalid_commit_subjects(subjects: Iterable[str]) -> list[str]:
    """Subjects that break Conventional Commits. Merge commits and blanks are exempt."""
    bad: list[str] = []
    for subject in subjects:
        if not subject or subject.startswith("Merge "):
            continue
        if not COMMIT.match(subject):
            bad.append(subject)
    return bad
