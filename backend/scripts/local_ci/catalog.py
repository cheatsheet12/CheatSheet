"""The ordered list of steps; the order mirrors .github/workflows/ci.yml."""

from __future__ import annotations

from local_ci.model import Step
from local_ci.steps_backend import BACKEND_STEPS
from local_ci.steps_frontend import FRONTEND_STEPS
from local_ci.steps_static import STATIC_STEPS

CATALOGUE: tuple[Step, ...] = (*STATIC_STEPS, *BACKEND_STEPS, *FRONTEND_STEPS)
