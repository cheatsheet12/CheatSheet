"""El padrón de punta a punta contra PostgreSQL real — casos 22, 23 y 24 del plan.

Lo que sólo se puede probar acá, con la aplicación entera armada:

- que el **composition root** conecte de verdad los dos contextos: `identity` pidiendo
  al padrón de `integrations` sin que ninguno importe al otro;
- que una empresa sin ARCA reciba «no disponible» en vez de un error, que es el estado
  normal apenas termina el onboarding;
- que conectar ARCA devuelva el aviso fiscal en la misma respuesta;
- que la empresa A no consulte el padrón con la credencial de la B.

ARCA sigue simulada. El simulado reserva prefijos de CUIT para los dos desenlaces
incómodos —uno que no existe y uno dado de baja—, así que el camino que bloquea se
demuestra sin tocar la red.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator
from dataclasses import replace

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.identity.application.padron import EstadoDeConsulta
from cheatsheet.platform.settings import Settings

from tests.conftest import settings_de_prueba
from tests.contexts.integrations.conftest_arca import bundle
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"

#: Estructuralmente válido — dígito verificador incluido —, porque `CUIT` lo exige antes
#: de que ARCA llegue a opinar. El prefijo 30 hace que el simulado lo trate como empresa.
CUIT_DE_LA_EMPRESA = "30712345671"
#: Reservado por el simulado: cualquier CUIT con ese prefijo responde «no existe». Es lo
#: que permite demostrar el camino que bloquea sin tocar la red.
CUIT_INEXISTENTE = "20000000001"
#: Otro CUIT válido, distinto del que trae el certificado.
CUIT_AJENO = "27123456780"


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest_asyncio.fixture
async def cliente(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    recursos = Recursos.crear(_settings())
    app = create_app(recursos.settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as abierto:
        yield abierto
    await recursos.cerrar()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _registrar(cliente: httpx.AsyncClient, email: str) -> str:
    respuesta = await cliente.post(
        "/auth/registro",
        json={"email": email, "contrasena": CONTRASENA, "nombre": "Ana Perez"},
    )
    assert respuesta.status_code == 201, respuesta.text
    return str(respuesta.json()["access_token"])


async def _completar_empresa(
    cliente: httpx.AsyncClient, token: str, *, cuit: str = CUIT_DE_LA_EMPRESA
) -> httpx.Response:
    return await cliente.put(
        "/auth/empresa",
        headers=_auth(token),
        json={
            "razon_social": "Panaderia Dona Rosa",
            "cuit": cuit,
            "condicion_iva": "RESPONSABLE_INSCRIPTO",
            "nombre_responsable": "Rosa Diaz",
            "email_contacto": "rosa@panaderia.com",
        },
    )


async def _conectar_arca(cliente: httpx.AsyncClient, token: str) -> httpx.Response:
    return await cliente.put(
        "/integraciones/ARCA/conexion",
        headers=_auth(token),
        json={
            "contenido": base64.b64encode(bundle(cuit=CUIT_DE_LA_EMPRESA)).decode(),
            "parametros": {},
        },
    )


async def _consultar(cliente: httpx.AsyncClient, token: str, cuit: str) -> httpx.Response:
    return await cliente.post("/auth/empresa/padron", headers=_auth(token), json={"cuit": cuit})


@pytest.mark.asyncio
async def test_sin_arca_conectada_la_consulta_responde_no_disponible(
    cliente: httpx.AsyncClient,
) -> None:
    """El estado normal recién salido del onboarding. **No** es un error.

    Es la mitad del hueco que esta unidad declara: en el paso 2 no hay certificado, así
    que no hay a quién preguntarle, y el formulario tiene que poder decirlo sin bloquear.
    """
    token = await _registrar(cliente, "sin-arca@empresa.com")
    await _completar_empresa(cliente, token)

    respuesta = await _consultar(cliente, token, CUIT_DE_LA_EMPRESA)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == EstadoDeConsulta.NO_DISPONIBLE
    assert respuesta.json()["datos"] is None


@pytest.mark.asyncio
async def test_con_arca_conectada_la_consulta_trae_los_datos(cliente: httpx.AsyncClient) -> None:
    """Caso 24 por el camino feliz: los dos contextos unidos en el composition root."""
    token = await _registrar(cliente, "con-arca@empresa.com")
    await _completar_empresa(cliente, token)
    assert (await _conectar_arca(cliente, token)).status_code == 200

    respuesta = await _consultar(cliente, token, CUIT_DE_LA_EMPRESA)

    cuerpo = respuesta.json()
    assert cuerpo["estado"] == EstadoDeConsulta.ENCONTRADO
    assert cuerpo["datos"]["razon_social"]
    assert cuerpo["datos"]["condicion_iva"] == "RESPONSABLE_INSCRIPTO"


@pytest.mark.asyncio
async def test_un_cuit_inexistente_bloquea_el_guardado(cliente: httpx.AsyncClient) -> None:
    """Caso 23. RN-01, aplicada donde sí se puede: con ARCA ya conectada."""
    token = await _registrar(cliente, "bloqueo@empresa.com")
    await _completar_empresa(cliente, token)
    assert (await _conectar_arca(cliente, token)).status_code == 200

    respuesta = await _completar_empresa(cliente, token, cuit=CUIT_INEXISTENTE)

    assert respuesta.status_code == 422, respuesta.text
    assert "padron" in respuesta.text.lower()

    # Y lo que ya estaba guardado sigue como estaba: no se pisó nada.
    actual = await cliente.get("/auth/empresa", headers=_auth(token))
    assert actual.json()["cuit"] == CUIT_DE_LA_EMPRESA


@pytest.mark.asyncio
async def test_conectar_arca_con_un_certificado_de_otro_cuit_devuelve_el_aviso(
    cliente: httpx.AsyncClient,
) -> None:
    """Caso 24. El hallazgo viaja en la misma respuesta que el Administrador está mirando."""
    token = await _registrar(cliente, "ajeno@empresa.com")
    await _completar_empresa(cliente, token, cuit=CUIT_AJENO)

    respuesta = await _conectar_arca(cliente, token)

    assert respuesta.status_code == 200, respuesta.text
    aviso = respuesta.json()["aviso_fiscal"]
    assert aviso is not None
    assert "otro CUIT" in aviso


@pytest.mark.asyncio
async def test_conectar_arca_con_el_certificado_correcto_no_avisa_nada(
    cliente: httpx.AsyncClient,
) -> None:
    token = await _registrar(cliente, "coincide@empresa.com")
    await _completar_empresa(cliente, token)

    respuesta = await _conectar_arca(cliente, token)

    assert respuesta.json()["aviso_fiscal"] is None


@pytest.mark.asyncio
async def test_la_empresa_a_no_consulta_con_la_credencial_de_la_b(
    cliente: httpx.AsyncClient,
) -> None:
    """Caso 22. Row-Level Security es del motor: no hay doble que lo pruebe."""
    token_a = await _registrar(cliente, "empresa-a@test.com")
    await _completar_empresa(cliente, token_a)
    assert (await _conectar_arca(cliente, token_a)).status_code == 200

    token_b = await _registrar(cliente, "empresa-b@test.com")
    await _completar_empresa(cliente, token_b, cuit=CUIT_AJENO)

    respuesta = await _consultar(cliente, token_b, CUIT_AJENO)

    assert respuesta.json()["estado"] == EstadoDeConsulta.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_la_lectura_de_la_empresa_devuelve_los_datos_para_editar(
    cliente: httpx.AsyncClient,
) -> None:
    """Caso 27 del lado del API: la pantalla de edición no puede mostrar lo que no recibe."""
    token = await _registrar(cliente, "lectura@empresa.com")
    await _completar_empresa(cliente, token)

    cuerpo = (await cliente.get("/auth/empresa", headers=_auth(token))).json()

    assert cuerpo["cuit"] == CUIT_DE_LA_EMPRESA
    assert cuerpo["condicion_iva"] == "RESPONSABLE_INSCRIPTO"
    assert cuerpo["nombre_responsable"] == "Rosa Diaz"
    assert cuerpo["email_contacto"] == "rosa@panaderia.com"
