"""`MensajeriaWhatsApp` y `SinCanal`: el cliente real de la Cloud API, sin red (U5, H2).

Todo corre sobre `httpx.MockTransport` y con un `esperar` falso: **ningún test resuelve
`graph.facebook.com` ni duerme**. Lo que se afirma es la clasificación de errores (por
`error.code` primero, por status cuando no hay código), cuántos `POST` salen en cada caso y que
el log no lleve datos personales.
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
    MensajeriaNoDisponible,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaWhatsApp,
    SinCanal,
)
from structlog.testing import capture_logs

pytestmark = pytest.mark.asyncio

TELEFONO = "5491112345678"
TEXTO = "Hola Ana, tu cobro de Corte vence hoy"
CONFIG = ConfiguracionDeMensajeria(
    token="fake-token-for-tests",
    phone_number_id="1234567890",
    graph_url="https://graph.test",
    graph_version="v21.0",
    timeout_segundos=5.0,
)


class Esperas:
    """Un `esperar` falso: anota los segundos y no duerme."""

    def __init__(self) -> None:
        self.segundos: list[float] = []

    async def __call__(self, segundos: float) -> None:
        self.segundos.append(segundos)


class Servidor:
    """Cuenta los `POST` y contesta con lo que le toque, en orden (el último se repite)."""

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


def _error(estado: int, codigo: int | None = None, **extra: object) -> httpx.Response:
    cuerpo: dict[str, object] = {"message": "detalle con 5491112345678", **extra}
    if codigo is not None:
        cuerpo["code"] = codigo
    return httpx.Response(estado, json={"error": cuerpo})


async def test_un_envio_exitoso_devuelve_el_wamid_y_manda_el_cuerpo_esperado() -> None:
    servidor = Servidor(_ok("wamid.123"))
    esperas = Esperas()

    wamid = await _canal(servidor, esperas).enviar(telefono=TELEFONO, texto=TEXTO)

    assert wamid == "wamid.123"
    assert len(servidor.pedidos) == 1
    pedido = servidor.pedidos[0]
    assert str(pedido.url) == "https://graph.test/v21.0/1234567890/messages"
    assert pedido.headers["authorization"] == "Bearer fake-token-for-tests"
    assert json.loads(pedido.read()) == {
        "messaging_product": "whatsapp",
        "to": TELEFONO,
        "type": "text",
        "text": {"body": TEXTO},
    }
    assert esperas.segundos == []


# --- Caso 4: sin conexión ---------------------------------------------------------------


@pytest.mark.parametrize(
    "falla",
    [
        httpx.ConnectError("sin conexión"),
        httpx.ConnectTimeout("sin conexión"),
        httpx.PoolTimeout("pool lleno"),
    ],
)
async def test_sin_conexion_reintenta_tres_veces_y_levanta_saturada(falla: Exception) -> None:
    servidor = Servidor(falla)
    esperas = Esperas()

    with pytest.raises(MensajeriaSaturada) as salida:
        await _canal(servidor, esperas).enviar(telefono=TELEFONO, texto=TEXTO)

    assert len(servidor.pedidos) == 3
    assert esperas.segundos == [1.0, 2.0]
    assert isinstance(salida.value, MensajeriaNoDisponible)


# --- Caso 5: el pedido pudo haber llegado ------------------------------------------------


@pytest.mark.parametrize(
    "falla",
    [
        httpx.ReadTimeout("lento"),
        httpx.WriteTimeout("lento"),
        httpx.ReadError("cortada"),
        httpx.RemoteProtocolError("cortada a mitad de respuesta"),
    ],
)
async def test_un_fallo_que_pudo_haber_llegado_no_se_reintenta(falla: Exception) -> None:
    servidor = Servidor(falla)
    esperas = Esperas()

    with pytest.raises(EnvioIncierto):
        await _canal(servidor, esperas).enviar(telefono=TELEFONO, texto=TEXTO)

    assert len(servidor.pedidos) == 1
    assert esperas.segundos == []


# --- Caso 6: espera exponencial -----------------------------------------------------------


async def test_503_503_200_devuelve_el_wamid_y_espera_uno_y_dos_segundos() -> None:
    servidor = Servidor(httpx.Response(503), httpx.Response(503), _ok("wamid.TRAS-REINTENTOS"))
    esperas = Esperas()

    wamid = await _canal(servidor, esperas).enviar(telefono=TELEFONO, texto=TEXTO)

    assert wamid == "wamid.TRAS-REINTENTOS"
    assert len(servidor.pedidos) == 3
    assert esperas.segundos == [1.0, 2.0]


# --- Caso 7 y 8: transitorios por código y por status -------------------------------------


async def test_un_429_sin_codigo_se_reintenta() -> None:
    servidor = Servidor(httpx.Response(429), _ok())
    esperas = Esperas()

    assert await _canal(servidor, esperas).enviar(telefono=TELEFONO, texto=TEXTO) == "wamid.OK"

    assert len(servidor.pedidos) == 2
    assert esperas.segundos == [1.0]


async def test_un_400_con_codigo_de_throttling_se_reintenta() -> None:
    servidor = Servidor(_error(400, 130429), _ok())
    esperas = Esperas()

    assert await _canal(servidor, esperas).enviar(telefono=TELEFONO, texto=TEXTO) == "wamid.OK"

    assert len(servidor.pedidos) == 2


@pytest.mark.parametrize("codigo", [4, 80007, 130429, 131056, 131000, 131016])
async def test_los_codigos_transitorios_se_reintentan_y_agotados_son_saturada(codigo: int) -> None:
    servidor = Servidor(_error(400, codigo))
    esperas = Esperas()

    with pytest.raises(MensajeriaSaturada) as salida:
        await _canal(servidor, esperas).enviar(telefono=TELEFONO, texto=TEXTO)

    assert len(servidor.pedidos) == 3
    assert salida.value.codigo == codigo


# --- Caso 9: permanentes ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estado", "codigo"),
    [
        (400, 131047),
        (400, 131026),
        (400, 132001),
        (401, 190),
        (401, None),
        (403, None),
        (400, 0),
        (400, 368),
    ],
)
async def test_los_permanentes_hacen_un_solo_post_y_levantan_rechazado(
    estado: int, codigo: int | None
) -> None:
    servidor = Servidor(_error(estado, codigo))
    esperas = Esperas()

    with pytest.raises(MensajeRechazado) as salida:
        await _canal(servidor, esperas).enviar(telefono=TELEFONO, texto=TEXTO)

    assert len(servidor.pedidos) == 1
    assert salida.value.codigo == codigo
    assert esperas.segundos == []


async def test_el_codigo_manda_sobre_el_status() -> None:
    # Un 500 que trae un código permanente no se reintenta: manda el código.
    servidor = Servidor(_error(500, 131047))

    with pytest.raises(MensajeRechazado):
        await _canal(servidor, Esperas()).enviar(telefono=TELEFONO, texto=TEXTO)

    assert len(servidor.pedidos) == 1


# --- Caso 10: cuerpos ilegibles -----------------------------------------------------------


async def test_un_4xx_con_cuerpo_ilegible_es_permanente_sin_codigo() -> None:
    servidor = Servidor(httpx.Response(400, content=b"<html>no es json</html>"))

    with pytest.raises(MensajeRechazado) as salida:
        await _canal(servidor, Esperas()).enviar(telefono=TELEFONO, texto=TEXTO)

    assert len(servidor.pedidos) == 1
    assert salida.value.codigo is None


async def test_un_5xx_sin_cuerpo_es_transitorio() -> None:
    servidor = Servidor(httpx.Response(502))

    with pytest.raises(MensajeriaSaturada) as salida:
        await _canal(servidor, Esperas()).enviar(telefono=TELEFONO, texto=TEXTO)

    assert len(servidor.pedidos) == 3
    assert salida.value.codigo is None


async def test_un_cuerpo_json_que_no_es_un_objeto_tampoco_rompe_la_clasificacion() -> None:
    servidor = Servidor(httpx.Response(400, json=["raro"]))

    with pytest.raises(MensajeRechazado) as salida:
        await _canal(servidor, Esperas()).enviar(telefono=TELEFONO, texto=TEXTO)

    assert salida.value.codigo is None


# --- Caso 11: el log no lleva datos personales --------------------------------------------


async def test_el_log_de_un_rechazo_trae_estado_codigo_y_traza_y_nada_personal() -> None:
    servidor = Servidor(
        _error(
            400,
            131047,
            error_data={"details": "el 5491112345678 no recibe"},
            fbtrace_id="AbC123",
        )
    )

    with capture_logs() as registros, pytest.raises(MensajeRechazado):
        await _canal(servidor, Esperas()).enviar(telefono=TELEFONO, texto=TEXTO)

    rechazos = [r for r in registros if r["event"] == "whatsapp_rechazo_el_mensaje"]
    assert len(rechazos) == 1
    assert rechazos[0]["estado"] == 400
    assert rechazos[0]["codigo"] == 131047
    assert rechazos[0]["fbtrace_id"] == "AbC123"
    volcado = repr(registros)
    assert TELEFONO not in volcado
    assert TEXTO not in volcado
    assert "no recibe" not in volcado
    assert "detalle con" not in volcado


async def test_el_mensaje_de_la_excepcion_tampoco_lleva_datos_personales() -> None:
    servidor = Servidor(_error(400, 131026, error_data={"details": TELEFONO}))

    with pytest.raises(MensajeRechazado) as salida:
        await _canal(servidor, Esperas()).enviar(telefono=TELEFONO, texto=TEXTO)

    assert TELEFONO not in str(salida.value)
    assert "131026" in str(salida.value)


# --- Caso 12: SinCanal --------------------------------------------------------------------


async def test_sin_canal_levanta_canal_no_conectado_y_no_toca_la_red() -> None:
    # `SinCanal` no recibe transporte ni configuración: no tiene con qué salir a la red.
    with pytest.raises(CanalNoConectado) as salida:
        await SinCanal().enviar(telefono=TELEFONO, texto=TEXTO)

    assert isinstance(salida.value, MensajeriaNoDisponible)
    assert TELEFONO not in str(salida.value)
