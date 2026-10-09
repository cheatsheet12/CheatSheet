"""ARCA de punta a punta contra PostgreSQL real, con delegación del web service (ADR-0014).

Lo que no se puede probar con un doble, y este archivo cubre:

- que **el ambiente no se pueda elegir desde el request** (caso 15): elegirlo mal significa
  emitir contra el servidor equivocado;
- que **la CUIT por la que se pregunta a ARCA salga de los datos de la empresa y nunca del
  cuerpo del pedido**: con delegación, esa CUIT decide en nombre de quién se factura;
- que el ticket de la plataforma quede **cifrado** en su tabla, sea **uno por servicio para
  todas las empresas**, y no salga por ninguna respuesta.

ARCA sigue simulada, siempre. Homologación también tiene límites de uso, y un test que
consume un ticket de 12 horas rompe el que corre después.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.main import create_app
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"


def _settings(**extra: object) -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
        **extra,  # type: ignore[arg-type]
    )


@pytest_asyncio.fixture
async def recursos(esquema_migrado: None) -> AsyncIterator[Recursos]:
    creados = Recursos.crear(_settings())
    yield creados
    await creados.cerrar()


@pytest_asyncio.fixture
async def cliente(recursos: Recursos) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(recursos.settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as abierto:
        yield abierto


async def _registrar(cliente: httpx.AsyncClient, email: str) -> str:
    respuesta = await cliente.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _empresa_de(token: str) -> EmpresaId:
    payload = token.split(".")[1]
    relleno = "=" * (-len(payload) % 4)
    return EmpresaId(UUID(json.loads(base64.urlsafe_b64decode(payload + relleno))["empresa_id"]))


CUIT_DE_LA_EMPRESA = "30000000015"
OTRA_CUIT = "30000000023"
#: Empieza con `PREFIJO_SIN_DELEGACION`: el simulador responde que no delegó.
CUIT_SIN_DELEGACION = "30999999006"


async def _completar_empresa(
    cliente: httpx.AsyncClient, token: str, cuit: str = CUIT_DE_LA_EMPRESA
) -> None:
    respuesta = await cliente.put(
        "/auth/empresa",
        headers=_auth(token),
        json={
            "razon_social": "Estudio Ejemplo SRL",
            "cuit": cuit,
            "condicion_iva": "RESPONSABLE_INSCRIPTO",
            "nombre_responsable": "Laura Ejemplo",
            "email_contacto": "admin@estudio-ejemplo.test",
        },
    )
    assert respuesta.status_code == 200, respuesta.text


async def _conectar_arca(
    cliente: httpx.AsyncClient, token: str, contenido: str = "", **parametros: str
) -> httpx.Response:
    return await cliente.put(
        "/integraciones/ARCA/conexion",
        headers=_auth(token),
        json={
            "contenido": base64.b64encode(contenido.encode()).decode(),
            "parametros": parametros,
        },
    )


async def _empresa_con_arca(cliente: httpx.AsyncClient, email: str, cuit: str) -> str:
    token = await _registrar(cliente, email)
    await _completar_empresa(cliente, token, cuit)
    respuesta = await _conectar_arca(cliente, token)
    assert respuesta.status_code == 200, respuesta.text
    return token


def _tarjeta(cuerpo: dict[str, object], sistema: str) -> dict[str, object]:
    integraciones = cuerpo["integraciones"]
    assert isinstance(integraciones, list)
    return next(i for i in integraciones if i["sistema"] == sistema)


# ----------------------------------------------------------------- conectar = verificar la delegación


@pytest.mark.asyncio
async def test_una_empresa_que_delego_queda_conectada_y_se_audita(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Primer criterio de aceptación de HU-E2-01 con ADR-0014."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _completar_empresa(cliente, token)

    respuesta = await _conectar_arca(cliente, token)

    assert respuesta.status_code == 200, respuesta.text
    vista = respuesta.json()
    assert vista["estado"] == "CONECTADO"
    assert "30-00000001-5" in str(vista["etiqueta"])
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT count(*) FROM registro_de_auditoria WHERE modulo = 'integrations'")
        )
        assert filas.scalar_one() == 1


@pytest.mark.asyncio
async def test_una_empresa_que_no_delego_no_escribe_ninguna_fila(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Segundo criterio: se indica el error y queda sin conectar."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _completar_empresa(cliente, token, CUIT_SIN_DELEGACION)

    respuesta = await _conectar_arca(cliente, token)

    assert respuesta.status_code == 422, respuesta.text
    assert "no registra" in respuesta.text
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(text("SELECT count(*) FROM configuracion_de_integracion"))
        assert filas.scalar_one() == 0


@pytest.mark.asyncio
async def test_sin_cuit_cargada_no_se_puede_verificar(cliente: httpx.AsyncClient) -> None:
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await _conectar_arca(cliente, token)

    assert respuesta.status_code == 422, respuesta.text
    assert "CUIT valido" in respuesta.text


@pytest.mark.asyncio
async def test_la_cuit_del_pedido_se_ignora_y_vale_la_de_la_empresa(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """**La garantía de ADR-0014.** La CUIT decide en nombre de quién se factura: si el
    cuerpo del pedido pudiera elegirla, cualquier Administrador apuntaría el certificado de
    la plataforma a otra empresa."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _completar_empresa(cliente, token)

    respuesta = await _conectar_arca(cliente, token, contenido=OTRA_CUIT, cuit=OTRA_CUIT)

    assert respuesta.status_code == 200, respuesta.text
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT parametros->>'cuit' FROM configuracion_de_integracion")
        )
        assert filas.scalar_one() == CUIT_DE_LA_EMPRESA


@pytest.mark.asyncio
async def test_la_tarjeta_muestra_el_ambiente_y_el_estado(cliente: httpx.AsyncClient) -> None:
    """Cuarto criterio de aceptación de HU-E2-01."""
    token = await _empresa_con_arca(cliente, "ana@empresa.com", CUIT_DE_LA_EMPRESA)

    listado = await cliente.get("/integraciones", headers=_auth(token))

    tarjeta = _tarjeta(listado.json(), "ARCA")
    assert tarjeta["ambiente"] == "HOMOLOGACION"
    assert tarjeta["estado"] == "CONECTADO"
    assert tarjeta["configurada"] is True


# ----------------------------------------------------------------- caso 15


@pytest.mark.asyncio
async def test_el_ambiente_no_se_puede_elegir_desde_el_request(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 15. **La garantía más cara de esta unidad.** Sale de `APP_ENV` y de ningún
    otro lado: se manda `ambiente: PRODUCCION` a propósito y se verifica que se ignore."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _completar_empresa(cliente, token)

    respuesta = await _conectar_arca(cliente, token, ambiente="PRODUCCION")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["ambiente"] == "HOMOLOGACION"
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(text("SELECT ambiente FROM configuracion_de_integracion"))
        assert filas.scalar_one() == "HOMOLOGACION"


# ----------------------------------------------------------------- el ticket de la plataforma


async def _ticket(recursos: Recursos, empresa_id: EmpresaId, servicio: ServicioDeArca) -> bytes:
    obtenido = b""
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Integraciones.armar(unidad.sesion, recursos.settings)
        obtenido = (await piezas.tickets_de_plataforma.ejecutar(servicio)).contenido
    return obtenido


@pytest.mark.asyncio
async def test_el_ticket_de_plataforma_se_guarda_cifrado(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    token = await _empresa_con_arca(cliente, "ana@empresa.com", CUIT_DE_LA_EMPRESA)

    await _ticket(recursos, _empresa_de(token), ServicioDeArca.WSFE)

    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text(
                "SELECT servicio, contenido_cifrado, algoritmo FROM ticket_de_plataforma"
                " WHERE servicio = 'wsfe'"
            )
        )
        servicio, contenido, algoritmo = filas.one()
    assert servicio == "wsfe"
    assert algoritmo == "AES-256-GCM/v1"
    assert b"TICKET-SIMULADO" not in bytes(contenido)


@pytest.mark.asyncio
async def test_dos_empresas_usan_el_mismo_ticket_de_plataforma(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """WSAA da un ticket por certificado y servicio: uno por empresa fallaría 12 horas."""
    token_a = await _empresa_con_arca(cliente, "ana@empresa-a.com", CUIT_DE_LA_EMPRESA)
    token_b = await _empresa_con_arca(cliente, "beto@empresa-b.com", OTRA_CUIT)

    primero = await _ticket(recursos, _empresa_de(token_a), ServicioDeArca.WSFE)
    segundo = await _ticket(recursos, _empresa_de(token_b), ServicioDeArca.WSFE)

    assert primero == segundo
    async with engine_dueno.begin() as conexion:
        # Conectar ya consultó el padrón, que tiene su propio ticket: se cuentan los de WSFE.
        filas = await conexion.execute(
            text("SELECT count(*) FROM ticket_de_plataforma WHERE servicio = 'wsfe'")
        )
        assert filas.scalar_one() == 1


@pytest.mark.asyncio
async def test_dos_servicios_conviven_como_dos_filas(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    token = await _empresa_con_arca(cliente, "ana@empresa.com", CUIT_DE_LA_EMPRESA)

    await _ticket(recursos, _empresa_de(token), ServicioDeArca.WSFE)
    await _ticket(recursos, _empresa_de(token), ServicioDeArca.PADRON_A5)

    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(text("SELECT servicio FROM ticket_de_plataforma"))
        assert sorted(f[0] for f in filas.all()) == ["ws_sr_padron_a5", "wsfe"]


# ----------------------------------------------------------------- caso 26 y verificación


@pytest.mark.asyncio
async def test_ni_la_marca_ni_el_ticket_salen_por_la_api(
    cliente: httpx.AsyncClient, recursos: Recursos
) -> None:
    token = await _empresa_con_arca(cliente, "ana@empresa.com", CUIT_DE_LA_EMPRESA)
    await _ticket(recursos, _empresa_de(token), ServicioDeArca.WSFE)

    listado = await cliente.get("/integraciones", headers=_auth(token))
    verificacion = await cliente.post("/integraciones/verificacion", headers=_auth(token))

    for cuerpo in (listado.text, verificacion.text):
        assert "TICKET-SIMULADO" not in cuerpo
        assert "delegacion-arca" not in cuerpo


@pytest.mark.asyncio
async def test_verificar_una_delegacion_vigente_la_deja_conectada(
    cliente: httpx.AsyncClient,
) -> None:
    token = await _empresa_con_arca(cliente, "ana@empresa.com", CUIT_DE_LA_EMPRESA)

    respuesta = await cliente.post("/integraciones/verificacion", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    assert _tarjeta(respuesta.json(), "ARCA")["estado"] == "CONECTADO"


# ----------------------------------------------------------------- cambio de CUIT


@pytest.mark.asyncio
async def test_cambiar_la_cuit_de_la_empresa_desconecta_arca(cliente: httpx.AsyncClient) -> None:
    """Hallazgo de la prueba local del 08/10: si ARCA quedaba conectada con la CUIT vieja, el
    comprobante saldría impreso con la nueva y autorizado en ARCA con la anterior."""
    token = await _empresa_con_arca(cliente, "ana@empresa.com", CUIT_DE_LA_EMPRESA)

    await _completar_empresa(cliente, token, OTRA_CUIT)

    listado = await cliente.get("/integraciones", headers=_auth(token))
    tarjeta = _tarjeta(listado.json(), "ARCA")
    assert tarjeta["estado"] == "NO_CONECTADO"
    assert "30-00000002-3" in str(tarjeta["detalle"]) or "30000000023" in str(tarjeta["detalle"])


@pytest.mark.asyncio
async def test_guardar_la_empresa_sin_cambiar_la_cuit_no_toca_arca(
    cliente: httpx.AsyncClient,
) -> None:
    token = await _empresa_con_arca(cliente, "ana@empresa.com", CUIT_DE_LA_EMPRESA)

    await _completar_empresa(cliente, token, CUIT_DE_LA_EMPRESA)

    listado = await cliente.get("/integraciones", headers=_auth(token))
    assert _tarjeta(listado.json(), "ARCA")["estado"] == "CONECTADO"
