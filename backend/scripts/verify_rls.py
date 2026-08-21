#!/usr/bin/env python3
"""Prove, against a real database, that one company cannot read another's rows.

Row-Level Security is the barrier that holds when the application code is wrong
(`platform/database.py`, ADR-002). It only works if the application connects as a role
that is **not** the owner of the tables and does **not** hold `BYPASSRLS` — and that is
a property of how the database was *provisioned*, not of anything in this repository.

On a managed provider it is easy to get silently wrong. On Neon, every role created
from the console, the API or the CLI is granted membership in `neon_superuser`, and
`neon_superuser` carries `BYPASSRLS`. A `cheatsheet_app` created that way inherits it:
every `aislamiento_por_empresa` policy stops firing, nothing looks broken, the local
test suite stays green against its own container, and the deployment serves one
company's data to another.

So this script does not read a checklist — it interrogates the live database as both
roles and, in the last check, actually tries to read across the tenant boundary.

    DATABASE_URL=... DATABASE_URL_MIGRATIONS=... python backend/scripts/verify_rls.py

Exit code 0 means every check passed. Anything else means the database must not be
used. Both URLs are read in the same SQLAlchemy form the application uses, on purpose:
a connection string that the application would reject fails here first.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cheatsheet.platform.database import argumentos_de_conexion
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

ROL_APP = "cheatsheet_app"
TABLA_AUDITORIA = "registro_de_auditoria"
EXTENSIONES_REQUERIDAS = ("vector", "btree_gist")
VERSIONES = Path(__file__).resolve().parents[1] / "migrations" / "versions"

_log = logging.getLogger("verify_rls")


def _motor(url: str) -> AsyncEngine:
    """One engine per run, no pool, and exactly the TLS the application would use."""
    return create_async_engine(url, poolclass=NullPool, connect_args=argumentos_de_conexion(url))


@dataclass(frozen=True, slots=True)
class Chequeo:
    """One verdict. `detalle` is written to be read by whoever has to fix it."""

    numero: int
    nombre: str
    ok: bool
    detalle: str


# --------------------------------------------------------------------------
# Queries. Every one of them is a literal with bound parameters: identifiers
# cannot be parameterised, and building these with f-strings would read to a
# scanner exactly like the injection it is not.
# --------------------------------------------------------------------------

SQL_ATRIBUTOS = text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :rol")

# Catches the attribute held directly *and* the one inherited through any group,
# which is how neon_superuser hands it over. Deliberately not written against
# 'neon_superuser' by name: the same mistake on another provider has another name.
SQL_ROLES_QUE_EVADEN = text(
    """
    SELECT r.rolname
      FROM pg_roles r
     WHERE r.rolbypassrls
       AND pg_has_role(:rol, r.oid, 'USAGE')
     ORDER BY r.rolname
    """
)

SQL_TABLAS_PROPIAS = text(
    """
    SELECT c.relname
      FROM pg_class c
      JOIN pg_roles r ON r.oid = c.relowner
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'r' AND r.rolname = :rol
     ORDER BY c.relname
    """
)

# `empresa_id` is the multi-tenant column of the whole system (CLAUDE.md §2.2), so
# "every table that has it" is the same set as "every table that must isolate".
# Discovering it from the catalogue means a table added in a future epic is covered
# the day it is created, without anyone remembering to edit this file.
SQL_TABLAS_CON_EMPRESA = text(
    """
    SELECT c.relname,
           c.relrowsecurity,
           c.relforcerowsecurity,
           (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS politicas
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind = 'r'
       AND EXISTS (SELECT 1
                     FROM pg_attribute a
                    WHERE a.attrelid = c.oid
                      AND a.attname = 'empresa_id'
                      AND NOT a.attisdropped)
     ORDER BY c.relname
    """
)

SQL_PRIVILEGIOS = text(
    """
    SELECT has_table_privilege(:rol, :tabla, 'SELECT') AS lectura,
           has_table_privilege(:rol, :tabla, 'INSERT') AS alta,
           has_table_privilege(:rol, :tabla, 'UPDATE') AS modificacion,
           has_table_privilege(:rol, :tabla, 'DELETE') AS borrado
    """
)

SQL_EXTENSIONES = text("SELECT extname FROM pg_extension")
SQL_VERSION_APLICADA = text("SELECT version_num FROM alembic_version")

SQL_DECLARAR_EMPRESA = text("SELECT set_config('app.current_empresa', :empresa, true)")

SQL_SEMBRAR = text(
    """
    INSERT INTO registro_de_auditoria
        (id, evento_id, empresa_id, usuario_id, modulo, accion,
         entidad_afectada, resultado, direccion_ip, "timestamp")
    VALUES (:id, :evento_id, :empresa, NULL, 'observability',
            'verificacion_de_aislamiento', 'backend/scripts/verify_rls.py',
            'completado', NULL, :momento)
    """
)

SQL_CONTAR_SONDA = text(
    "SELECT count(*) FROM registro_de_auditoria WHERE evento_id IN (:evento_a, :evento_b)"
)

SQL_LIMPIAR = text("DELETE FROM registro_de_auditoria WHERE evento_id = :evento_id")


# --------------------------------------------------------------------------
# Checks 1-7: what the catalogue says.
# --------------------------------------------------------------------------


async def _check_atributos(conexion: AsyncConnection) -> Chequeo:
    nombre = f"{ROL_APP} no es superusuario ni evade RLS"
    fila = (await conexion.execute(SQL_ATRIBUTOS, {"rol": ROL_APP})).first()
    if fila is None:
        return Chequeo(1, nombre, False, f"el rol {ROL_APP} no existe en este cluster")
    es_super, evade = bool(fila[0]), bool(fila[1])
    if es_super or evade:
        culpables = ", ".join(
            etiqueta
            for etiqueta, activo in (("SUPERUSER", es_super), ("BYPASSRLS", evade))
            if activo
        )
        return Chequeo(1, nombre, False, f"tiene {culpables}: las politicas no se aplican")
    return Chequeo(1, nombre, True, "sin SUPERUSER ni BYPASSRLS")


async def _check_herencia(conexion: AsyncConnection) -> Chequeo:
    nombre = f"{ROL_APP} no hereda BYPASSRLS de ningun grupo"
    filas = (await conexion.execute(SQL_ROLES_QUE_EVADEN, {"rol": ROL_APP})).scalars().all()
    if filas:
        heredados = ", ".join(str(r) for r in filas)
        return Chequeo(
            2,
            nombre,
            False,
            f"lo hereda de: {heredados}. Si dice neon_superuser, el rol se creo desde "
            f"la consola de Neon en lugar de por SQL",
        )
    return Chequeo(2, nombre, True, "no pertenece a ningun rol con BYPASSRLS")


async def _check_propiedad(conexion: AsyncConnection) -> Chequeo:
    nombre = f"{ROL_APP} no es dueno de ninguna tabla"
    filas = (await conexion.execute(SQL_TABLAS_PROPIAS, {"rol": ROL_APP})).scalars().all()
    if filas:
        propias = ", ".join(str(t) for t in filas)
        return Chequeo(3, nombre, False, f"es dueno de: {propias}. El dueno esta exento de FORCE")
    return Chequeo(3, nombre, True, "no posee ninguna tabla de public")


async def _check_politicas(conexion: AsyncConnection) -> Chequeo:
    nombre = "toda tabla con empresa_id tiene RLS, FORCE y politica"
    filas = (await conexion.execute(SQL_TABLAS_CON_EMPRESA)).all()
    if not filas:
        return Chequeo(4, nombre, False, "ninguna tabla tiene empresa_id: la base esta vacia")
    rotas = [
        f"{fila[0]} (rls={bool(fila[1])}, force={bool(fila[2])}, politicas={int(fila[3])})"
        for fila in filas
        if not (bool(fila[1]) and bool(fila[2]) and int(fila[3]) > 0)
    ]
    if rotas:
        return Chequeo(4, nombre, False, "sin aislamiento completo: " + ", ".join(rotas))
    return Chequeo(4, nombre, True, f"{len(filas)} tabla(s) con RLS forzado y politica")


async def _check_bitacora_inmutable(conexion: AsyncConnection) -> Chequeo:
    nombre = f"{TABLA_AUDITORIA} es append-only para {ROL_APP}"
    parametros = {"rol": ROL_APP, "tabla": TABLA_AUDITORIA}
    fila = (await conexion.execute(SQL_PRIVILEGIOS, parametros)).first()
    if fila is None:
        return Chequeo(5, nombre, False, "no se pudieron leer los privilegios")
    lectura, alta, modificacion, borrado = (bool(fila[i]) for i in range(4))
    if not (lectura and alta):
        return Chequeo(5, nombre, False, "le faltan SELECT o INSERT: la app no puede auditar")
    if modificacion or borrado:
        sobrantes = ", ".join(e for e, a in (("UPDATE", modificacion), ("DELETE", borrado)) if a)
        return Chequeo(5, nombre, False, f"tiene {sobrantes}: HS-T5 RN-03 pide inmutabilidad")
    return Chequeo(5, nombre, True, "SELECT e INSERT, sin UPDATE ni DELETE")


async def _check_extensiones(conexion: AsyncConnection) -> Chequeo:
    nombre = "extensiones vector y btree_gist instaladas"
    instaladas = {str(e) for e in (await conexion.execute(SQL_EXTENSIONES)).scalars().all()}
    faltantes = [e for e in EXTENSIONES_REQUERIDAS if e not in instaladas]
    if faltantes:
        return Chequeo(
            6,
            nombre,
            False,
            f"faltan: {', '.join(faltantes)}. Instalarlas requiere privilegios que la "
            f"aplicacion no tendra despues",
        )
    return Chequeo(6, nombre, True, ", ".join(EXTENSIONES_REQUERIDAS))


def _revision_esperada() -> str | None:
    """The head of the local migration history: the revision nobody points back to."""
    revisiones: set[str] = set()
    anteriores: set[str] = set()
    for archivo in sorted(VERSIONES.glob("*.py")):
        texto = archivo.read_text(encoding="utf-8")
        actual = re.search(r'^revision: str = "([^"]+)"', texto, re.MULTILINE)
        if actual is None:
            continue
        revisiones.add(actual.group(1))
        previa = re.search(r'^down_revision: str \| None = "([^"]+)"', texto, re.MULTILINE)
        if previa is not None:
            anteriores.add(previa.group(1))
    cabezas = revisiones - anteriores
    return cabezas.pop() if len(cabezas) == 1 else None


async def _check_migraciones(conexion: AsyncConnection) -> Chequeo:
    nombre = "la base esta en la ultima migracion"
    esperada = _revision_esperada()
    if esperada is None:
        return Chequeo(7, nombre, False, f"no pude deducir una unica cabeza en {VERSIONES}")
    aplicada = (await conexion.execute(SQL_VERSION_APLICADA)).scalar_one_or_none()
    if aplicada is None:
        return Chequeo(7, nombre, False, "alembic_version esta vacia: falta correr las migraciones")
    if str(aplicada) != esperada:
        return Chequeo(
            7, nombre, False, f"la base esta en {aplicada} y el codigo espera {esperada}"
        )
    return Chequeo(7, nombre, True, f"revision {esperada}")


# --------------------------------------------------------------------------
# Check 8: what the database actually does.
# --------------------------------------------------------------------------


async def _sembrar(motor: AsyncEngine, empresa: uuid.UUID, evento: uuid.UUID) -> None:
    """Write one probe row as the owner.

    The company is announced even here: `FORCE ROW LEVEL SECURITY` subjects the owner
    to the policy too, and relying on the owner happening to hold BYPASSRLS would make
    this script depend on the very thing it is checking.
    """
    async with motor.begin() as conexion:
        await conexion.execute(SQL_DECLARAR_EMPRESA, {"empresa": str(empresa)})
        await conexion.execute(
            SQL_SEMBRAR,
            {
                "id": uuid.uuid4(),
                "evento_id": evento,
                "empresa": empresa,
                "momento": datetime.now(UTC),
            },
        )


async def _limpiar(motor: AsyncEngine, empresa: uuid.UUID, evento: uuid.UUID) -> None:
    """Remove a probe row. The owner does it because the application holds no DELETE."""
    async with motor.begin() as conexion:
        await conexion.execute(SQL_DECLARAR_EMPRESA, {"empresa": str(empresa)})
        await conexion.execute(SQL_LIMPIAR, {"evento_id": evento})


async def _contar_como_app(
    motor: AsyncEngine,
    empresa: uuid.UUID | None,
    eventos: tuple[uuid.UUID, uuid.UUID],
) -> int:
    """Count the two probe rows visible to the application role, in one transaction."""
    async with motor.connect() as conexion:
        if empresa is not None:
            await conexion.execute(SQL_DECLARAR_EMPRESA, {"empresa": str(empresa)})
        visibles = await conexion.execute(
            SQL_CONTAR_SONDA, {"evento_a": eventos[0], "evento_b": eventos[1]}
        )
        return int(visibles.scalar_one())


async def _check_sonda(motor_dueno: AsyncEngine, motor_app: AsyncEngine) -> Chequeo:
    nombre = "una empresa no ve las filas de otra (sonda viva)"
    empresa_a, empresa_b = uuid.uuid4(), uuid.uuid4()
    eventos = (uuid.uuid4(), uuid.uuid4())
    try:
        await _sembrar(motor_dueno, empresa_a, eventos[0])
        await _sembrar(motor_dueno, empresa_b, eventos[1])
        con_empresa = await _contar_como_app(motor_app, empresa_a, eventos)
        sin_empresa = await _contar_como_app(motor_app, None, eventos)
    except SQLAlchemyError as error:
        return Chequeo(8, nombre, False, f"la sonda no pudo completarse: {error}")
    finally:
        await _limpiar(motor_dueno, empresa_a, eventos[0])
        await _limpiar(motor_dueno, empresa_b, eventos[1])

    if con_empresa != 1:
        detalle = (
            f"declarando una sola empresa vio {con_empresa} de 2 filas; "
            f"deberia ver exactamente la suya"
        )
        return Chequeo(8, nombre, False, detalle)
    if sin_empresa != 0:
        return Chequeo(8, nombre, False, f"sin empresa declarada vio {sin_empresa} filas")
    return Chequeo(8, nombre, True, "vio 1 de 2 con empresa declarada, y 0 sin declararla")


# --------------------------------------------------------------------------
# Orchestration.
# --------------------------------------------------------------------------


def _variable(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        _log.error(
            "Falta la variable de entorno %s. Ver docs/staging-database.md para el "
            "formato exacto de la URL.",
            nombre,
        )
        raise SystemExit(2)
    return valor


def _informar(chequeos: Sequence[Chequeo]) -> int:
    for chequeo in chequeos:
        marca = " OK " if chequeo.ok else "FALLA"
        _log.info("[%s] %d. %s — %s", marca, chequeo.numero, chequeo.nombre, chequeo.detalle)
    fallidos = [c for c in chequeos if not c.ok]
    if fallidos:
        _log.error(
            "%d de %d comprobaciones fallaron. Esta base NO debe usarse hasta corregirlas.",
            len(fallidos),
            len(chequeos),
        )
        return 1
    _log.info("Las %d comprobaciones pasaron.", len(chequeos))
    return 0


async def _ejecutar() -> int:
    motor_app = _motor(_variable("DATABASE_URL"))
    motor_dueno = _motor(_variable("DATABASE_URL_MIGRATIONS"))
    try:
        async with motor_dueno.connect() as conexion:
            # Read as the owner: the application role holds no grant on alembic_version,
            # and a permission error there would look like a missing migration.
            chequeos = [
                await _check_atributos(conexion),
                await _check_herencia(conexion),
                await _check_propiedad(conexion),
                await _check_politicas(conexion),
                await _check_bitacora_inmutable(conexion),
                await _check_extensiones(conexion),
                await _check_migraciones(conexion),
            ]
        chequeos.append(await _check_sonda(motor_dueno, motor_app))
    finally:
        await motor_app.dispose()
        await motor_dueno.dispose()
    return _informar(chequeos)


def main() -> int:
    # stdout, not stderr: PowerShell renders anything a native command writes to stderr
    # as a NativeCommandError, in red, so a successful run would read as a failure on
    # the platform this team uses. The report is this tool's output, not a diagnostic
    # aside, and the exit code is what carries pass or fail.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    try:
        return asyncio.run(_ejecutar())
    except SQLAlchemyError as error:
        _log.error("No se pudo verificar la base: %s", error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
