"""El horario de atención y la política de fuera de horario, de punta a punta (casos 16, 17 y 37).

Tres costuras que ninguna prueba de capa mira:

1. **El aislamiento**: el horario de la empresa A no rige para la B (RLS sobre `regla_de_negocio`).
2. **La API**: `PUT /reglas/horario-de-atencion` con horario cortado y fechas, el rechazo del
   dominio como 422 con su mensaje y el rechazo del Operador.
3. **El webhook**: con la política de mensaje fijo y el negocio cerrado, el cliente recibe el
   mensaje fijo y su entrante queda sin intención; la empresa sin horario recibe la respuesta
   normal.

Requiere PostgreSQL (`requiere_base`): se saltea sin base y corre en la CI.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.platform.settings import Settings
from cheatsheet.workers import tasks_identity

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import CONSENTIMIENTO, VERSION_DE_PRIVACIDAD
from tests.integracion.test_api_usuarios import DespachadorEspia

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CONTRASENA = "una-contrasena-larga"
TELEFONO = "5491112345678"

MENSAJE_CIERRE = "La hora de cierre debe ser posterior a la de apertura."
MENSAJE_SUPERPUESTAS = "Las franjas de un mismo día no pueden superponerse ni tocarse."


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest.fixture
def despachador(monkeypatch: pytest.MonkeyPatch) -> DespachadorEspia:
    espia = DespachadorEspia()
    monkeypatch.setattr(tasks_identity, "_despachador", lambda _settings: espia)
    return espia


@pytest_asyncio.fixture
async def cliente_http(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as http:
        yield http
    await recursos.cerrar()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _registrar(http: httpx.AsyncClient, email: str) -> tuple[str, str]:
    """Devuelve `(token, empresa_id)`. La empresa sale del JWT, sin consultar nada."""
    respuesta = await http.post(
        "/auth/registro",
        json={
            "email": email,
            "contrasena": CONTRASENA,
            "nombre": "Ana Perez",
            "consentimiento": CONSENTIMIENTO,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    token = str(respuesta.json()["access_token"])
    carga = token.split(".")[1]
    carga += "=" * (-len(carga) % 4)
    return token, str(json.loads(base64.urlsafe_b64decode(carga))["empresa_id"])


async def _operador(
    http: httpx.AsyncClient, despachador: DespachadorEspia, token_admin: str
) -> str:
    invitacion = await http.post(
        "/usuarios/invitaciones",
        headers=_auth(token_admin),
        json={"email": "beto@empresa.com", "rol": "OPERADOR"},
    )
    assert invitacion.status_code == 201, invitacion.text
    aceptacion = await http.post(
        "/auth/invitaciones/aceptar",
        json={
            "token": despachador.tareas[0]["kwargs"]["token"],
            "nombre": "Beto Gomez",
            "contrasena": CONTRASENA,
            "version_privacidad": VERSION_DE_PRIVACIDAD,
        },
    )
    assert aceptacion.status_code == 201, aceptacion.text
    ingreso = await http.post(
        "/auth/login", json={"email": "beto@empresa.com", "contrasena": CONTRASENA}
    )
    return str(ingreso.json()["access_token"])


def _horario(politica: str = "AGENTE_RESPONDE", **cambios: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "dias": [
            {
                "dia": 0,
                "franjas": [
                    {"desde": "09:00", "hasta": "13:00"},
                    {"desde": "16:00", "hasta": "20:00"},
                ],
            },
            {"dia": 5, "franjas": [{"desde": "09:00", "hasta": "14:00"}]},
        ],
        "fechas_cerradas": ["2026-10-12"],
        "politica": politica,
    }
    cuerpo.update(cambios)
    return cuerpo


def _reglas_de_horario(listado: httpx.Response) -> list[dict[str, Any]]:
    return [uno for uno in listado.json()["reglas"] if uno["tipo"] == "HORARIO_DE_ATENCION"]


def _notificacion(texto: str, *, externo_id: str) -> bytes:
    cuerpo = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "id": externo_id,
                                    "from": TELEFONO,
                                    "timestamp": "1789000000",
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(cuerpo).encode("utf-8")


async def _escribir(http: httpx.AsyncClient, empresa_id: str, texto: str, externo_id: str) -> None:
    crudo = _notificacion(texto, externo_id=externo_id)
    secreto = (_settings().whatsapp_webhook_secret or "").encode("utf-8")
    firma = hmac.new(secreto, crudo, hashlib.sha256).hexdigest()
    respuesta = await http.post(
        f"/webhooks/whatsapp/{empresa_id}",
        content=crudo,
        headers={"x-hub-signature-256": f"sha256={firma}", "content-type": "application/json"},
    )
    assert respuesta.status_code == 200, respuesta.text


async def _mensajes(http: httpx.AsyncClient, token: str) -> list[dict[str, Any]]:
    listado = await http.get("/conversaciones", headers=_auth(token))
    [conversacion] = listado.json()["conversaciones"]
    detalle = await http.get(f"/conversaciones/{conversacion['id']}", headers=_auth(token))
    return list(detalle.json()["mensajes"])


class TestApiDelHorario:
    async def test_el_administrador_guarda_dos_franjas_y_fechas_y_el_listado_las_devuelve(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        """Caso 17."""
        token, _ = await _registrar(cliente_http, "horario-alta@test.local")

        guardada = await cliente_http.put(
            "/reglas/horario-de-atencion", headers=_auth(token), json=_horario("MENSAJE_FIJO")
        )

        assert guardada.status_code == 200, guardada.text
        [regla] = _reglas_de_horario(await cliente_http.get("/reglas", headers=_auth(token)))
        assert regla["activa"] is True
        assert regla["prioridad"] == 0
        assert regla["configuracion"]["politica"] == "MENSAJE_FIJO"
        assert regla["configuracion"]["fechas_cerradas"] == ["2026-10-12"]
        franjas = regla["configuracion"]["dias"][0]["franjas"]
        assert [uno["desde"] for uno in franjas] == ["09:00", "16:00"]

    async def test_guardar_dos_veces_reemplaza_en_vez_de_acumular(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token, _ = await _registrar(cliente_http, "horario-reemplazo@test.local")

        for politica in ("AGENTE_RESPONDE", "MENSAJE_FIJO"):
            respuesta = await cliente_http.put(
                "/reglas/horario-de-atencion", headers=_auth(token), json=_horario(politica)
            )
            assert respuesta.status_code == 200, respuesta.text

        reglas = _reglas_de_horario(await cliente_http.get("/reglas", headers=_auth(token)))
        assert [uno["configuracion"]["politica"] for uno in reglas] == ["MENSAJE_FIJO"]

    async def test_el_dominio_rechaza_con_su_mensaje(self, cliente_http: httpx.AsyncClient) -> None:
        """Caso 17: 422 con el texto del dominio."""
        token, _ = await _registrar(cliente_http, "horario-422@test.local")
        invertida = _horario(dias=[{"dia": 0, "franjas": [{"desde": "13:00", "hasta": "09:00"}]}])
        tocadas = _horario(
            dias=[
                {
                    "dia": 0,
                    "franjas": [
                        {"desde": "09:00", "hasta": "13:00"},
                        {"desde": "13:00", "hasta": "16:00"},
                    ],
                }
            ]
        )

        primera = await cliente_http.put(
            "/reglas/horario-de-atencion", headers=_auth(token), json=invertida
        )
        segunda = await cliente_http.put(
            "/reglas/horario-de-atencion", headers=_auth(token), json=tocadas
        )

        assert primera.status_code == 422
        assert MENSAJE_CIERRE in primera.text
        assert segunda.status_code == 422
        assert MENSAJE_SUPERPUESTAS in segunda.text

    async def test_un_operador_no_puede_configurarlo_pero_si_leerlo(
        self, cliente_http: httpx.AsyncClient, despachador: DespachadorEspia
    ) -> None:
        """Caso 17: el guard es el caso de uso, no la pantalla."""
        token_admin, _ = await _registrar(cliente_http, "ana@empresa.com")
        token_operador = await _operador(cliente_http, despachador, token_admin)

        rechazo = await cliente_http.put(
            "/reglas/horario-de-atencion", headers=_auth(token_operador), json=_horario()
        )

        assert (
            rechazo.status_code == 422
        )  # `EntradaInvalida(MOTIVO_SOLO_ADMIN)`, como el escalamiento
        listado = await cliente_http.get("/reglas", headers=_auth(token_operador))
        assert listado.status_code == 200
        assert _reglas_de_horario(listado) == []

    async def test_el_horario_de_una_empresa_no_se_ve_en_la_otra(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        """Caso 16: RLS sobre `regla_de_negocio`."""
        token_a, _ = await _registrar(cliente_http, "horario-a@test.local")
        token_b, _ = await _registrar(cliente_http, "horario-b@test.local")
        await cliente_http.put(
            "/reglas/horario-de-atencion", headers=_auth(token_a), json=_horario("MENSAJE_FIJO")
        )

        listado_b = await cliente_http.get("/reglas", headers=_auth(token_b))

        assert _reglas_de_horario(listado_b) == []


class TestFueraDeHorarioPorWhatsApp:
    async def test_la_empresa_con_mensaje_fijo_recibe_el_fijo_y_la_otra_la_respuesta_normal(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        """Caso 37: A (política (b), casi siempre cerrada) y B (sin horario: «siempre abierta»).

        El horario de A abre sólo los lunes de 03:00 a 03:01, así que el test no depende de la
        hora a la que corra la CI.
        """
        token_a, empresa_a = await _registrar(cliente_http, "fuera-a@test.local")
        token_b, empresa_b = await _registrar(cliente_http, "fuera-b@test.local")
        casi_siempre_cerrado = _horario(
            "MENSAJE_FIJO",
            dias=[{"dia": 0, "franjas": [{"desde": "03:00", "hasta": "03:01"}]}],
            fechas_cerradas=[],
        )
        guardada = await cliente_http.put(
            "/reglas/horario-de-atencion", headers=_auth(token_a), json=casi_siempre_cerrado
        )
        assert guardada.status_code == 200, guardada.text

        await _escribir(cliente_http, empresa_a, "hola, cuánto sale un corte", "fuera-a-1")
        await _escribir(cliente_http, empresa_b, "hola, cuánto sale un corte", "fuera-b-1")

        mensajes_a = await _mensajes(cliente_http, token_a)
        [entrante_a] = [uno for uno in mensajes_a if uno["direccion"] == "ENTRANTE"]
        salientes_a = [uno["contenido"] for uno in mensajes_a if uno["direccion"] == "SALIENTE"]
        assert entrante_a["intencion"] is None
        assert len(salientes_a) == 1
        assert "fuera del horario de atención" in salientes_a[0]

        mensajes_b = await _mensajes(cliente_http, token_b)
        [entrante_b] = [uno for uno in mensajes_b if uno["direccion"] == "ENTRANTE"]
        salientes_b = [uno["contenido"] for uno in mensajes_b if uno["direccion"] == "SALIENTE"]
        assert entrante_b["intencion"] is not None
        assert all("fuera del horario" not in texto for texto in salientes_b)
