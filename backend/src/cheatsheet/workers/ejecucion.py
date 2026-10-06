"""How a Celery task gets from synchronous code into an async world, safely.

**This module exists because of a defect QA found by sending two invitations.** The first
email went out; the second failed with `got Future attached to a different loop`, and
every one after it would have failed the same way.

The cause is the seam between Celery and asyncio. A Celery task is synchronous, so each
execution calls `asyncio.run`, which creates a **new event loop and closes it at the
end**. The worker, meanwhile, built its `Recursos` once at import time — and a SQLAlchemy
async engine and a redis-py client both hold connections bound to the loop that opened
them. The second task checks a connection out of the pool, finds one created in a loop
that no longer exists, and dies.

The fix is to stop sharing what cannot be shared: **one event loop per task execution,
and one set of resources inside it, disposed before the loop closes.** The cost is a new
connection per task, which at the volume of a notifications queue is nothing next to
sending an email — and the alternative, a pool that has to be reasoned about across loop
boundaries, is the kind of correct-by-luck that produced this bug.

Two shapes are deliberately *not* used here:

- **A single long-lived loop per worker process.** It works, and it makes every task
  share one loop's resources — including a task that leaves a connection in a bad state.
- **`NullPool` on a shared engine.** It solves the database and leaves Redis with the
  same latent problem, which is worse than solving neither: it looks fixed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from cheatsheet.api.dependencies import Recursos
from cheatsheet.platform.settings import Settings

T = TypeVar("T")


def ejecutar_tarea(settings: Settings, trabajo: Callable[[Recursos], Awaitable[T]]) -> T:
    """Run one task body: its own loop, its own resources, closed on the way out.

    `settings` rather than `Recursos` is what a task registration should hold, and that
    is the point of the signature: passing resources built elsewhere is exactly the
    mistake this module exists to prevent.
    """

    async def correr() -> T:
        recursos = Recursos.crear(settings)
        try:
            return await trabajo(recursos)
        finally:
            # Before the loop closes, so the engine's connections are released by the
            # same loop that opened them.
            await recursos.cerrar()

    return asyncio.run(correr())
