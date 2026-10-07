"""La migración 0037: columnas e índice de las entregas de WhatsApp (U7, caso 29).

Solo columnas e índices, **sin backfill** (D1 de la revalidación): una fila de recordatorio sin
`enviado_en` no es una fila «trabada» que haya que arreglar. Son síncronos a propósito, como
`test_migracion_0036.py`: `alembic.command` arranca su propio loop de asyncio. Necesitan
PostgreSQL: se saltean sin base y corren en CI.
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Ana Diaz', 'PANEL', true, :ahora, :ahora)"
)
CREAR_COBRO = text(
    "INSERT INTO cobro (id, empresa_id, cliente_id, monto, descripcion, estado, vence_el, "
    "created_at, updated_at) "
    "VALUES (:id, :empresa_id, :cliente_id, 100.00, 'Cobro', 'PENDIENTE', :ahora, :ahora, :ahora)"
)
CREAR_RECORDATORIO_VIEJO = text(
    "INSERT INTO recordatorio (id, cobro_id, paso, canal) VALUES (:id, :cobro_id, :paso, 'WHATSAPP')"
)
CREAR_RECORDATORIO = text(
    "INSERT INTO recordatorio (id, cobro_id, paso, canal, externo_id) "
    "VALUES (:id, :cobro_id, :paso, 'WHATSAPP', :externo_id)"
)
LEER_RECORDATORIO = text(
    "SELECT enviado_en, estado_entrega, externo_id FROM recordatorio WHERE id = :id"
)
COLUMNAS = text(
    "SELECT count(*) FROM information_schema.columns WHERE "
    "(table_name = 'recordatorio' AND column_name IN ('externo_id', 'ultimo_error')) OR "
    "(table_name = 'mensaje' AND column_name = 'motivo_de_falla')"
)
INDICE = text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_recordatorio_externo_id'")


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _motor() -> AsyncEngine:
    """El rol dueño ve todas las empresas (`BYPASSRLS`, ADR-0005)."""
    return create_async_engine(os.environ["DATABASE_URL_MIGRATIONS"])


async def _ejecutar(sentencia: object, parametros: list[dict[str, object]]) -> None:
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            for fila in parametros:
                await conexion.execute(sentencia, fila)  # type: ignore[call-overload]
    finally:
        await motor.dispose()


async def _leer(
    sentencia: object, parametros: dict[str, object] | None = None
) -> list[tuple[object, ...]]:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            filas = (await conexion.execute(sentencia, parametros or {})).all()  # type: ignore[call-overload]
    finally:
        await motor.dispose()
    return [tuple(fila) for fila in filas]


def _sembrar_cobro() -> uuid.UUID:
    empresa_id, cliente_id, cobro_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    asyncio.run(_ejecutar(CREAR_EMPRESA, [{"id": empresa_id}]))
    asyncio.run(
        _ejecutar(CREAR_CLIENTE, [{"id": cliente_id, "empresa_id": empresa_id, "ahora": AHORA}])
    )
    asyncio.run(
        _ejecutar(
            CREAR_COBRO,
            [{"id": cobro_id, "empresa_id": empresa_id, "cliente_id": cliente_id, "ahora": AHORA}],
        )
    )
    return cobro_id


@pytest.fixture
def esquema_en_0036(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0036` y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0036")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def test_downgrade_deja_las_tablas_sin_las_columnas_ni_el_indice(esquema_en_0036: None) -> None:
    assert asyncio.run(_leer(COLUMNAS)) == [(0,)]
    assert asyncio.run(_leer(INDICE)) == []


def test_sube_sin_backfill_y_la_fila_vieja_queda_igual(esquema_en_0036: None) -> None:
    """Una fila sin `enviado_en` no se toca: reescribirla podría reenviar lo que sí salió."""
    cobro_id = _sembrar_cobro()
    recordatorio_id = uuid.uuid4()
    asyncio.run(
        _ejecutar(
            CREAR_RECORDATORIO_VIEJO, [{"id": recordatorio_id, "cobro_id": cobro_id, "paso": 1}]
        )
    )

    command.upgrade(_config(), "head")

    fila = asyncio.run(_leer(LEER_RECORDATORIO, {"id": recordatorio_id}))
    assert fila == [(None, None, None)]
    assert asyncio.run(_leer(COLUMNAS)) == [(3,)]


def test_el_indice_de_externo_id_es_unico_y_parcial(esquema_migrado: None) -> None:
    definicion = asyncio.run(_leer(INDICE))
    assert len(definicion) == 1
    assert "UNIQUE" in str(definicion[0][0])

    cobro_id = _sembrar_cobro()
    wamid = f"wamid-{uuid.uuid4()}"
    primero, segundo, tercero, cuarto = (uuid.uuid4() for _ in range(4))
    asyncio.run(
        _ejecutar(
            CREAR_RECORDATORIO,
            [
                {"id": primero, "cobro_id": cobro_id, "paso": 1, "externo_id": wamid},
                # Los sin `wamid` no chocan entre sí: el índice es parcial.
                {"id": segundo, "cobro_id": cobro_id, "paso": 2, "externo_id": None},
                {"id": tercero, "cobro_id": cobro_id, "paso": 3, "externo_id": None},
            ],
        )
    )
    with pytest.raises(IntegrityError):
        asyncio.run(
            _ejecutar(
                CREAR_RECORDATORIO,
                [{"id": cuarto, "cobro_id": cobro_id, "paso": 4, "externo_id": wamid}],
            )
        )
