# Local CI

Runs, on your machine, the steps that [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml)
runs, and prints a Markdown summary you can paste into a Pull Request. Why it exists and when
a summary counts as verification: [ADR-0015](../../../docs/adr/0015-local-ci-verification.md)
(Proposed).

```bash
python backend/scripts/run_local_ci.py                 # everything
python backend/scripts/run_local_ci.py --list          # steps, required or optional
python backend/scripts/run_local_ci.py --only ruff-check mypy      # a subset (+ prerequisites)
python backend/scripts/run_local_ci.py --skip frontend-build
python backend/scripts/run_local_ci.py --keep-containers --output summary.md
```

## Before the first run

- A virtual environment with `pip install -r requirements-dev.txt` and `pip install -e backend/`
  (the script does not install anything, unlike CI).
- **Docker** (Compose v2). Without it the database steps are `SKIPPED`.
- Optional but required for a `COMPLETE` verdict: `jq` and `bash` (guards test),
  `gitleaks` (secret scan), Node 22 + `npm` (frontend gates).
- Ports `5433` (PostgreSQL) and `6380` (Redis) must be free: stop `docker compose up` from
  `backend/` first. The script uses its own compose project (`cheatsheet-localci`) with
  fresh volumes, and removes them at the end unless you pass `--keep-containers`.

## What it guarantees

- Child processes get `DATABASE_URL`, `DATABASE_URL_MIGRATIONS`, `REDIS_URL` and
  `APP_ENV=test` pointing at the local containers. Any ambient value is discarded; no `.env`
  file is read or written. The run aborts if a target host is not local.
- A missing tool is `SKIPPED` with the reason, never `PASS`.
- Exit codes: `0` complete, `1` a step failed, `2` bad arguments, `3` nothing failed but a
  required step was skipped or not run (this includes `--only` subsets).
- The verdict is `COMPLETE` only if every required step passed. `worktree-clean` fails if
  tracked files differ from `HEAD`, so the SHA in the summary is the code that was checked.

## Differences from hosted CI

- Dependencies are not installed by the script.
- `settings.json` is validated in Python instead of `jq` (same condition).
- mypy receives the file list on stdin (Windows command-line length limit); same files.
- The coverage XML report is not written (it is not a gate).
- `deploy-staging` is not reproduced.
- `frontend-build` (`next build`) is an optional extra that CI does not run.

The pure logic (verdict, step selection, host guard, summary, conventions) is covered by
`backend/tests/scripts/`.
