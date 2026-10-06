"""La migración 0033: `faq.usos` pasa a línea de base y nace `faq_uso` (ADR-0012, caso 20).

Sube y baja sin perder el total: `downgrade` pliega los eventos en `usos` antes de borrar la
tabla. Son síncronos a propósito, como `test_migracion_0032.py`: `alembic.command` arranca su
propio loop de asyncio. Necesitan PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

AHORA = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_FAQ_VIEJA = text(
    "INSERT INTO faq (id, empresa_id, pregunta, respuesta, embedding_obsoleto, usos, "
    "created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'p', 'r', true, 47, :ahora, :ahora)"
)
LEER_FAQ_NUEVA = text(
    "SELECT usos_anteriores, editada_en, seguimiento_desde FROM faq WHERE id = :id"
)
LEER_FAQ_VIEJA = text("SELECT usos FROM faq WHERE id = :id")
TABLA = text("SELECT to_regclass('faq_uso') IS NOT NULL")
CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Ana Diaz', 'AGENTE', true, :ahora, :ahora)"
)
CONVERSACION = text(
    "INSERT INTO conversacion (id, empresa_id, cliente_id, estado, contador, ventana_maximo, "
    "created_at) VALUES (:id, :empresa_id, :cliente_id, 'ACTIVA', 0, 3, :ahora)"
)
MENSAJE = text(
    "INSERT INTO mensaje (id, conversacion_id, empresa_id, direccion, tipo_contenido, contenido, "
    "momento) VALUES (:id, :conversacion_id, :empresa_id, 'SALIENTE', 'TEXTO', 'x', :ahora)"
)
USO = text(
    "INSERT INTO faq_uso (id, empresa_id, faq_id, mensaje_id, usado_en) "
    "VALUES (:id, :empresa_id, :faq_id, :mensaje_id, :ahora)"
)


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _motor() -> AsyncEngine:
    """El rol dueño: ve todas las empresas (`BYPASSRLS`, ADR-0005) y puede sembrar."""
    return create_async_engine(os.environ["DATABASE_URL_MIGRATIONS"])


async def _sembrar_faq_vieja() -> tuple[uuid.UUID, uuid.UUID]:
    empresa_id, faq_id = uuid.uuid4(), uuid.uuid4()
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
            await conexion.execute(
                CREAR_FAQ_VIEJA, {"id": faq_id, "empresa_id": empresa_id, "ahora": AHORA}
            )
    finally:
        await motor.dispose()
    return empresa_id, faq_id


async def _sembrar_tres_usos(empresa_id: uuid.UUID, faq_id: uuid.UUID) -> None:
    cliente_id, conversacion_id = uuid.uuid4(), uuid.uuid4()
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            await conexion.execute(
                CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}
            )
            await conexion.execute(
                CONVERSACION,
                {
                    "id": conversacion_id,
                    "empresa_id": empresa_id,
                    "cliente_id": cliente_id,
                    "ahora": AHORA,
                },
            )
            for _ in range(3):
                mensaje_id = uuid.uuid4()
                await conexion.execute(
                    MENSAJE,
                    {
                        "id": mensaje_id,
                        "conversacion_id": conversacion_id,
                        "empresa_id": empresa_id,
                        "ahora": AHORA,
                    },
                )
                await conexion.execute(
                    USO,
                    {
                        "id": uuid.uuid4(),
                        "empresa_id": empresa_id,
                        "faq_id": faq_id,
                        "mensaje_id": mensaje_id,
                        "ahora": AHORA,
                    },
                )
    finally:
        await motor.dispose()


async def _leer(
    sentencia: object, parametros: dict[str, object] | None = None
) -> tuple[object, ...]:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            fila = (await conexion.execute(sentencia, parametros or {})).one()  # type: ignore[call-overload]
    finally:
        await motor.dispose()
    return tuple(fila)


@pytest.fixture
def esquema_en_0032(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0032` y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0032")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def test_downgrade_deja_la_columna_vieja_y_sin_la_tabla(esquema_en_0032: None) -> None:
    assert asyncio.run(_leer(TABLA)) == (False,)


def test_upgrade_conserva_el_contador_como_linea_de_base(esquema_en_0032: None) -> None:
    """Caso 20: `faq.usos = 47` → `usos_anteriores = 47`, sin `editada_en` y con seguimiento."""
    _, faq_id = asyncio.run(_sembrar_faq_vieja())

    command.upgrade(_config(), "head")

    usos, editada_en, seguimiento = asyncio.run(_leer(LEER_FAQ_NUEVA, {"id": faq_id}))
    assert (usos, editada_en) == (47, None)
    assert seguimiento is not None


def test_downgrade_pliega_los_eventos_en_el_contador_viejo(esquema_en_0032: None) -> None:
    """Caso 20: 47 de base y 3 eventos → `usos = 50`, y subir otra vez queda limpio."""
    empresa_id, faq_id = asyncio.run(_sembrar_faq_vieja())
    command.upgrade(_config(), "head")
    asyncio.run(_sembrar_tres_usos(empresa_id, faq_id))

    command.downgrade(_config(), "0032")

    assert asyncio.run(_leer(LEER_FAQ_VIEJA, {"id": faq_id})) == (50,)
    command.upgrade(_config(), "head")
    assert asyncio.run(_leer(TABLA)) == (True,)
    assert asyncio.run(_leer(LEER_FAQ_NUEVA, {"id": faq_id}))[0] == 50
