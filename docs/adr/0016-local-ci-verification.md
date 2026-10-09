# ADR-0016 — Verify locally with the full CI summary while hosted CI is unavailable

- **Status:** Proposed
- **Date:** 2026-10-08
- **Decided by:** Person in charge of the repository (Luciano) — proposal for the team to accept or reject
- **Modules affected:** infra

---

## Context

The GitHub Actions minutes of the organization are exhausted until 1 November. Every
workflow run fails within seconds, before any step executes, so no Pull Request can show
a green `CI` check and nothing that `ci.yml` verifies is being verified.

[`CLAUDE.md`](../../CLAUDE.md) §3.4 forbids bypassing CI, and the Definition of Done (§7)
is only meaningful if its checks run somewhere. At the same time:

- `develop` and `main` have **no branch protection** (the repository is private on the
  GitHub Free plan, which does not offer it). Nothing technically stops a merge with a red
  or missing check, so the rule is enforced by discipline alone — which is exactly what
  weakens when the pipeline is broken for weeks.
- Work on the Core contexts (money, tax documents, tenant isolation) keeps arriving, and
  several gates in `ci.yml` exist precisely for them: Row-Level Security verification
  against a real PostgreSQL, the BYPASSRLS negative check, the integration suite that must
  not skip, and the 80% coverage threshold.
- A remote Neon test database exists but, over the team's network, is too slow and jittery
  to be the default for the integration suite.
- Docker is the missing piece on the main development machine today; it is being
  installed.

The question is how to keep merging safely, and honestly, for the weeks the hosted pipeline
is unavailable.

## Decision

While hosted CI is unavailable, **a Pull Request may be merged only if the summary produced
by `python backend/scripts/run_local_ci.py` is pasted into the PR and shows verdict
`COMPLETE`**, in addition to the usual review.

Details:

1. **The script reproduces `ci.yml` locally**, step by step (conventions, ruff, mypy,
   architecture, guards, gitleaks, PostgreSQL 16 + Redis through `docker compose`,
   provisioning, migrations, `verify_rls.py` and its negative check, full pytest with
   coverage, the no-skip integration run, and the frontend gates). It is documented in
   [`backend/scripts/local_ci/README.md`](../../backend/scripts/local_ci/README.md).
2. **Required steps.** Every step that `ci.yml` runs as a gate is required. That is all of
   them except `frontend-build`, an extra that CI does not run today. The summary's verdict
   is `COMPLETE` only if no step failed and every required step passed. A step that could
   not run (missing Docker, `jq`, `gitleaks`, Node) is reported `SKIPPED`, never as passed,
   and makes the verdict `INCOMPLETE`.
3. **Run on the PR's head commit.** The summary carries the commit SHA, and a required step
   fails if tracked files differ from `HEAD`. The SHA in the summary must equal the PR's
   head SHA; any later push requires a new run.
4. **Who may merge.** The same rule as always: another person reviews, or the person in
   charge merges their own unit as already agreed. Reviewers may ask to re-run the script
   on the head commit and compare.
5. **Temporary by construction.** The rule ends on its own the day hosted CI runs again.
   From then on a green `CI` check on the PR is required as before, and **hosted CI must be
   re-run on `develop`** for everything merged under this ADR (a push to `develop` already
   triggers it); a failure found there is fixed with priority.
6. **Not allowed under this ADR:** skipping required steps, partial runs (`--only`,
   `--skip`) presented as complete, `--no-verify`, `CHEATSHEET_UNSAFE=1`, lowering the
   coverage threshold, editing `ci.yml` or the script to make a step pass, or pasting a
   summary produced from a different commit.
7. **Safety of the run itself.** The script starts its own disposable containers (compose
   project `cheatsheet-localci`, fresh volumes every run), builds every database URL itself,
   and refuses to run if any target host is not local. It never reads or writes `.env`
   files.

If accepted, `CLAUDE.md` §3.4 needs a one-line amendment pointing to this ADR as the
documented exception; this ADR does not change `CLAUDE.md`.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| Pay for more Actions minutes with a spending cap | Cheapest and the real fix: keeps CI identical, hosted and independent of anyone's machine | Not ruled out — **recommended for the long term**. It depends on the organization's billing, so this ADR covers the gap until it happens |
| Self-hosted runner | Runs the same `ci.yml` unchanged | Needs an always-on machine, its maintenance and a secure setup for a private repository; disproportionate for a few weeks |
| Run the integration suite against the remote Neon test database | No Docker needed | Too slow and unstable over this network, and it would not replace the disposable-container property the RLS checks rely on |
| Merge without verification until Actions is back | Zero effort | Rejected: merges to `develop` auto-deploy to staging, and the Core contexts handle money and tax documents |
| Only run ruff/mypy/pytest by hand and say so in the PR | Simple | Unreproducible and inconsistent between people; skips the RLS, integration and guard checks that need services |

## Consequences

**Positive**
- Every merge in the period is backed by the same checks CI performs, including the ones
  that need PostgreSQL and Redis.
- The summary is a uniform, paste-ready artifact, and the verdict logic is unit tested.
- The script keeps its value afterwards: a full pre-push check on a developer machine.

**Negative / cost we accept**
- Merges depend on a person running the script and reporting honestly. The SHA, the clean
  working tree requirement and the reviewer's option to re-run reduce, but do not remove,
  that trust.
- Environment drift is possible: developers run Windows (or macOS) while CI ran
  `ubuntu-latest`. Differences in line endings, paths, shell and tool versions can make a
  step pass locally and fail in CI, or the reverse. The re-run of hosted CI on `develop`
  (point 5) is what catches this.
- A full run is slow (containers, the whole test suite, frontend install).

**What becomes harder from now on**
- Keeping the script in sync with `ci.yml`: a new CI step must be added to the script
  while this tool exists.
- The `deploy-staging` job is not reproduced (it needs secrets and acts on shared
  infrastructure); it keeps running only on hosted CI.

## Impact on repository rules

- [x] [`CLAUDE.md`](../../CLAUDE.md) — §3.4 needs a one-line amendment once this ADR is accepted (not done here)
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [x] [`pyproject.toml`](../../pyproject.toml) — `backend/scripts` joins pytest's `pythonpath` and mypy's `mypy_path` so the script's tests run and are type-checked
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [ ] `backend/.env.example` or `frontend/.env.example`
- [ ] None

## References

- [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — the pipeline being reproduced
- [`backend/scripts/local_ci/README.md`](../../backend/scripts/local_ci/README.md) — usage
- [ADR-0005](0005-staging-database-neon.md) — the tenant barrier verified by `verify_rls.py`
- [`docs/aidlc/units/infra-ci-local.md`](../aidlc/units/infra-ci-local.md) — the unit plan
