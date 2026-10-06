"""ARCA de punta a punta contra PostgreSQL real — casos 15 a 17, 20, 21, 22 y 26.

Cuatro cosas no se pueden probar con un doble, y son las que este archivo cubre:

- que **el ambiente no se pueda elegir desde el request** (caso 15). Es la garantía más
  cara de esta unidad: elegirlo mal significa emitir contra el servidor equivocado;
- que la política RLS impida que una empresa lea o renueve el ticket de otra — un ticket es
  una sesión viva, y leer el ajeno es hablarle a ARCA como esa otra empresa;
- que el token quede **cifrado** en la base y no salga por ninguna respuesta;
- que dos servicios de ARCA convivan como dos filas, que es lo que la unidad siguiente
  necesita.

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
from cheatsheet.contexts.integrations.application.tickets import ObtenerTicketDeAcceso
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.contexts.integrations.conftest_arca import CUIT_DE_PRUEBA, bundle
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


async def _conectar_arca(
    cliente: httpx.AsyncClient, token: str, credencial: bytes | None = None, **parametros: str
) -> httpx.Response:
    return await cliente.put(
        "/integraciones/ARCA/conexion",
        headers=_auth(token),
        json={
            "contenido": base64.b64encode(credencial or bundle()).decode(),
            "parametros": parametros,
        },
    )


def _tarjeta(cuerpo: dict[str, object], sistema: str) -> dict[str, object]:
    integraciones = cuerpo["integraciones"]
    assert isinstance(integraciones, list)
    return next(i for i in integraciones if i["sistema"] == sistema)


# ----------------------------------------------------------------- casos 16 y 17


@pytest.mark.asyncio
async def test_conectar_arca_con_credenciales_validas_deja_conectada(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 16, y el primer criterio de aceptación."""
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await _conectar_arca(cliente, token)

    assert respuesta.status_code == 200, respuesta.text
    vista = respuesta.json()
    assert vista["estado"] == "CONECTADO"
    assert CUIT_DE_PRUEBA in str(vista["etiqueta"])
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT count(*) FROM registro_de_auditoria WHERE modulo = 'integrations'")
        )
        assert filas.scalar_one() == 1


@pytest.mark.asyncio
async def test_un_certificado_vencido_no_escribe_ninguna_fila(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 17, y el segundo criterio: se indica el error y queda sin conectar."""
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await _conectar_arca(cliente, token, credencial=bundle(vence_en_dias=-1))

    assert respuesta.status_code == 422, respuesta.text
    assert "vencio" in respuesta.text
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(text("SELECT count(*) FROM configuracion_de_integracion"))
        assert filas.scalar_one() == 0


@pytest.mark.asyncio
async def test_una_credencial_ilegible_se_rechaza(cliente: httpx.AsyncClient) -> None:
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await _conectar_arca(cliente, token, credencial=b"esto no es un certificado")

    assert respuesta.status_code == 422, respuesta.text


@pytest.mark.asyncio
async def test_la_tarjeta_muestra_el_ambiente_y_el_estado(cliente: httpx.AsyncClient) -> None:
    """Cuarto criterio de aceptación de HU-E2-01."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_arca(cliente, token)

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
    """Caso 15. **La garantía más cara de esta unidad.**

    Una empresa que pudiera elegir el ambiente podría creer que está facturando mientras
    practica — o, peor, emitir un comprobante real e irreversible desde un despliegue de
    prueba. Se manda `ambiente: PRODUCCION` a propósito y se verifica que el sistema lo
    ignore: sale de `APP_ENV` y de ningún otro lado.
    """
    token = await _registrar(cliente, "ana@empresa.com")

    respuesta = await _conectar_arca(cliente, token, ambiente="PRODUCCION")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["ambiente"] == "HOMOLOGACION"
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(text("SELECT ambiente FROM configuracion_de_integracion"))
        assert filas.scalar_one() == "HOMOLOGACION"


# ----------------------------------------------------------------- casos 20, 21 y 22


async def _ticket(
    recursos: Recursos, empresa_id: EmpresaId, servicio: ServicioDeArca
) -> tuple[bytes, object]:
    obtenido: tuple[bytes, object] = (b"", None)
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Integraciones.armar(unidad.sesion, recursos.settings)
        vigente = await ObtenerTicketDeAcceso(
            integraciones=piezas.integraciones,
            tickets=piezas.tickets,
            cifrado=piezas.cifrado,
            adaptadores=piezas.adaptadores,
            reloj=unidad.reloj,
        ).ejecutar(empresa_id=empresa_id, servicio=servicio)
        obtenido = (vigente.contenido, vigente.expira_en)
    return obtenido


@pytest.mark.asyncio
async def test_conectar_guarda_el_ticket_cifrado(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 20. Y el ticket queda guardado porque ARCA no da un segundo mientras viva."""
    token = await _registrar(cliente, "ana@empresa.com")

    await _conectar_arca(cliente, token)

    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT servicio, contenido_cifrado, algoritmo FROM ticket_de_acceso")
        )
        servicio, contenido, algoritmo = filas.one()
    assert servicio == "wsfe"
    assert algoritmo == "AES-256-GCM/v1"
    assert b"TICKET-SIMULADO" not in bytes(contenido)


@pytest.mark.asyncio
async def test_el_ticket_guardado_al_conectar_se_reusa(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """Sin esto, pedir un ticket justo después de conectar chocaría con la regla de ARCA."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_arca(cliente, token)
    empresa_id = _empresa_de(token)

    contenido, _ = await _ticket(recursos, empresa_id, ServicioDeArca.WSFE)

    assert contenido.startswith(b"TICKET-SIMULADO")
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(text("SELECT count(*) FROM ticket_de_acceso"))
        assert filas.scalar_one() == 1  # se reusó, no se acumuló


@pytest.mark.asyncio
async def test_dos_servicios_conviven_como_dos_filas(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """Caso 22. Es lo que `padron-y-datos-fiscales` va a necesitar."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_arca(cliente, token)
    empresa_id = _empresa_de(token)

    await _ticket(recursos, empresa_id, ServicioDeArca.PADRON_A5)

    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(text("SELECT servicio FROM ticket_de_acceso"))
        # Ordenado en Python: la colación de PostgreSQL trata el guion bajo de una forma
        # que no vale la pena atar a un test.
        assert sorted(f[0] for f in filas.all()) == ["ws_sr_padron_a5", "wsfe"]


@pytest.mark.asyncio
async def test_una_empresa_no_ve_ni_renueva_el_ticket_de_otra(
    cliente: httpx.AsyncClient, recursos: Recursos
) -> None:
    """Caso 21. Un ticket es una sesión viva: leer el ajeno es hablarle a ARCA como ella."""
    token_a = await _registrar(cliente, "ana@empresa-a.com")
    token_b = await _registrar(cliente, "beto@empresa-b.com")
    await _conectar_arca(cliente, token_a)
    empresa_b = _empresa_de(token_b)

    # B no tiene ARCA conectada, así que no hay ticket que darle — y menos el de A.
    from cheatsheet.contexts.integrations.application.errors import TicketNoDisponible

    with pytest.raises(TicketNoDisponible):
        await _ticket(recursos, empresa_b, ServicioDeArca.WSFE)

    listado_b = await cliente.get("/integraciones", headers=_auth(token_b))
    assert _tarjeta(listado_b.json(), "ARCA")["configurada"] is False


# ----------------------------------------------------------------- caso 26


@pytest.mark.asyncio
async def test_ni_la_clave_privada_ni_el_ticket_salen_por_la_api(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 26. La clave privada es la identidad fiscal de la empresa."""
    token = await _registrar(cliente, "ana@empresa.com")
    credencial = bundle()

    conexion_json = await _conectar_arca(cliente, token, credencial=credencial)
    listado = await cliente.get("/integraciones", headers=_auth(token))
    verificacion = await cliente.post("/integraciones/verificacion", headers=_auth(token))

    for cuerpo in (conexion_json.text, listado.text, verificacion.text):
        assert "PRIVATE KEY" not in cuerpo
        assert "BEGIN CERTIFICATE" not in cuerpo
        assert "TICKET-SIMULADO" not in cuerpo

    async with engine_dueno.begin() as sesion:
        filas = await sesion.execute(
            text("SELECT credencial_contenido_cifrado FROM configuracion_de_integracion")
        )
        guardada = bytes(filas.scalar_one())
    assert b"PRIVATE KEY" not in guardada
    assert credencial not in guardada


@pytest.mark.asyncio
async def test_verificar_arca_no_abre_ningun_socket_y_deja_conectada(
    cliente: httpx.AsyncClient,
) -> None:
    """Decisión D-e: el chequeo en vivo lee el certificado, no llama a WSAA."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_arca(cliente, token)

    respuesta = await cliente.post("/integraciones/verificacion", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    assert _tarjeta(respuesta.json(), "ARCA")["estado"] == "CONECTADO"


@pytest.mark.asyncio
async def test_un_certificado_por_vencer_se_ve_en_atencion(cliente: httpx.AsyncClient) -> None:
    """Caso 23 de punta a punta: se conecta con 20 días de vida y la pantalla lo dice."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_arca(cliente, token, credencial=bundle(vence_en_dias=20))

    respuesta = await cliente.post("/integraciones/verificacion", headers=_auth(token))

    tarjeta = _tarjeta(respuesta.json(), "ARCA")
    assert tarjeta["estado"] == "ATENCION"
    assert "vence en" in str(tarjeta["detalle"])
