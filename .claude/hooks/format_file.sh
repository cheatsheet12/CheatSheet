#!/usr/bin/env bash
# PostToolUse hook (Write|Edit): formats the file that was just written.
#
# Never blocks. If the tool is not installed, it does nothing.
# The real gate is `ruff format --check` in CI; this only saves the team from
# wasting time on formatting differences.

set -uo pipefail

file="$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')"
[ -n "$file" ] || exit 0
[ -f "$file" ] || exit 0

root="$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)" || exit 0

# ruff from the project virtual environment, or whichever one is on PATH.
ruff_bin=""
if [ -x "$root/.venv/bin/ruff" ]; then
  ruff_bin="$root/.venv/bin/ruff"
elif command -v ruff > /dev/null 2>&1; then
  ruff_bin="ruff"
fi

case "$file" in
  *.py)
    [ -n "$ruff_bin" ] || exit 0
    "$ruff_bin" format --quiet "$file" 2> /dev/null
    "$ruff_bin" check --quiet --fix-only "$file" 2> /dev/null
    ;;
  *.ts | *.tsx | *.js | *.jsx | *.css | *.json)
    [ -x "$root/dashboard/node_modules/.bin/prettier" ] || exit 0
    "$root/dashboard/node_modules/.bin/prettier" --write --log-level error "$file" 2> /dev/null
    ;;
esac

exit 0
