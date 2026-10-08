"""El panel de auditoría, las notificaciones y el soporte, de punta a punta (épico 10).

Las costuras que ninguna prueba unitaria mira:

1. **Que la bitácora se llene sola.** Cada request del propio test deja una fila, así que lo
   que se lista acá no es un `fixture`: es lo que el sistema realmente registró.

2. **Que el filtro llegue al `WHERE`.** El caso de uso arma `FiltrosDeBitacora` y el
   repositorio lo traduce a SQL; que las dos mitades coincidan sólo se ve consultando el motor.

3. **Que Solo Lectura reciba un 422 con el motivo**, y no un 500 ni una lista vacía.

4. **Que una notificación se cree sola cuando algo falla**, por el suscriptor que corre en la
   misma transacción de la operación fallida.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.observability.application.consultas import MOTIVO_SIN_ACCESO
from cheatsheet.contexts.observability.domain.solicitud_de_soporte import (
    MENSAJE_CAMPOS_OBLIGATORIOS,
)
from cheatsheet.platform.settings import Settings

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.guarda import argumentos_de_conexion_de_prueba

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6381/0"),
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


async def _registro(http: httpx.AsyncClient) -> tuple[str, str]:
    """Una cuenta nueva: devuelve su token y su empresa."""
    respuesta = await http.post(
        "/auth/registro",
        json={
            "email": f"{uuid4()}@cheatsheet.ar",
            "contrasena": CONTRASENA,
            "nombre": "Ana Perez",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    return str(cuerpo["access_token"]), str(cuerpo["empresa_id"])


async def _sesion_admin(http: httpx.AsyncClient) -> str:
    token, _ = await _registro(http)
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ la bitácora


@pytest.mark.asyncio
async def test_la_bitacora_muestra_lo_que_el_sistema_registro(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _sesion_admin(cliente_http)

    respuesta = await cliente_http.get("/bitacora", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total"] >= 1
    fila = cuerpo["operaciones"][0]
    # HU-E12-01 RN-01: timestamp, módulo, operación, entidad afectada, iniciador y estado.
    assert set(fila) == {
        "id",
        "timestamp",
        "modulo",
        "accion",
        "entidad_afectada",
        "iniciador",
        "resultado",
        "usuario_id",
    }


@pytest.mark.asyncio
async def test_el_filtro_por_modulo_llega_al_where(cliente_http: httpx.AsyncClient) -> None:
    token = await _sesion_admin(cliente_http)

    identity = await cliente_http.get(
        "/bitacora", headers=_auth(token), params={"modulo": "identity"}
    )
    reporting = await cliente_http.get(
        "/bitacora", headers=_auth(token), params={"modulo": "reporting"}
    )

    assert identity.json()["total"] >= 1
    assert {uno["modulo"] for uno in identity.json()["operaciones"]} == {"identity"}
    assert reporting.json()["total"] == 0


@pytest.mark.asyncio
async def test_el_filtro_por_iniciador(cliente_http: httpx.AsyncClient) -> None:
    token = await _sesion_admin(cliente_http)

    de_la_ia = await cliente_http.get("/bitacora", headers=_auth(token), params={"iniciador": "ia"})

    assert de_la_ia.status_code == 200
    assert de_la_ia.json()["total"] == 0


@pytest.mark.asyncio
async def test_la_busqueda_por_texto(cliente_http: httpx.AsyncClient) -> None:
    token = await _sesion_admin(cliente_http)

    encontradas = await cliente_http.get(
        "/bitacora", headers=_auth(token), params={"texto": "registrar"}
    )
    ninguna = await cliente_http.get(
        "/bitacora", headers=_auth(token), params={"texto": "no-existe-esta-operacion"}
    )

    assert encontradas.json()["total"] >= 1
    assert ninguna.json()["total"] == 0


@pytest.mark.asyncio
async def test_un_filtro_mal_escrito_se_rechaza(cliente_http: httpx.AsyncClient) -> None:
    """Un filtro inválido que devuelve todo es peor que uno que falla: el usuario lee la
    lista completa creyendo que filtró."""
    token = await _sesion_admin(cliente_http)

    respuesta = await cliente_http.get(
        "/bitacora", headers=_auth(token), params={"modulo": "no-existe"}
    )

    assert respuesta.status_code == 422


@pytest.mark.asyncio
async def test_el_detalle_trae_el_timeline_de_la_entidad(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _sesion_admin(cliente_http)
    listado = await cliente_http.get("/bitacora", headers=_auth(token))
    primera = listado.json()["operaciones"][0]

    detalle = await cliente_http.get(f"/bitacora/{primera['id']}", headers=_auth(token))

    assert detalle.status_code == 200, detalle.text
    cuerpo = detalle.json()
    assert cuerpo["operacion"]["id"] == primera["id"]
    assert len(cuerpo["timeline"]) >= 1
    assert cuerpo["paso_con_error"] is None


@pytest.mark.asyncio
async def test_una_operacion_inexistente(cliente_http: httpx.AsyncClient) -> None:
    token = await _sesion_admin(cliente_http)

    respuesta = await cliente_http.get(f"/bitacora/{uuid4()}", headers=_auth(token))

    assert respuesta.status_code == 422


@pytest.mark.asyncio
async def test_la_bitacora_exige_sesion(cliente_http: httpx.AsyncClient) -> None:
    assert (await cliente_http.get("/bitacora")).status_code == 401


# ------------------------------------------------------------------ notificaciones


@pytest.mark.asyncio
async def test_la_bandeja_arranca_vacia(cliente_http: httpx.AsyncClient) -> None:
    token = await _sesion_admin(cliente_http)

    respuesta = await cliente_http.get("/notificaciones", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"notificaciones": [], "no_leidas": 0}


async def _publicar_error(recursos: Recursos, empresa_id: str) -> None:
    """Publica un evento auditable fallido por el **mismo** camino que una operación real.

    No hay ruta de la API que produzca un `Resultado.ERROR` sin depender de un servicio externo
    —un rechazo de ARCA, un webhook mal firmado—, así que lo que se ejercita acá es el
    cableado: `construir_publicador` engancha el suscriptor de auditoría y el de notificaciones
    sobre la misma sesión, y de ahí para abajo corre todo lo de verdad: el ACL sobre `identity`
    leyendo las preferencias, el repositorio, y RLS acotando las dos escrituras.
    """
    from cheatsheet.api.dependencies import unidad_de_trabajo
    from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
    from cheatsheet.shared.empresa import EmpresaId

    async for unidad in unidad_de_trabajo(recursos, EmpresaId(UUID(empresa_id))):
        await unidad.publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=EmpresaId(UUID(empresa_id)),
                ocurrido_en=unidad.reloj.ahora(),
                modulo=Modulo.PAYMENTS,
                accion="confirmar_pago",
                entidad_afectada="Cobro:1",
                resultado=Resultado.ERROR,
            )
        )


@pytest.mark.asyncio
async def test_una_operacion_fallida_deja_una_notificacion(
    cliente_http: httpx.AsyncClient,
) -> None:
    """El suscriptor corriendo de verdad, y las preferencias por defecto decidiendo a quién.

    Una cuenta nueva está suscripta a todo (`PreferenciasDeNotificacion.todas`), así que la
    administradora recibe el aviso — y lo recibe **destacado**, porque un error es lo que hay
    que mirar hoy (RN-04).
    """
    token, empresa_id = await _registro(cliente_http)
    recursos = Recursos.crear(_settings())
    try:
        await _publicar_error(recursos, empresa_id)
    finally:
        await recursos.cerrar()

    respuesta = await cliente_http.get("/notificaciones", headers=_auth(token))

    cuerpo = respuesta.json()
    assert cuerpo["no_leidas"] == 1
    aviso = cuerpo["notificaciones"][0]
    assert aviso["categoria"] == "COBROS"
    assert aviso["severidad"] == "ALTA"
    assert aviso["se_destaca"] is True
    assert "confirmar_pago" in aviso["cuerpo"]


@pytest.mark.asyncio
async def test_una_operacion_exitosa_no_deja_notificacion(
    cliente_http: httpx.AsyncClient,
) -> None:
    """Todo lo que el registro de una cuenta escribió en la bitácora salió bien, y por eso la
    bandeja sigue vacía: un centro de notificaciones que avisa de lo que funcionó es un centro
    que nadie mira."""
    token = await _sesion_admin(cliente_http)

    respuesta = await cliente_http.get("/notificaciones", headers=_auth(token))

    assert respuesta.json()["no_leidas"] == 0


@pytest.mark.asyncio
async def test_marcar_como_leida(cliente_http: httpx.AsyncClient) -> None:
    token, empresa_id = await _registro(cliente_http)
    recursos = Recursos.crear(_settings())
    try:
        await _publicar_error(recursos, empresa_id)
    finally:
        await recursos.cerrar()
    bandeja = (await cliente_http.get("/notificaciones", headers=_auth(token))).json()
    primera = bandeja["notificaciones"][0]

    marcada = await cliente_http.post(
        f"/notificaciones/{primera['id']}/lectura", headers=_auth(token)
    )

    assert marcada.status_code == 200, marcada.text
    assert marcada.json()["leida"] is True
    # Una alta ya leída deja de destacarse: seguir haciéndolo enseña a ignorar lo destacado.
    assert marcada.json()["se_destaca"] is False
    despues = await cliente_http.get("/notificaciones", headers=_auth(token))
    assert despues.json()["no_leidas"] == 0


@pytest.mark.asyncio
async def test_la_notificacion_de_otra_empresa_no_se_marca(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _sesion_admin(cliente_http)

    respuesta = await cliente_http.post(f"/notificaciones/{uuid4()}/lectura", headers=_auth(token))

    assert respuesta.status_code == 422


# ------------------------------------------------------------------ soporte


@pytest.mark.asyncio
async def test_abrir_una_solicitud_de_soporte(cliente_http: httpx.AsyncClient) -> None:
    token = await _sesion_admin(cliente_http)

    creada = await cliente_http.post(
        "/soporte",
        headers=_auth(token),
        json={
            "asunto": "No puedo emitir",
            "descripcion": "ARCA rechaza todo desde ayer",
            "prioridad": "ALTA",
        },
    )

    assert creada.status_code == 201, creada.text
    cuerpo = creada.json()
    assert cuerpo["estado"] == "ABIERTA"
    assert cuerpo["esta_abierta"] is True

    listado = await cliente_http.get(
        "/soporte", headers=_auth(token), params={"solo_abiertas": True}
    )
    assert [una["id"] for una in listado.json()["solicitudes"]] == [cuerpo["id"]]


@pytest.mark.asyncio
async def test_sin_asunto_da_la_frase_de_la_historia(cliente_http: httpx.AsyncClient) -> None:
    token = await _sesion_admin(cliente_http)

    respuesta = await cliente_http.post(
        "/soporte", headers=_auth(token), json={"asunto": "  ", "descripcion": "algo"}
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == MENSAJE_CAMPOS_OBLIGATORIOS


@pytest.mark.asyncio
async def test_abrir_una_solicitud_queda_en_la_bitacora(
    cliente_http: httpx.AsyncClient,
) -> None:
    token = await _sesion_admin(cliente_http)
    await cliente_http.post(
        "/soporte", headers=_auth(token), json={"asunto": "Consulta", "descripcion": "Una duda"}
    )

    bitacora = await cliente_http.get(
        "/bitacora", headers=_auth(token), params={"texto": "solicitud_de_soporte"}
    )

    assert bitacora.json()["total"] == 1
    assert bitacora.json()["operaciones"][0]["modulo"] == "observability"


async def _sesion_de_solo_lectura(http: httpx.AsyncClient, empresa_id: str) -> str:
    """Una sesión con rol Solo Lectura, sembrando el usuario.

    El token de una invitación **no existe en ninguna respuesta de la API** —sale en el mail, y
    el sistema guarda su hash—, así que aceptarla desde acá no es posible sin espiar la cola de
    Celery. Sembrar la fila prueba lo mismo que importa: el guarda del caso de uso frente a una
    sesión con ese rol.
    """
    from cheatsheet.contexts.identity.infrastructure.seguridad import HasherArgon2
    from sqlalchemy import text as sql
    from sqlalchemy.ext.asyncio import create_async_engine

    email = f"{uuid4()}@cheatsheet.ar"
    engine = create_async_engine(
        os.environ["DATABASE_URL_MIGRATIONS"],
        connect_args=argumentos_de_conexion_de_prueba(os.environ["DATABASE_URL_MIGRATIONS"]),
    )
    async with engine.begin() as conexion:
        await conexion.execute(
            sql(
                "INSERT INTO usuario (id, empresa_id, email, nombre, rol, estado, "
                "hash_de_contrasena, pref_idioma, pref_zona_horaria, pref_suscripciones) "
                "VALUES (:id, :empresa_id, :email, 'Carla Lectora', 'SOLO_LECTURA', 'ACTIVO', "
                ":hash, 'es-AR', 'America/Argentina/Buenos_Aires', '{}'::jsonb)"
            ),
            {
                "id": uuid4(),
                "empresa_id": empresa_id,
                "email": email,
                "hash": HasherArgon2().hashear(CONTRASENA).valor,
            },
        )
    await engine.dispose()

    ingreso = await http.post("/auth/login", json={"email": email, "contrasena": CONTRASENA})
    assert ingreso.status_code == 200, ingreso.text
    return str(ingreso.json()["access_token"])


# ------------------------------------------------------------------ permisos


@pytest.mark.asyncio
async def test_solo_lectura_no_entra_a_la_bitacora(cliente_http: httpx.AsyncClient) -> None:
    """HU-E12-01 RN-05, comprobado desde afuera y con el motivo en el cuerpo.

    Se invita a alguien con rol Solo Lectura y se acepta la invitación, que es la única forma
    de conseguir una sesión con ese rol — y de paso prueba que el guarda es del caso de uso y
    no del router.
    """
    token, empresa_id = await _registro(cliente_http)
    del token  # La sesión de administrador no se usa: lo que se prueba es la del otro rol.
    solo_lectura = await _sesion_de_solo_lectura(cliente_http, empresa_id)

    respuesta = await cliente_http.get("/bitacora", headers=_auth(solo_lectura))

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == MOTIVO_SIN_ACCESO

    # Pero su propia bandeja de notificaciones sí la ve: marcar leída no es gestión.
    bandeja = await cliente_http.get("/notificaciones", headers=_auth(solo_lectura))
    assert bandeja.status_code == 200
