"""Los reembolsos de punta a punta contra PostgreSQL: lo que ningún doble puede probar (H1).

El test unitario de `tests/api/test_reembolso_confirma_el_estado.py` prueba el contrato de commit
con un doble; **acá** se prueba contra la base real que el rechazo y su evento `ERROR` quedan
escritos aunque la respuesta sea un 422, que la solicitud en vuelo sobrevive a una pasarela que no
contesta, y que la suma de las filas es el acumulado después de cada camino.

MercadoPago sigue simulado, siempre. Las tres ramas se eligen con la descripción del cobro
(«rechazar», «demorar»), y como el doble es de proceso (`armar_pasarela`), la decisión tomada al
crear el link sobrevive hasta el reembolso, que es otro request.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

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

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CONTRASENA = "una-contrasena-larga"
CREADO = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, origen, activo, created_at, updated_at) "
    "VALUES (:id, :empresa_id, 'Acme SA', 'PANEL', true, :ahora, :ahora)"
)
#: Lo que haría el webhook: el cobro pasa a pagado con el id que el doble sabe leer
#: (`pago-<preferencia>`). La fecha de pago es ahora: un reembolso manual de hoy no es anterior.
PAGAR = text(
    "UPDATE cobro SET estado = 'APROBADO', mp_payment_id = 'pago-' || mp_preference_id, "
    "fecha_pago = now() - interval '1 hour', medio_de_pago = :medio WHERE id = :id"
)
LEER_ACUMULADO = text(
    "SELECT c.monto_reembolsado, COALESCE(sum(r.monto), 0) AS suma, count(r.id) AS filas "
    "FROM cobro c LEFT JOIN reembolso r ON r.cobro_id = c.id WHERE c.id = :id "
    "GROUP BY c.monto_reembolsado"
)
LEER_BITACORA = text("SELECT resultado FROM registro_de_auditoria WHERE accion = :accion")


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest_asyncio.fixture
async def http(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        yield cliente
    await recursos.cerrar()


async def _administrador(
    http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> tuple[dict[str, str], uuid.UUID]:
    """Registra una empresa (su primer usuario es Administrador) y siembra un cliente."""
    registro = await http.post(
        "/auth/registro",
        json={"email": "ana@empresa.com", "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert registro.status_code == 201, registro.text
    cabeceras = {"Authorization": f"Bearer {registro.json()['access_token']}"}
    cliente_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        empresa_id = (await conexion.execute(text("SELECT id FROM empresa"))).scalar_one()
        await conexion.execute(
            CREAR_CLIENTE, {"id": cliente_id, "empresa_id": empresa_id, "ahora": CREADO}
        )
    return cabeceras, cliente_id


async def _cobro_pagado(
    http: httpx.AsyncClient,
    engine_dueno: AsyncEngine,
    cabeceras: dict[str, str],
    cliente_id: uuid.UUID,
    *,
    descripcion: str = "Consulta de septiembre",
    transferencia: bool = False,
) -> str:
    """Un cobro creado por la API (así el doble aprende su preferencia) y luego pagado."""
    creado = await http.post(
        "/cobros",
        headers=cabeceras,
        json={"cliente_id": str(cliente_id), "monto": "1000.00", "descripcion": descripcion},
    )
    assert creado.status_code == 201, creado.text
    cobro_id = str(creado.json()["id"])
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            PAGAR,
            {
                "id": cobro_id,
                "medio": "TRANSFERENCIA" if transferencia else "LINK_MERCADOPAGO",
            },
        )
    return cobro_id


async def _suma_y_acumulado(engine_dueno: AsyncEngine, cobro_id: str) -> tuple[str, str, int]:
    async with engine_dueno.connect() as conexion:
        fila = (await conexion.execute(LEER_ACUMULADO, {"id": cobro_id})).one()
    return str(fila[0]), str(fila[1]), int(fila[2])


async def _bitacora(engine_dueno: AsyncEngine, accion: str) -> list[str]:
    async with engine_dueno.connect() as conexion:
        filas = await conexion.execute(LEER_BITACORA, {"accion": accion})
        return [str(f[0]) for f in filas]


# ------------------------------------------------------------------ el camino feliz


async def test_dos_reembolsos_parciales_completan_el_cobro_y_un_tercero_es_un_conflicto(
    http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 31: `GET` trae `reembolsos` y el acumulado numérico; las rutas responden 200 y 409."""
    cabeceras, cliente_id = await _administrador(http, engine_dueno)
    cobro_id = await _cobro_pagado(http, engine_dueno, cabeceras, cliente_id)

    antes = (await http.get(f"/cobros/{cobro_id}", headers=cabeceras)).json()
    assert antes["reembolsos"] == []
    assert antes["monto_reembolsado"] == "0.00"
    assert antes["reembolso_en_proceso_monto"] is None

    parcial = await http.post(
        f"/cobros/{cobro_id}/reembolso", headers=cabeceras, json={"monto": "400.00"}
    )
    assert parcial.status_code == 200, parcial.text
    assert parcial.json()["estado"] == "REEMBOLSADO_PARCIAL"
    assert parcial.json()["monto_reembolsado"] == "400.00"
    assert parcial.json()["reembolso_en_proceso"] is False

    total = await http.post(
        f"/cobros/{cobro_id}/reembolso", headers=cabeceras, json={"monto": "600.00"}
    )
    assert total.json()["estado"] == "REEMBOLSADO"

    otro = await http.post(
        f"/cobros/{cobro_id}/reembolso", headers=cabeceras, json={"monto": "1.00"}
    )
    assert otro.status_code == 409, otro.text
    detalle = (await http.get(f"/cobros/{cobro_id}", headers=cabeceras)).json()
    assert [r["monto"] for r in detalle["reembolsos"]] == ["400.00", "600.00"]
    assert {r["origen"] for r in detalle["reembolsos"]} == {"API_MERCADOPAGO"}
    # Caso 28: la suma de las filas es el acumulado.
    assert await _suma_y_acumulado(engine_dueno, cobro_id) == ("1000.00", "1000.00", 2)


async def test_un_monto_mayor_al_pendiente_es_un_422_y_no_escribe_nada(
    http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    cabeceras, cliente_id = await _administrador(http, engine_dueno)
    cobro_id = await _cobro_pagado(http, engine_dueno, cabeceras, cliente_id)

    respuesta = await http.post(
        f"/cobros/{cobro_id}/reembolso", headers=cabeceras, json={"monto": "1000.01"}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert await _suma_y_acumulado(engine_dueno, cobro_id) == ("0.00", "0", 0)


# ------------------------------------------------------------------ H1: el rechazo queda escrito


async def test_un_rechazo_responde_422_pero_el_evento_de_error_queda_escrito(
    http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """**Caso 11 (H1)**, contra la base real: antes de esta unidad el rechazo y su evento se
    descartaban con la excepción, y el administrador nunca recibía la notificación de RN-03."""
    cabeceras, cliente_id = await _administrador(http, engine_dueno)
    cobro_id = await _cobro_pagado(
        http, engine_dueno, cabeceras, cliente_id, descripcion="Consulta que va a rechazar"
    )

    respuesta = await http.post(
        f"/cobros/{cobro_id}/reembolso", headers=cabeceras, json={"monto": "400.00"}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["error"] == "ReembolsoRechazado"
    assert await _bitacora(engine_dueno, "rechazar_reembolso") == ["error"]
    detalle = (await http.get(f"/cobros/{cobro_id}", headers=cabeceras)).json()
    assert detalle["estado"] == "APROBADO"
    assert detalle["reembolso_en_proceso"] is False
    # Sin la marca colgada, se puede volver a intentar.
    assert await _suma_y_acumulado(engine_dueno, cobro_id) == ("0.00", "0", 0)


async def test_demorar_deja_el_reembolso_en_proceso_y_actualizar_estado_lo_confirma_una_vez(
    http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Casos 12, 13 y 14: «Reembolso en proceso» sobrevive al request; «Actualizar estado» lo
    confirma, y apretarlo dos veces inserta una sola fila."""
    cabeceras, cliente_id = await _administrador(http, engine_dueno)
    cobro_id = await _cobro_pagado(
        http, engine_dueno, cabeceras, cliente_id, descripcion="Consulta que va a demorar"
    )

    pedido = await http.post(
        f"/cobros/{cobro_id}/reembolso", headers=cabeceras, json={"monto": "400.00"}
    )
    assert pedido.status_code == 200, pedido.text
    assert pedido.json()["reembolso_en_proceso"] is True
    assert pedido.json()["reembolso_en_proceso_monto"] == "400.00"
    assert pedido.json()["estado"] == "APROBADO"
    otro = await http.post(
        f"/cobros/{cobro_id}/reembolso", headers=cabeceras, json={"monto": "100.00"}
    )
    assert otro.status_code == 409, otro.text

    primera = await http.post(f"/cobros/{cobro_id}/reembolso/actualizacion", headers=cabeceras)
    segunda = await http.post(f"/cobros/{cobro_id}/reembolso/actualizacion", headers=cabeceras)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["estado"] == "REEMBOLSADO_PARCIAL"
    assert segunda.json()["monto_reembolsado"] == "400.00"
    assert await _suma_y_acumulado(engine_dueno, cobro_id) == ("400.00", "400.00", 1)


# ------------------------------------------------------------------ manual y corrección


async def test_el_registro_manual_es_de_transferencias_y_se_corrige_una_sola_vez(
    http: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    cabeceras, cliente_id = await _administrador(http, engine_dueno)
    por_link = await _cobro_pagado(http, engine_dueno, cabeceras, cliente_id)
    cobro_id = await _cobro_pagado(http, engine_dueno, cabeceras, cliente_id, transferencia=True)
    # El día de hoy **en Argentina**, que es como lo mide el dominio (no el de UTC).
    hoy = datetime.now(timezone(timedelta(hours=-3))).date().isoformat()
    cuerpo = {"monto": "300.00", "fecha": hoy, "referencia": "OP-9", "motivo": "Devolucion"}

    sobre_un_link = await http.post(
        f"/cobros/{por_link}/reembolsos", headers=cabeceras, json=cuerpo
    )
    assert sobre_un_link.status_code == 409, sobre_un_link.text

    registrado = await http.post(f"/cobros/{cobro_id}/reembolsos", headers=cabeceras, json=cuerpo)
    assert registrado.status_code == 200, registrado.text
    assert registrado.json()["estado"] == "REEMBOLSADO_PARCIAL"
    fila = (await http.get(f"/cobros/{cobro_id}", headers=cabeceras)).json()["reembolsos"][0]
    assert fila["origen"] == "MANUAL"
    assert fila["referencia"] == "OP-9"
    assert fila["corregido"] is False

    correccion_url = f"/cobros/{cobro_id}/reembolsos/{fila['id']}/correccion"
    corregido = await http.post(correccion_url, headers=cabeceras, json={"motivo": "Se cargo mal"})
    assert corregido.status_code == 200, corregido.text
    assert corregido.json()["estado"] == "APROBADO"
    otra_vez = await http.post(correccion_url, headers=cabeceras, json={"motivo": "Otra vez"})
    assert otra_vez.status_code == 409, otra_vez.text

    detalle = (await http.get(f"/cobros/{cobro_id}", headers=cabeceras)).json()
    assert [r["monto"] for r in detalle["reembolsos"]] == ["300.00", "-300.00"]
    assert [r["corregido"] for r in detalle["reembolsos"]] == [True, False]
    assert detalle["reembolsos"][1]["corrige_a"] == fila["id"]
    assert await _suma_y_acumulado(engine_dueno, cobro_id) == ("0.00", "0.00", 2)
