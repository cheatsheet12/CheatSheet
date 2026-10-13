"""`enviar_plantilla` de los tres canales: la plantilla aprobada sale por la Cloud API (U6).

Mismo patrón que `test_canal.py`: `httpx.MockTransport` y un `esperar` falso, así que **ningún test
resuelve `graph.facebook.com` ni duerme**. El bucle de reintento es el mismo que el de `enviar`
(`canal_http.py`): acá se prueba la forma del `POST` de plantilla, un caso por clase de error y los
códigos nuevos de plantilla.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.infrastructure import canal_http
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaSimulada,
    MensajeriaWhatsApp,
    SinCanal,
)
from cheatsheet.platform.settings import Entorno
from structlog.testing import capture_logs

from tests.logs import logger_nuevo

pytestmark = pytest.mark.asyncio

TELEFONO = "5491112345678"
CONFIG = ConfiguracionDeMensajeria(
    token="fake-token-for-tests",
    phone_number_id="1234567890",
    graph_url="https://graph.test",
    graph_version="v21.0",
    timeout_segundos=5.0,
)
PARAMETROS = {"nombre": "Ana", "concepto": "Cuota de octubre"}


class Esperas:
    def __init__(self) -> None:
        self.segundos: list[float] = []

    async def __call__(self, segundos: float) -> None:
        self.segundos.append(segundos)


class Servidor:
    def __init__(self, *respuestas: httpx.Response | Exception) -> None:
        self._respuestas = list(respuestas)
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        indice = min(len(self.pedidos), len(self._respuestas)) - 1
        respuesta = self._respuestas[indice]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


def _canal(
    servidor: Callable[[httpx.Request], httpx.Response], esperas: Esperas
) -> MensajeriaWhatsApp:
    return MensajeriaWhatsApp(CONFIG, transporte=httpx.MockTransport(servidor), esperar=esperas)


def _ok(wamid: str = "wamid.OK") -> httpx.Response:
    return httpx.Response(200, json={"messages": [{"id": wamid}]})


def _error(estado: int, codigo: int) -> httpx.Response:
    return httpx.Response(
        estado, json={"error": {"message": f"detalle con {TELEFONO}", "code": codigo}}
    )


async def _enviar(canal: MensajeriaWhatsApp) -> str:
    return await canal.enviar_plantilla(
        telefono=TELEFONO, nombre="recordatorio_de_cobro", idioma="es_AR", parametros=PARAMETROS
    )


async def test_la_plantilla_sale_como_type_template_con_parametros_con_nombre() -> None:
    servidor = Servidor(_ok("wamid.777"))

    wamid = await _enviar(_canal(servidor, Esperas()))

    assert wamid == "wamid.777"
    assert len(servidor.pedidos) == 1
    pedido = servidor.pedidos[0]
    assert str(pedido.url) == "https://graph.test/v21.0/1234567890/messages"
    assert pedido.headers["authorization"] == "Bearer fake-token-for-tests"
    assert json.loads(pedido.read()) == {
        "messaging_product": "whatsapp",
        "to": TELEFONO,
        "type": "template",
        "template": {
            "name": "recordatorio_de_cobro",
            "language": {"code": "es_AR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "parameter_name": "nombre", "text": "Ana"},
                        {
                            "type": "text",
                            "parameter_name": "concepto",
                            "text": "Cuota de octubre",
                        },
                    ],
                }
            ],
        },
    }


async def test_una_plantilla_sin_parametros_no_manda_componentes() -> None:
    servidor = Servidor(_ok())

    await _canal(servidor, Esperas()).enviar_plantilla(
        telefono=TELEFONO, nombre="sin_variables", idioma="es_AR", parametros={}
    )

    cuerpo = json.loads(servidor.pedidos[0].read())
    assert "components" not in cuerpo["template"]


@pytest.mark.parametrize("codigo", [132000, 132012, 132015, 132016, 132001])
async def test_los_codigos_de_plantilla_son_permanentes_con_un_solo_post(codigo: int) -> None:
    servidor = Servidor(_error(400, codigo))
    esperas = Esperas()

    with pytest.raises(MensajeRechazado) as salida:
        await _enviar(_canal(servidor, esperas))

    assert len(servidor.pedidos) == 1
    assert esperas.segundos == []
    assert salida.value.codigo == codigo


async def test_un_503_tres_veces_levanta_saturada_con_espera_entre_intentos() -> None:
    servidor = Servidor(httpx.Response(503))
    esperas = Esperas()

    with pytest.raises(MensajeriaSaturada):
        await _enviar(_canal(servidor, esperas))

    assert len(servidor.pedidos) == 3
    assert esperas.segundos == [1.0, 2.0]


async def test_un_timeout_de_lectura_es_incierto_y_no_se_reintenta() -> None:
    servidor = Servidor(httpx.ReadTimeout("lento"))
    esperas = Esperas()

    with pytest.raises(EnvioIncierto):
        await _enviar(_canal(servidor, esperas))

    assert len(servidor.pedidos) == 1
    assert esperas.segundos == []


async def test_el_log_de_una_plantilla_rechazada_no_lleva_datos_personales(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger_nuevo(monkeypatch, canal_http)
    servidor = Servidor(_error(400, 132000))

    with capture_logs() as registros, pytest.raises(MensajeRechazado):
        await _enviar(_canal(servidor, Esperas()))

    volcado = json.dumps(registros, default=str)
    assert registros  # el test no pasa por no haber registrado nada
    assert TELEFONO not in volcado
    assert "Ana" not in volcado
    assert "Cuota de octubre" not in volcado
    assert "fake-token-for-tests" not in volcado


async def test_el_simulado_acepta_la_plantilla_sin_red_y_devuelve_un_id_unico() -> None:
    simulado = MensajeriaSimulada(Entorno.LOCAL)

    uno = await simulado.enviar_plantilla(
        telefono=TELEFONO, nombre="x", idioma="es_AR", parametros=PARAMETROS
    )
    otro = await simulado.enviar_plantilla(
        telefono=TELEFONO, nombre="x", idioma="es_AR", parametros=PARAMETROS
    )

    assert uno.startswith("simulado-")
    assert uno != otro
    assert [nombre for nombre, _ in simulado.plantillas_enviadas] == ["x", "x"]


async def test_sin_canal_levanta_canal_no_conectado_para_la_plantilla() -> None:
    with pytest.raises(CanalNoConectado):
        await SinCanal().enviar_plantilla(
            telefono=TELEFONO, nombre="x", idioma="es_AR", parametros=PARAMETROS
        )
