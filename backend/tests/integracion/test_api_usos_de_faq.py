"""Los usos de las FAQ por HTTP (ADR-0012): listado, detalle y el webhook repetido.

Los endpoints leen de `faq_uso`; el webhook la escribe. Sin base se saltean y corren en CI.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from sqlalchemy.exc import IntegrityError

from tests.integracion.conftest import requiere_base
from tests.integracion.test_api_bitacora import _sesion_de_solo_lectura
from tests.integracion.test_api_conversacional import (
    _auth,
    _firmado,
    _notificacion,
    _registrar,
    _salientes,
    _settings,
)

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

#: El simulado lee «cuánto sale…» como FAQ, y los embeddings por hash dan similitud 1 con el
#: mismo texto: una FAQ con esta pregunta es la que el agente encuentra.
PREGUNTA = "hola, cuánto sale un corte"


@pytest_asyncio.fixture
async def cliente_http(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as http:
        yield http
    await recursos.cerrar()


async def _crear_faq(http: httpx.AsyncClient, token: str) -> dict[str, object]:
    creada = await http.post(
        "/faqs", headers=_auth(token), json={"pregunta": PREGUNTA, "respuesta": "Sale $8000."}
    )
    assert creada.status_code == 201, creada.text
    return dict(creada.json())


async def _preguntar(http: httpx.AsyncClient, empresa_id: str, externo_id: str) -> int:
    crudo = _notificacion(PREGUNTA, externo_id=externo_id)
    respuesta = await http.post(
        f"/webhooks/whatsapp/{empresa_id}", content=crudo, headers=_firmado(crudo)
    )
    return respuesta.status_code


async def _faqs(http: httpx.AsyncClient, token: str) -> list[dict[str, object]]:
    return list((await http.get("/faqs", headers=_auth(token))).json()["faqs"])


class TestListado:
    async def test_el_alta_y_el_listado_traen_los_tres_conteos_y_no_traen_usos(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        """Caso 21: primer criterio enmendado de HU-E9-04."""
        token, _ = await _registrar(cliente_http, f"usos-alta-{uuid4()}@test.local")

        creada = await _crear_faq(cliente_http, token)
        (listada,) = await _faqs(cliente_http, token)

        for faq in (creada, listada):
            assert (faq["usos_este_mes"], faq["usos_mes_anterior"], faq["usos_total"]) == (0, 0, 0)
            assert faq["editada_en"] is None
            assert "usos" not in faq

    async def test_responder_una_faq_suma_un_uso_este_mes(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token, empresa_id = await _registrar(cliente_http, f"usos-suma-{uuid4()}@test.local")
        await _crear_faq(cliente_http, token)

        assert await _preguntar(cliente_http, empresa_id, "wamid-uno") == 200

        (faq,) = await _faqs(cliente_http, token)
        assert (faq["usos_este_mes"], faq["usos_total"]) == (1, 1)

    async def test_editar_responde_con_sus_conteos_y_marca_la_edicion(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token, empresa_id = await _registrar(cliente_http, f"usos-edita-{uuid4()}@test.local")
        creada = await _crear_faq(cliente_http, token)
        await _preguntar(cliente_http, empresa_id, "wamid-edita")

        editada = await cliente_http.put(
            f"/faqs/{creada['id']}",
            headers=_auth(token),
            json={"pregunta": PREGUNTA, "respuesta": "Ahora sale $9000."},
        )

        assert editada.status_code == 200, editada.text
        assert (editada.json()["usos_este_mes"], editada.json()["usos_total"]) == (1, 1)
        assert editada.json()["editada_en"] is not None


class TestWebhookRepetido:
    async def test_el_mismo_mensaje_dos_veces_cuenta_un_uso(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        """Caso 13. Meta reintenta: 200 las dos veces y un solo uso."""
        token, empresa_id = await _registrar(cliente_http, f"usos-repetido-{uuid4()}@test.local")
        await _crear_faq(cliente_http, token)

        for _ in range(2):
            assert await _preguntar(cliente_http, empresa_id, "wamid-repetido") == 200

        (faq,) = await _faqs(cliente_http, token)
        assert faq["usos_total"] == 1

    async def test_dos_entregas_concurrentes_del_mismo_mensaje_cuentan_un_uso(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        """Caso 14. El perdedor choca con `uq_mensaje_externo_id` y no deja nada.

        En producción ese choque es un 500 y Meta reintenta (el reintento es el caso 13). El
        transporte ASGI de las pruebas no lo convierte en 500: propaga la excepción, y por eso
        se junta con `return_exceptions`.
        """
        token, empresa_id = await _registrar(cliente_http, f"usos-carrera-{uuid4()}@test.local")
        await _crear_faq(cliente_http, token)

        resultados = await asyncio.gather(
            _preguntar(cliente_http, empresa_id, "wamid-carrera"),
            _preguntar(cliente_http, empresa_id, "wamid-carrera"),
            return_exceptions=True,
        )

        # Si el primero confirma antes de que el segundo consulte, el segundo es un repetido
        # común y también da 200: la carrera no siempre se da, el resultado es el mismo.
        choques = [uno for uno in resultados if isinstance(uno, IntegrityError)]
        assert 200 in resultados, resultados
        assert all(uno == 200 for uno in resultados if uno not in choques), resultados
        assert all("uq_mensaje_externo_id" in str(uno) for uno in choques), choques
        (faq,) = await _faqs(cliente_http, token)
        assert faq["usos_total"] == 1
        assert len(await _salientes(cliente_http, token)) == 1


class TestDetalle:
    async def test_una_faq_nunca_editada_dice_que_no_hay_con_que_comparar(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token, _ = await _registrar(cliente_http, f"usos-detalle-{uuid4()}@test.local")
        creada = await _crear_faq(cliente_http, token)

        detalle = await cliente_http.get(f"/faqs/{creada['id']}/uso", headers=_auth(token))

        assert detalle.status_code == 200, detalle.text
        cuerpo = detalle.json()
        assert cuerpo["comparacion"] is None
        assert cuerpo["motivo_sin_comparacion"] == "SIN_EDICIONES"
        conteos = (cuerpo["usos_este_mes"], cuerpo["usos_mes_anterior"], cuerpo["usos_total"])
        assert conteos == (0, 0, 0)

    async def test_una_faq_inexistente_se_rechaza_como_las_demas_rutas_de_faq(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token, _ = await _registrar(cliente_http, f"usos-inexistente-{uuid4()}@test.local")

        detalle = await cliente_http.get(f"/faqs/{uuid4()}/uso", headers=_auth(token))

        # Como PUT y DELETE: `FAQInexistente` es una `EntradaInvalida` (422), no un 404.
        assert detalle.status_code == 422

    async def test_un_rol_de_solo_lectura_lee_el_detalle(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        token, empresa_id = await _registrar(cliente_http, f"usos-lector-{uuid4()}@test.local")
        creada = await _crear_faq(cliente_http, token)
        lector = await _sesion_de_solo_lectura(cliente_http, empresa_id)

        detalle = await cliente_http.get(f"/faqs/{creada['id']}/uso", headers=_auth(lector))

        assert detalle.status_code == 200, detalle.text

    async def test_un_conteo_de_otra_empresa_no_se_ve(
        self, cliente_http: httpx.AsyncClient
    ) -> None:
        """Caso 15 (HTTP): la empresa B no ve los usos de la A."""
        token_a, empresa_a = await _registrar(cliente_http, f"usos-a-{uuid4()}@test.local")
        token_b, _ = await _registrar(cliente_http, f"usos-b-{uuid4()}@test.local")
        await _crear_faq(cliente_http, token_a)
        await _crear_faq(cliente_http, token_b)
        await _preguntar(cliente_http, empresa_a, "wamid-aislado")

        (de_b,) = await _faqs(cliente_http, token_b)

        assert de_b["usos_total"] == 0
