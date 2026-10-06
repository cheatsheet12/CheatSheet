"""El savepoint por cobro del barrido de recordatorios (U5, H1), sobre SQLAlchemy.

`async with sesion.begin_nested()` es un `SAVEPOINT`: si algo adentro falla, la base vuelve al
punto donde empezó el bloque y **el resto de la transacción sigue viva**. Es el mismo patrón que
`observability/infrastructure/repository.py` y `master_data/infrastructure/correccion.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.payments.application.errors import DespachoNoPersistido


class AislamientoConSavepoint:
    """`PortAislamiento`: un savepoint por bloque."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    @asynccontextmanager
    async def aislar(self) -> AsyncIterator[None]:
        try:
            async with self._sesion.begin_nested():
                yield
        except SQLAlchemyError as exc:
            # El savepoint ya se deshizo al salir del `async with` de arriba. No se copia el
            # texto de la excepción: puede traer los valores de la fila.
            raise DespachoNoPersistido(
                f"La base rechazó el despacho ({type(exc).__name__})"
            ) from exc


__all__ = ["AislamientoConSavepoint"]
