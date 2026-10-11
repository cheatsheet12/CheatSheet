"""Adaptadores SQLAlchemy del envío en tres tiempos, compartidos por `payments` y `scheduling`.

Viven en `platform/` (dueño de la sesión de base de datos) y no en un contexto: ninguno los
duplica y R3/R4 se cumplen. Implementan los `Protocol` de `shared/transaccion.py`.

**`ConfirmacionDeLaUnidad`** (U7, D-U7-3, H1): `PortTransaccion` sobre la sesión de la unidad de trabajo.
`sesion_de_empresa` declara la empresa con `set_config(..., true)` (el `SET LOCAL`), que **muere con el commit**: sin volver a declararla, la
primera consulta después de confirmar correría sin empresa y RLS no mostraría nada (o rechazaría
la escritura). Por eso el commit y la nueva declaración van juntos, en este único lugar.

`expire_on_commit=False` (`platform/database.py`): los objetos ya leídos siguen usables.

**`AislamientoConSavepoint`** (U5, H1): `async with sesion.begin_nested()` es un `SAVEPOINT`: si algo
adentro falla, la base vuelve al punto donde empezó el bloque y el resto de la transacción sigue
viva. Mismo patrón que `observability/infrastructure/repository.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.platform.database import GUC_EMPRESA
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.transaccion import DespachoNoPersistido


class ConfirmacionDeLaUnidad:
    """`PortTransaccion`: commit y nueva transacción ya declarada para la misma empresa."""

    def __init__(self, sesion: AsyncSession, empresa_id: EmpresaId) -> None:
        self._sesion = sesion
        self._empresa_id = empresa_id

    async def confirmar(self) -> None:
        try:
            await self._sesion.commit()
        except SQLAlchemyError as exc:
            # El commit falló: lo no confirmado no existe. Se deja la sesión usable para el
            # recordatorio siguiente. Sin el texto de la excepción: puede traer valores de la fila.
            await self._volver_a_empezar()
            raise DespachoNoPersistido(
                f"La base rechazó la confirmación ({type(exc).__name__})"
            ) from exc
        await self._declarar_empresa()

    async def _volver_a_empezar(self) -> None:
        try:
            await self._sesion.rollback()
            await self._declarar_empresa()
        except SQLAlchemyError:
            # La conexión no volvió: el próximo recordatorio fallará solo y se registrará solo.
            return

    async def _declarar_empresa(self) -> None:
        await self._sesion.execute(
            text("SELECT set_config(:clave, :valor, true)"),
            {"clave": GUC_EMPRESA, "valor": str(self._empresa_id)},
        )


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


__all__ = ["AislamientoConSavepoint", "ConfirmacionDeLaUnidad"]
