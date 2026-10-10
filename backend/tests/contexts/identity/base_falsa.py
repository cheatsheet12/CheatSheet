"""A stand-in for the database, just deep enough for the per-request session check.

`sesion_de_empresa` and `ConsultaDeUsuarioVigentePostgres` only ever call `execute`,
`commit` and `rollback` on a session, and `async with` on the factory's product, so that is
all this implements. Each step can be made slow independently (taking the connection is the
`set_config`, the user query is the `SELECT`), which is what the two time limits are about.

It is a fake of the *session*, not of SQL: nothing here says anything about Row-Level
Security. That is proved against a real PostgreSQL in
`tests/integracion/test_consulta_de_sesion_postgres.py`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass
class EscenarioDeBase:
    """What the fake database does, and what it saw."""

    fila: Any
    demora_de_conexion: float = 0.0
    demora_de_consulta: float = 0.0
    abiertas: int = 0
    cerradas: int = 0
    confirmaciones: int = 0
    reversiones: int = 0
    empresas_anunciadas: list[str] = field(default_factory=list)
    #: Raised when the connection is taken, the way a driver does at connect time.
    error_de_conexion: BaseException | None = None


class _Resultado:
    def __init__(self, fila: Any) -> None:
        self._fila = fila

    def one_or_none(self) -> Any:
        return self._fila


class SesionFalsa:
    """Just enough of `AsyncSession` for `sesion_de_empresa` and the query adapter."""

    def __init__(self, escenario: EscenarioDeBase) -> None:
        self._e = escenario

    async def __aenter__(self) -> SesionFalsa:
        self._e.abiertas += 1
        return self

    async def __aexit__(self, *_: object) -> None:
        self._e.abiertas -= 1
        self._e.cerradas += 1

    async def execute(self, sentencia: Any, parametros: dict[str, str] | None = None) -> _Resultado:
        if "set_config" in str(sentencia):
            # Taking the connection: the step the engine's own 10 s limit protects.
            assert parametros is not None
            self._e.empresas_anunciadas.append(parametros["valor"])
            await asyncio.sleep(self._e.demora_de_conexion)
            if self._e.error_de_conexion is not None:
                raise self._e.error_de_conexion
            return _Resultado(None)
        await asyncio.sleep(self._e.demora_de_consulta)
        return _Resultado(self._e.fila)

    async def commit(self) -> None:
        self._e.confirmaciones += 1

    async def rollback(self) -> None:
        self._e.reversiones += 1


def fabrica_de_sesiones(escenario: EscenarioDeBase) -> async_sessionmaker[AsyncSession]:
    """The object `Recursos.sesiones` would be, typed as the real thing for the call sites."""

    def fabrica() -> SesionFalsa:
        return SesionFalsa(escenario)

    return cast("async_sessionmaker[AsyncSession]", fabrica)


def fila(
    empresa_id: EmpresaId,
    *,
    rol: str = "OPERADOR",
    estado: str = "ACTIVO",
    terminos_version: str | None = "1.0",
    acepto_privacidad_vigente: bool = True,
) -> Any:
    """The columns the check selects."""
    return SimpleNamespace(
        empresa_id=empresa_id,
        rol=rol,
        estado=estado,
        terminos_version=terminos_version,
        acepto_privacidad_vigente=acepto_privacidad_vigente,
    )
