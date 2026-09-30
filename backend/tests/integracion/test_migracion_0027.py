"""La migración 0027 sobre datos viejos: backfill exacto, sube/baja/sube y el informe (ADR-0010).

Se ejerce con filas que existían **antes** de la migración, porque un backfill probado solo sobre
una tabla vacía no prueba nada. El esquema se baja a `0026`, se siembran cobros con el modelo viejo
(un número `monto_reembolsado` y ningún historial), se sube a `0027` y se mira qué recibió cada fila:

| Cobro existente                    | estado nuevo         | fila `reembolso`                      |
| REEMBOLSADO por el total           | REEMBOLSADO          | una, por el monto                     |
| REEMBOLSADO por una parte (parcial)| REEMBOLSADO_PARCIAL  | una, por lo devuelto                  |
| REEMBOLSADO sin monto (anomalía)   | REEMBOLSADO          | ninguna (no se inventa un monto)      |
| APROBADO / PENDIENTE / CANCELADO   | el mismo             | ninguna                               |

Los tests son síncronos a propósito: `alembic.command` arranca su propio loop de asyncio, y un test
`async` lo tendría ya corriendo. Lo que necesita SQL propio lo hace con `asyncio.run`. Necesitan
PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from types import ModuleType
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.integracion.conftest import RAIZ_BACKEND, requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CREADO = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
PAGADO = datetime(2026, 8, 3, 15, 30, tzinfo=UTC)
ACTUALIZADO = datetime(2026, 8, 20, 9, 15, tzinfo=UTC)
VENCE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _config() -> Config:
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    return config


def _la_migracion() -> ModuleType:
    """El módulo de la 0027 por su ruta: un nombre que empieza con dígito no se importa."""
    ruta = RAIZ_BACKEND / "migrations" / "versions" / "0027_reembolsos.py"
    spec = importlib.util.spec_from_file_location("migracion_0027", ruta)
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def esquema_en_0026(esquema_migrado: None) -> Iterator[None]:
    """Baja a `0026` y, pase lo que pase, deja el esquema en `head` para el resto."""
    config = _config()
    command.downgrade(config, "0026")
    try:
        yield
    finally:
        command.upgrade(config, "head")


def _motor() -> AsyncEngine:
    """El rol dueño, que ve todas las empresas (`BYPASSRLS`, ADR-0005) y puede sembrar."""
    return create_async_engine(os.environ["DATABASE_URL_MIGRATIONS"])


CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
)
CREAR_COBRO_VIEJO = text(
    "INSERT INTO cobro (id, empresa_id, cliente_id, monto, descripcion, estado, vence_el, "
    "fecha_pago, mp_payment_id, monto_reembolsado, created_at, updated_at) "
    "VALUES (:id, :empresa_id, :cliente_id, 1000.00, 'Consulta', :estado, :vence, :fecha_pago, "
    ":mp_payment_id, :monto_reembolsado, :creado, :actualizado)"
)


SACAR_REGLA_DE_FECHA = text("ALTER TABLE cobro DROP CONSTRAINT ck_cobro_fecha_de_pago")
#: Como la dejó la 0026: `NOT VALID`, así que una fila que ya la violaba sigue ahí.
PONER_REGLA_DE_FECHA = text(
    "ALTER TABLE cobro ADD CONSTRAINT ck_cobro_fecha_de_pago "
    "CHECK (estado NOT IN ('APROBADO', 'REEMBOLSADO') OR fecha_pago IS NOT NULL) NOT VALID"
)


async def _sembrar(cobros: list[dict[str, Any]], *, violando_la_fecha: bool = False) -> uuid.UUID:
    """Una empresa, un cliente y los cobros dados, con el esquema **viejo** de reembolsos.

    `violando_la_fecha` reproduce lo que la 0026 informa y no corrige: una fila pagada sin fecha
    que ya existía cuando la restricción (`NOT VALID`) se agregó. Con la restricción puesta, no se
    podría sembrar.
    """
    empresa_id, cliente_id = uuid.uuid4(), uuid.uuid4()
    motor = _motor()
    try:
        async with motor.begin() as conexion:
            if violando_la_fecha:
                await conexion.execute(SACAR_REGLA_DE_FECHA)
            await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
            await conexion.execute(
                CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": CREADO}
            )
            for cobro in cobros:
                await conexion.execute(
                    CREAR_COBRO_VIEJO,
                    {
                        "id": uuid.uuid4(),
                        "empresa_id": empresa_id,
                        "cliente_id": cliente_id,
                        "estado": cobro["estado"],
                        "vence": VENCE,
                        "fecha_pago": cobro.get("fecha_pago"),
                        "mp_payment_id": cobro.get("mp_payment_id"),
                        "monto_reembolsado": cobro.get("monto_reembolsado"),
                        "creado": CREADO,
                        "actualizado": ACTUALIZADO,
                    },
                )
            if violando_la_fecha:
                await conexion.execute(PONER_REGLA_DE_FECHA)
    finally:
        await motor.dispose()
    return empresa_id


#: Consultas literales (no interpoladas), ordenadas para que la comparación no dependa del orden
#: físico de las filas.
LEER_COBROS = text(
    "SELECT mp_payment_id, estado, monto_reembolsado FROM cobro "
    "WHERE empresa_id = :empresa_id ORDER BY mp_payment_id NULLS LAST, estado"
)
LEER_FILAS = text(
    "SELECT c.mp_payment_id, r.monto, r.fecha_devolucion, r.origen, r.motivo, r.referencia, "
    "r.registrado_por, r.mp_refund_id, r.corrige_a "
    "FROM reembolso r JOIN cobro c ON c.id = r.cobro_id "
    "WHERE r.empresa_id = :empresa_id ORDER BY r.monto"
)
LEER_VIEJO = text(
    "SELECT mp_payment_id, estado, monto_reembolsado FROM cobro "
    "WHERE empresa_id = :empresa_id ORDER BY mp_payment_id NULLS LAST, estado"
)
CONTAR_TABLA = text("SELECT to_regclass('public.reembolso') IS NOT NULL")


async def _leer(consulta: TextClause, empresa_id: uuid.UUID) -> list[dict[str, Any]]:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            filas = (await conexion.execute(consulta, {"empresa_id": empresa_id})).mappings().all()
    finally:
        await motor.dispose()
    return [dict(fila) for fila in filas]


TOTAL: dict[str, Any] = {
    "estado": "REEMBOLSADO",
    "fecha_pago": PAGADO,
    "mp_payment_id": "pago-total",
    "monto_reembolsado": Decimal("1000.00"),
}
PARCIAL: dict[str, Any] = {
    "estado": "REEMBOLSADO",
    "fecha_pago": PAGADO,
    "mp_payment_id": "pago-parcial",
    "monto_reembolsado": Decimal("400.00"),
}
ANOMALO: dict[str, Any] = {
    "estado": "REEMBOLSADO",
    "fecha_pago": PAGADO,
    "mp_payment_id": "pago-anomalo",
}
SIN_REEMBOLSO: list[dict[str, Any]] = [
    {"estado": "APROBADO", "fecha_pago": PAGADO, "mp_payment_id": "pago-aprobado"},
    {"estado": "PENDIENTE"},
    {"estado": "CANCELADO"},
]


def test_cada_reembolsado_viejo_gana_su_fila_y_los_parciales_se_re_derivan(
    esquema_en_0026: None,
) -> None:
    empresa_id = asyncio.run(_sembrar([TOTAL, PARCIAL, ANOMALO, *SIN_REEMBOLSO]))

    command.upgrade(_config(), "0027")

    filas = asyncio.run(_leer(LEER_FILAS, empresa_id))
    assert [(f["mp_payment_id"], f["monto"]) for f in filas] == [
        ("pago-parcial", Decimal("400.00")),
        ("pago-total", Decimal("1000.00")),
    ]
    for fila in filas:
        assert fila["origen"] == "API_MERCADOPAGO"
        # La única fecha que había; el motivo dice que es aproximada.
        assert fila["fecha_devolucion"] == ACTUALIZADO
        assert fila["motivo"] == "Registrado antes de ADR-0010; fecha aproximada"
        assert fila["registrado_por"] is None
        assert fila["referencia"] is None
        assert fila["mp_refund_id"] is None
        assert fila["corrige_a"] is None

    cobros = {c["mp_payment_id"]: c for c in asyncio.run(_leer(LEER_COBROS, empresa_id))}
    assert cobros["pago-total"]["estado"] == "REEMBOLSADO"
    assert cobros["pago-parcial"]["estado"] == "REEMBOLSADO_PARCIAL"
    assert cobros["pago-parcial"]["monto_reembolsado"] == Decimal("400.00")
    # No se le inventa un monto: sigue `REEMBOLSADO` con acumulado cero, y se informa.
    assert cobros["pago-anomalo"]["estado"] == "REEMBOLSADO"
    assert cobros["pago-anomalo"]["monto_reembolsado"] == Decimal("0.00")
    assert cobros["pago-aprobado"]["monto_reembolsado"] == Decimal("0.00")
    assert cobros["pago-aprobado"]["estado"] == "APROBADO"


def test_el_acumulado_deja_de_ser_nulo_para_todo_cobro_existente(esquema_en_0026: None) -> None:
    empresa_id = asyncio.run(_sembrar(SIN_REEMBOLSO))

    command.upgrade(_config(), "0027")

    cobros = asyncio.run(_leer(LEER_COBROS, empresa_id))
    assert len(cobros) == len(SIN_REEMBOLSO)
    assert all(c["monto_reembolsado"] == Decimal("0.00") for c in cobros)


def test_la_migracion_sube_baja_y_vuelve_a_subir_sin_perder_lo_devuelto(
    esquema_en_0026: None,
) -> None:
    empresa_id = asyncio.run(_sembrar([TOTAL, PARCIAL, ANOMALO, *SIN_REEMBOLSO]))
    config = _config()

    command.upgrade(config, "0027")
    command.downgrade(config, "0026")

    # Al bajar: la tabla desaparece, el parcial vuelve a figurar `REEMBOLSADO` (el comportamiento
    # viejo) y el acumulado en cero vuelve a ser `NULL`.
    viejos = {c["mp_payment_id"]: c for c in asyncio.run(_leer(LEER_VIEJO, empresa_id))}
    assert asyncio.run(_existe_la_tabla()) is False
    assert viejos["pago-parcial"]["estado"] == "REEMBOLSADO"
    assert viejos["pago-parcial"]["monto_reembolsado"] == Decimal("400.00")
    assert viejos["pago-total"]["monto_reembolsado"] == Decimal("1000.00")
    assert viejos["pago-aprobado"]["monto_reembolsado"] is None
    assert viejos["pago-anomalo"]["monto_reembolsado"] is None

    command.upgrade(config, "0027")

    filas = asyncio.run(_leer(LEER_FILAS, empresa_id))
    assert len(filas) == 2
    cobros = {c["mp_payment_id"]: c for c in asyncio.run(_leer(LEER_COBROS, empresa_id))}
    assert cobros["pago-parcial"]["estado"] == "REEMBOLSADO_PARCIAL"


async def _existe_la_tabla() -> bool:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            return bool((await conexion.execute(CONTAR_TABLA)).scalar_one())
    finally:
        await motor.dispose()


def test_un_reembolsado_sin_monto_se_informa_y_la_restriccion_queda_sin_validar(
    esquema_en_0026: None,
) -> None:
    """No se inventa un monto: la migración no falla, informa la empresa y deja `NOT VALID`."""
    empresa_id = asyncio.run(_sembrar([ANOMALO]))

    command.upgrade(_config(), "0027")

    assert asyncio.run(_restriccion_validada("ck_cobro_estado_de_reembolso")) is False
    avisos = asyncio.run(_correr_el_informe())
    assert any(str(empresa_id) in aviso and "1 cobro(s)" in aviso for aviso in avisos), avisos


def test_sin_anomalias_la_restriccion_de_estado_queda_validada(esquema_en_0026: None) -> None:
    """Cuando el informe da cero, `NOT VALID` deja de hacer falta y la migración la valida."""
    asyncio.run(_sembrar([TOTAL, PARCIAL, *SIN_REEMBOLSO]))

    command.upgrade(_config(), "0027")

    assert asyncio.run(_restriccion_validada("ck_cobro_estado_de_reembolso")) is True
    assert asyncio.run(_restriccion_validada("ck_cobro_reembolso_en_vuelo")) is True
    # La de la fecha sí queda `NOT VALID`, como dice el plan: se recrea con el estado nuevo.
    assert asyncio.run(_restriccion_validada("ck_cobro_fecha_de_pago")) is False


def test_un_cobro_pagado_sin_fecha_no_hace_fallar_la_migracion(esquema_en_0026: None) -> None:
    """La anomalía que la 0026 informa y no corrige: una restricción `NOT VALID` se evalúa en cada
    `UPDATE`, así que la 0027 saca `ck_cobro_fecha_de_pago` antes de completar el acumulado."""
    empresa_id = asyncio.run(
        _sembrar(
            [{"estado": "APROBADO", "mp_payment_id": "pago-sin-fecha"}], violando_la_fecha=True
        )
    )

    command.upgrade(_config(), "0027")

    cobros = asyncio.run(_leer(LEER_COBROS, empresa_id))
    assert [(c["estado"], c["monto_reembolsado"]) for c in cobros] == [
        ("APROBADO", Decimal("0.00"))
    ]


async def _restriccion_validada(nombre: str) -> bool:
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            return bool(
                (
                    await conexion.execute(
                        text("SELECT convalidated FROM pg_constraint WHERE conname = :nombre"),
                        {"nombre": nombre},
                    )
                ).scalar_one()
            )
    finally:
        await motor.dispose()


async def _correr_el_informe() -> list[str]:
    """Los `NOTICE` que emite el informe de la migración, capturados de la conexión."""
    avisos: list[str] = []
    motor = _motor()
    try:
        async with motor.connect() as conexion:
            crudo = await conexion.get_raw_connection()
            # El log del servidor llega al driver, no a SQLAlchemy: se escucha en el driver.
            driver = crudo.driver_connection
            assert driver is not None
            driver._connection.add_log_listener(lambda _con, mensaje: avisos.append(str(mensaje)))
            await conexion.execute(text(_la_migracion().INFORME_Y_VALIDACION))
    finally:
        await motor.dispose()
    return avisos
