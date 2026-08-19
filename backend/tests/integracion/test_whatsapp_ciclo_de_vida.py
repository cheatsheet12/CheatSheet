"""El ciclo de vida completo de HU-E2-03 contra PostgreSQL real — casos 16 y 21 a 24.

Tres cosas no se pueden probar con un doble, y son justo las que este archivo cubre:

- que la política RLS impida que una empresa vea o sondee la fila pendiente de otra
  (Row-Level Security es una función del motor: un test contra un diccionario pasaría sin
  probar nada, que es peor que no tener test);
- que `empresas_con_integracion_pendiente()` —la única lectura entre empresas del
  sistema— devuelva sólo ids y nada más;
- que la credencial guardada no salga nunca por la API.

Meta sigue simulada, siempre: la regla del workflow es que los tests no tocan la red de un
proveedor externo, y una base en localhost no es eso.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.main import create_app
from cheatsheet.contexts.integrations.application.sondeo import (
    MOTIVO_VENCIDO,
    SondearIntegracionesPendientes,
)
from cheatsheet.contexts.integrations.domain.valores import EstadoDeConexion
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    empresas_con_integracion_pendiente,
)
from cheatsheet.contexts.integrations.infrastructure.whatsapp.simulado import (
    PARAMETRO_NAME_STATUS,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers import tasks_integrations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
FAKE_TOKEN_FOR_TESTS = b"fake-token-for-tests"
PHONE_ID = "109876543210987"
WABA_ID = "102030405060708"


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
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


def _cuerpo(**extra: str) -> dict[str, object]:
    return {
        "contenido": base64.b64encode(FAKE_TOKEN_FOR_TESTS).decode(),
        "parametros": {"phone_number_id": PHONE_ID, "waba_id": WABA_ID, **extra},
    }


async def _conectar_whatsapp(
    cliente: httpx.AsyncClient, token: str, **extra: str
) -> dict[str, object]:
    respuesta = await cliente.put(
        "/integraciones/WHATSAPP/conexion", headers=_auth(token), json=_cuerpo(**extra)
    )
    assert respuesta.status_code == 200, respuesta.text
    return dict(respuesta.json())


def _tarjeta(cuerpo: dict[str, object], sistema: str) -> dict[str, object]:
    integraciones = cuerpo["integraciones"]
    assert isinstance(integraciones, list)
    return next(i for i in integraciones if i["sistema"] == sistema)


def _empresa_de(token: str) -> EmpresaId:
    """Read the company out of the access token instead of asking the API for it.

    The claim is already there — `EmpresaMiddleware` reads exactly this on every request —
    and decoding it here keeps the test from depending on an endpoint that has nothing to
    do with what it is checking.
    """
    payload = token.split(".")[1]
    relleno = "=" * (-len(payload) % 4)
    datos = json.loads(base64.urlsafe_b64decode(payload + relleno))
    return EmpresaId(UUID(datos["empresa_id"]))


async def _sondear(
    recursos: Recursos, empresa_id: EmpresaId, *, ahora: datetime, maximo_dias: int = 7
) -> int:
    """Lo que corre la tarea de Celery, sin Celery ni Redis de por medio."""
    resueltos = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        piezas = Integraciones.armar(unidad.sesion, recursos.settings)
        desenlaces = await SondearIntegracionesPendientes(
            integraciones=piezas.integraciones,
            cifrado=piezas.cifrado,
            adaptadores=piezas.adaptadores,
            publicador=unidad.publicador,
            reloj=RelojFijo(ahora),
            timeout_segundos=recursos.settings.whatsapp_timeout_segundos,
            maximo_dias=maximo_dias,
        ).ejecutar(empresa_id=empresa_id)
        resueltos = len(desenlaces)
    return resueltos


# --------------------------------------------------------------------- caso 16


@pytest.mark.asyncio
async def test_conectar_whatsapp_deja_la_integracion_pendiente_y_lo_audita(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 16. Primer criterio de aceptación: se inicia la verificación y queda pendiente."""
    token = await _registrar(cliente, "ana@empresa.com")

    vista = await _conectar_whatsapp(cliente, token)

    assert vista["estado"] == "PENDIENTE"
    assert vista["configurada"] is True
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT accion FROM registro_de_auditoria WHERE modulo = 'integrations'")
        )
        acciones = [fila[0] for fila in filas.all()]
    assert len(acciones) == 1


@pytest.mark.asyncio
async def test_una_pendiente_no_ofrece_reconectar_y_arranca_el_reloj(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """`pendiente_desde` es lo que después decide cuándo dejar de esperar (gap H10)."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)

    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT estado, pendiente_desde FROM configuracion_de_integracion")
        )
        estado, pendiente_desde = filas.one()

    assert estado == "PENDIENTE"
    assert pendiente_desde is not None


# --------------------------------------------------------- casos 17, 18 y 20 de punta a punta


async def _responde_meta(engine: AsyncEngine, name_status: str) -> None:
    """Cambia lo que el simulado va a contestar en el próximo sondeo.

    Es la única forma de reproducir lo que realmente pasa —Meta cambia de opinión entre
    una consulta y la siguiente, horas después— sin esperar 24 horas ni pinchar el
    adaptador desde adentro del caso de uso.
    """
    async with engine.begin() as conexion:
        await conexion.execute(
            text("UPDATE configuracion_de_integracion SET parametros = parametros || :nuevo"),
            {"nuevo": json.dumps({PARAMETRO_NAME_STATUS: name_status})},
        )


@pytest.mark.asyncio
async def test_el_sondeo_aprueba_el_numero_y_guarda_el_display_name(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """Caso 17 de punta a punta. Segundo criterio de aceptación de HU-E2-03.

    Se conecta pendiente —el desenlace real—, después Meta cambia de opinión, y recién ahí
    el sondeo la resuelve. Es la transición completa, no un atajo.
    """
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)
    assert (await _sondear(recursos, empresa_id, ahora=datetime.now(UTC))) == 0

    await _responde_meta(engine_dueno, "APPROVED")
    resueltos = await _sondear(recursos, empresa_id, ahora=datetime.now(UTC))

    assert resueltos == 1
    listado = await cliente.get("/integraciones", headers=_auth(token))
    tarjeta = _tarjeta(listado.json(), "WHATSAPP")
    assert tarjeta["estado"] == "CONECTADO"
    assert tarjeta["etiqueta"]


@pytest.mark.asyncio
async def test_el_sondeo_que_rechaza_deja_el_motivo_en_la_tarjeta(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """Caso 18 de punta a punta. Tercer criterio: se notifica el motivo y queda sin conectar."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)

    await _responde_meta(engine_dueno, "DECLINED")
    resueltos = await _sondear(recursos, empresa_id, ahora=datetime.now(UTC))

    assert resueltos == 1
    listado = await cliente.get("/integraciones", headers=_auth(token))
    tarjeta = _tarjeta(listado.json(), "WHATSAPP")
    assert tarjeta["estado"] == "NO_CONECTADO"
    assert tarjeta["detalle"]
    # Sigue configurada: la pantalla ofrece «Reconectar», no «Conectar».
    assert tarjeta["configurada"] is True


@pytest.mark.asyncio
async def test_el_sondeo_que_sigue_pendiente_no_cambia_nada(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """Caso 19 contra la base: 48 sondeos por día no pueden dejar 48 filas de auditoría."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)

    for _ in range(3):
        assert await _sondear(recursos, empresa_id, ahora=datetime.now(UTC)) == 0

    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT count(*) FROM registro_de_auditoria WHERE modulo = 'integrations'")
        )
        assert filas.scalar_one() == 1  # sólo la conexión inicial


@pytest.mark.asyncio
async def test_pasado_el_maximo_el_sondeo_deja_de_esperar(
    cliente: httpx.AsyncClient, recursos: Recursos
) -> None:
    """Caso 20 contra la base."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)

    resueltos = await _sondear(recursos, empresa_id, ahora=datetime.now(UTC) + timedelta(days=8))

    assert resueltos == 1
    listado = await cliente.get("/integraciones", headers=_auth(token))
    tarjeta = _tarjeta(listado.json(), "WHATSAPP")
    assert tarjeta["estado"] == "NO_CONECTADO"
    assert tarjeta["detalle"] == MOTIVO_VENCIDO


# ----------------------------------------------------------------- casos 21 y 22


@pytest.mark.asyncio
async def test_una_empresa_no_ve_ni_sondea_la_pendiente_de_otra(
    cliente: httpx.AsyncClient, recursos: Recursos
) -> None:
    """Caso 21. La barrera es la política RLS, no un `WHERE` que alguien podría olvidar."""
    token_a = await _registrar(cliente, "ana@empresa-a.com")
    token_b = await _registrar(cliente, "beto@empresa-b.com")
    await _conectar_whatsapp(cliente, token_a)
    empresa_b = _empresa_de(token_b)

    listado_b = await cliente.get("/integraciones", headers=_auth(token_b))
    tarjeta_b = _tarjeta(listado_b.json(), "WHATSAPP")

    assert tarjeta_b["estado"] == "NO_CONECTADO"
    assert tarjeta_b["configurada"] is False
    # Y el sondeo de B tampoco alcanza la fila de A.
    assert await _sondear(recursos, empresa_b, ahora=datetime.now(UTC) + timedelta(days=8)) == 0


@pytest.mark.asyncio
async def test_el_barrido_entre_empresas_devuelve_solo_ids(
    cliente: httpx.AsyncClient, recursos: Recursos
) -> None:
    """Caso 22. La función `SECURITY DEFINER` es un agujero en la única barrera
    multi-empresa del sistema, así que se la mantiene tan angosta que lo que salga por
    ella no sirva para nada por sí solo."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)

    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_integracion_pendiente(sesion)
        columnas = await sesion.execute(text("SELECT * FROM empresas_con_integracion_pendiente()"))
        nombres = list(columnas.keys())

    assert empresas == [empresa_id]
    assert nombres == ["empresa_id"]


@pytest.mark.asyncio
async def test_sin_empresa_declarada_no_se_ve_ninguna_configuracion(
    cliente: httpx.AsyncClient, recursos: Recursos
) -> None:
    """La sesión sin empresa existe para la función, no para leer la tabla."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)

    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        filas = await sesion.execute(text("SELECT count(*) FROM configuracion_de_integracion"))

    assert filas.scalar_one() == 0


@pytest.mark.asyncio
async def test_una_integracion_resuelta_desaparece_del_barrido(
    cliente: httpx.AsyncClient, recursos: Recursos
) -> None:
    """Si no, se sondearía para siempre una fila que ya se resolvió."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)

    await _sondear(recursos, empresa_id, ahora=datetime.now(UTC) + timedelta(days=8))

    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        assert await empresas_con_integracion_pendiente(sesion) == []


# --------------------------------------------------------------------- caso 24


@pytest.mark.asyncio
async def test_la_credencial_de_whatsapp_no_sale_por_ninguna_respuesta(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
) -> None:
    """Caso 24. Ni el token, ni los identificadores de Meta, ni el texto cifrado."""
    token = await _registrar(cliente, "ana@empresa.com")

    conexion_json = await _conectar_whatsapp(cliente, token)
    listado = await cliente.get("/integraciones", headers=_auth(token))
    verificacion = await cliente.post("/integraciones/verificacion", headers=_auth(token))

    for cuerpo in (str(conexion_json), listado.text, verificacion.text):
        assert FAKE_TOKEN_FOR_TESTS.decode() not in cuerpo
        assert PHONE_ID not in cuerpo
        assert WABA_ID not in cuerpo

    # Y en la base está cifrado, no en claro.
    async with engine_dueno.begin() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT credencial_contenido_cifrado, credencial_algoritmo "
                "FROM configuracion_de_integracion"
            )
        )
        contenido, algoritmo = filas.one()
    assert FAKE_TOKEN_FOR_TESTS not in bytes(contenido)
    assert algoritmo == "AES-256-GCM/v1"


@pytest.mark.asyncio
async def test_reconectar_vuelve_a_mandar_el_numero_a_revision(
    cliente: httpx.AsyncClient,
) -> None:
    """Y no acumula filas: la identidad del agregado es `(empresa, sistema)`."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token, **{PARAMETRO_NAME_STATUS: "APPROVED"})

    vista = await _conectar_whatsapp(cliente, token)

    assert vista["estado"] == "PENDIENTE"
    listado = await cliente.get("/integraciones", headers=_auth(token))
    integraciones = listado.json()["integraciones"]
    assert len([i for i in integraciones if i["sistema"] == "WHATSAPP"]) == 1


# ------------------------------------------------- las dos tareas, de punta a punta

requiere_redis = pytest.mark.skipif(
    os.environ.get("REDIS_URL", "").strip() == "",
    reason="Necesita Redis: el registro de idempotencia vive ahí.",
)


@requiere_redis
@pytest.mark.asyncio
async def test_el_barrido_encuentra_la_empresa_y_la_tarea_resuelve_su_pendiente(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """El camino completo de la tarea: barrido → fan-out → sondeo → auditoría → aviso.

    El despachador se reemplaza por un espía a propósito: encolar de verdad dejaría
    mensajes en un Redis que nadie consume, y lo que importa acá es **a quién** se encola,
    que es lo único que el barrido decide.
    """
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)
    await _responde_meta(engine_dueno, "APPROVED")

    encoladas: list[EmpresaId] = []

    def _anotar(_settings: object, empresa: EmpresaId) -> None:
        encoladas.append(empresa)

    with mock.patch.object(tasks_integrations, "_encolar_empresa", _anotar):
        encontradas = await tasks_integrations.sondear_pendientes(recursos)

    assert encontradas == 1
    assert encoladas == [empresa_id]

    resueltos = await tasks_integrations.sondear_empresa(recursos, empresa_id, "ventana-1")

    assert resueltos == 1
    listado = await cliente.get("/integraciones", headers=_auth(token))
    assert _tarjeta(listado.json(), "WHATSAPP")["estado"] == "CONECTADO"


@requiere_redis
@pytest.mark.asyncio
async def test_una_redelivery_de_la_tarea_no_repite_nada(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """Caso 23 contra Redis real. La cola sólo puede prometer at-least-once."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)
    await _responde_meta(engine_dueno, "APPROVED")
    ventana = f"ventana-{uuid4()}"

    primera = await tasks_integrations.sondear_empresa(recursos, empresa_id, ventana)
    segunda = await tasks_integrations.sondear_empresa(recursos, empresa_id, ventana)

    assert primera == 1
    assert segunda == 0  # la clave ya estaba tomada: no se volvió a preguntar ni a avisar
    async with engine_dueno.begin() as conexion:
        filas = await conexion.execute(
            text("SELECT count(*) FROM registro_de_auditoria WHERE modulo = 'integrations'")
        )
        assert filas.scalar_one() == 2  # la conexión y la aprobación, una vez cada una


@requiere_redis
@pytest.mark.asyncio
async def test_el_barrido_no_encuentra_nada_cuando_no_hay_pendientes(
    cliente: httpx.AsyncClient, recursos: Recursos
) -> None:
    await _registrar(cliente, "ana@empresa.com")

    assert await tasks_integrations.sondear_pendientes(recursos) == 0


@requiere_redis
@pytest.mark.asyncio
async def test_la_tarea_resuelve_los_destinatarios_del_aviso_desde_identity(
    cliente: httpx.AsyncClient, recursos: Recursos, engine_dueno: AsyncEngine
) -> None:
    """Decisión D-c: quiénes son los administradores lo sabe `identity`, y quien lo
    pregunta es la tarea —composition root—, nunca el contexto `integrations`."""
    token = await _registrar(cliente, "ana@empresa.com")
    await _conectar_whatsapp(cliente, token)
    empresa_id = _empresa_de(token)
    await _responde_meta(engine_dueno, "DECLINED")

    avisos: list[Any] = []

    class AvisoEspia:
        async def avisar(self, aviso: Any) -> None:
            avisos.append(aviso)

    with mock.patch.object(tasks_integrations, "crear_aviso", return_value=AvisoEspia()):
        await tasks_integrations.sondear_empresa(recursos, empresa_id, f"ventana-{uuid4()}")

    assert len(avisos) == 1
    assert avisos[0].destinatarios == ("ana@empresa.com",)
    assert avisos[0].estado is EstadoDeConexion.NO_CONECTADO
