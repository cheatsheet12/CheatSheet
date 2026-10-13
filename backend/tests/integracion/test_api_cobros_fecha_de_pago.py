"""`GET /cobros/{id}` devuelve cuándo, cómo y con qué operación se pagó (D91, ADR-0010).

La costura que el test unitario no mira: que el agregado, el repositorio y el esquema de salida
hablen el mismo idioma. En particular, que el campo HTTP se llame `fecha_pago` (antes
`pagado_en`) y que un cobro pagado por link deje `numero_de_operacion` en `null`.

La ruta de lectura no consulta el rol (HU-E6-02 RN-04: todos leen), así que un administrador
alcanza para ejercerla; lo que se prueba es la forma de la respuesta, no el permiso.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.platform.settings import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import CONSENTIMIENTO

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CONTRASENA = "una-contrasena-larga"
CREADO = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
PAGADO = datetime(2026, 8, 3, 15, 30, tzinfo=UTC)
VENCE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, cuit, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', '20222222223', 'PANEL', true, :ahora, :ahora)"
)
CREAR_COBRO = text(
    "INSERT INTO cobro (id, empresa_id, cliente_id, monto, descripcion, estado, vence_el, "
    "fecha_pago, fecha_pago_aproximada, mp_payment_id, created_at, updated_at) "
    "VALUES (:id, :empresa_id, :cliente_id, 1210.00, 'Consulta', :estado, :vence, :fecha, "
    ":aproximada, :pago, :creado, :creado)"
)


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest_asyncio.fixture
async def cliente_http(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as http:
        yield http
    await recursos.cerrar()


async def _empresa_con_cobro(
    http: httpx.AsyncClient,
    engine_dueno: AsyncEngine,
    *,
    estado: str,
    fecha: datetime | None,
    aproximada: bool,
) -> tuple[str, uuid.UUID]:
    registro = await http.post(
        "/auth/registro",
        json={
            "email": "ana@empresa.com",
            "contrasena": CONTRASENA,
            "nombre": "Ana Perez",
            "consentimiento": CONSENTIMIENTO,
        },
    )
    assert registro.status_code == 201, registro.text
    token = str(registro.json()["access_token"])
    cobro_id, cliente_id = uuid.uuid4(), uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        empresa_id = (await conexion.execute(text("SELECT id FROM empresa"))).scalar_one()
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": CREADO}
        )
        await conexion.execute(
            CREAR_COBRO,
            {
                "id": cobro_id,
                "empresa_id": empresa_id,
                "cliente_id": cliente_id,
                "estado": estado,
                "vence": VENCE,
                "fecha": fecha,
                "aproximada": aproximada,
                "pago": "pago-1" if fecha is not None else None,
                "creado": CREADO,
            },
        )
    return token, cobro_id


async def test_un_cobro_pagado_por_link_devuelve_fecha_medio_y_operacion_nula(
    cliente_http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    token, cobro_id = await _empresa_con_cobro(
        cliente_http, engine_dueno, estado="APROBADO", fecha=PAGADO, aproximada=True
    )

    respuesta = await cliente_http.get(
        f"/cobros/{cobro_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["fecha_pago"].startswith("2026-08-03T15:30:00")
    assert cuerpo["fecha_pago_aproximada"] is True
    assert cuerpo["medio_de_pago"] == "LINK_MERCADOPAGO"
    assert cuerpo["numero_de_operacion"] is None
    assert "pagado_en" not in cuerpo


async def test_un_cobro_sin_pagar_no_tiene_fecha_de_pago(
    cliente_http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    token, cobro_id = await _empresa_con_cobro(
        cliente_http, engine_dueno, estado="PENDIENTE", fecha=None, aproximada=False
    )

    respuesta = await cliente_http.get(
        f"/cobros/{cobro_id}", headers={"Authorization": f"Bearer {token}"}
    )

    cuerpo = respuesta.json()
    assert cuerpo["fecha_pago"] is None
    assert cuerpo["fecha_pago_aproximada"] is False
    assert cuerpo["medio_de_pago"] == "LINK_MERCADOPAGO"


async def test_el_detalle_devuelve_el_nombre_y_el_cuit_del_cliente(
    cliente_http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """HU-E6-02 criterio 1: el detalle muestra los datos del cliente, no sólo su id.

    El nombre y el CUIT salen de `master_data` (resueltos en el composition root, no por el
    puerto de `payments`, que por D92 no ve el CUIT). El CUIT se devuelve formateado para mostrar.
    """
    token, cobro_id = await _empresa_con_cobro(
        cliente_http, engine_dueno, estado="PENDIENTE", fecha=None, aproximada=False
    )

    respuesta = await cliente_http.get(
        f"/cobros/{cobro_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["cliente_nombre"] == "Acme SA"
    assert cuerpo["cliente_cuit"] == "20-22222222-3"
