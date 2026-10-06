# Backend image — one image, three commands.
#
# The API, the Celery workers and Beat are the same code with a different entrypoint,
# so they share this image. Only the API is deployed today (see the R1 decision in
# docs/aidlc/units/infra-staging-deployment.md); the other two are one `command:` away
# and deliberately need no second image, which is how one of them would end up running
# older code against a newer schema.
#
#   API    uvicorn cheatsheet.api.main:create_app --factory --host 0.0.0.0 --port $PORT
#   worker celery -A cheatsheet.workers.main:app worker -Q <queues> -c <n>
#   beat   celery -A cheatsheet.workers.main:app beat
#
# Migrations are NOT run from here. They run in the deploy workflow, as the owner role,
# before the new image is released — see .github/workflows/deploy-staging.yml.

# Same minor as CI (PYTHON_VERSION in ci.yml) and as pyproject's requires-python.
# A different minor here would mean staging runs a Python nobody tested against.
FROM python:3.11-slim-bookworm

# - PYTHONDONTWRITEBYTECODE: no .pyc in a layer nothing will reuse.
# - PYTHONUNBUFFERED: structlog writes to stdout and the platform reads it live; a
#   buffered stream means logs arrive after the crash they were supposed to explain.
# - PIP_NO_CACHE_DIR: the wheel cache would be baked into the image and never used.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# asyncpg, argon2-cffi and cryptography publish manylinux wheels for CPython 3.11, so
# no compiler is needed and none is installed: a build toolchain in a runtime image is
# attack surface that never runs. If a dependency ever arrives without a wheel, the
# build fails loudly here rather than silently shipping a compiler.

# The build context is `backend/`, not the repository root: this image needs nothing
# from `frontend/` or `docs/`, and a context is uploaded to the builder in full. It is
# also what lets `.dockerignore` live in `backend/` — CLAUDE.md §2.3, a config file that
# affects one package belongs inside that package.

# Dependency metadata first, so that editing application code does not reinstall every
# dependency. The editable install needs the package importable at install time, hence
# src/ comes along.
COPY pyproject.toml ./
COPY src ./src
RUN pip install -e .

# Everything the three commands read at runtime. Alembic is here for the operator who
# needs to inspect a revision from inside the container — the deploy runs it outside.
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

# Non-root. The process needs to read the image and write nothing.
RUN useradd --create-home --uid 10001 cheatsheet
USER cheatsheet

# Documentation only: the platform injects $PORT and the command binds to it.
EXPOSE 8000

# `--factory` because api/main.py exposes `create_app()` rather than a module-level app,
# so that a test can build an application with its own resources (its own docstring
# says so).
#
# The `sh -c exec` dance is not decoration. $PORT is injected by the platform and has
# to be expanded at run time, which needs a shell; but a plain shell-form CMD leaves
# `sh` as PID 1, and the SIGTERM the platform sends on every deploy would go to the
# shell instead of to uvicorn. The application would be killed rather than closed, and
# `ciclo_de_vida` in api/main.py — which awaits `recursos.cerrar()` — would never run,
# leaking the database pool and the Redis connection on each release. `exec` replaces
# the shell with uvicorn, so the signal reaches the process that knows what to do.
CMD ["sh", "-c", "exec uvicorn cheatsheet.api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
