"""`PlantillasDeMeta`: crear, editar y leer las plantillas de la WABA, sin red (U6, D-U6-7).

Todo corre sobre `httpx.MockTransport` y un `esperar` falso: **ningún test resuelve
`graph.facebook.com` ni duerme**. Lo que se afirma es la forma de cada pedido (nombre, idioma,
categoría UTILITY, parámetros con nombre y un ejemplo por variable), la paginación, que un
rechazo lleve el texto de Meta y que ningún log lo contenga.
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
from cheatsheet.contexts.conversational.infrastructure.canal_errores import (
    SUBCODIGOS_NOMBRE_EN_USO,
    leer_error,
)
from cheatsheet.contexts.conversational.infrastructure.plantillas_meta import (
    PlantillasDeMeta,
    PlantillasSimuladas,
    SinCuentaDeMeta,
)
from cheatsheet.platform.settings import Entorno
from structlog.testing import capture_logs

pytestmark = pytest.mark.asyncio

CUERPO = "Hola {{nombre}}, tu cobro de {{concepto}} vence pronto. Gracias."
EJEMPLOS = {"nombre": "Ana", "concepto": "Cuota de octubre"}


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


def _cliente(
    servidor: Callable[[httpx.Request], httpx.Response], esperas: Esperas | None = None
) -> PlantillasDeMeta:
    return PlantillasDeMeta(
        token="fake-token-for-tests",
        waba_id="999000111",
        graph_url="https://graph.test",
        graph_version="v21.0",
        timeout_segundos=5.0,
        transporte=httpx.MockTransport(servidor),
        esperar=esperas or Esperas(),
    )


def _error(estado: int, codigo: int, **extra: object) -> httpx.Response:
    return httpx.Response(estado, json={"error": {"code": codigo, **extra}})


async def test_crear_manda_nombre_idioma_categoria_utility_y_un_ejemplo_por_variable() -> None:
    servidor = Servidor(
        httpx.Response(200, json={"id": "555", "status": "PENDING", "category": "UTILITY"})
    )

    respuesta = await _cliente(servidor).crear(
        nombre="recordatorio_de_cobro", idioma="es_AR", cuerpo=CUERPO, ejemplos=EJEMPLOS
    )

    assert (respuesta.meta_plantilla_id, respuesta.estado, respuesta.categoria) == (
        "555",
        "PENDING",
        "UTILITY",
    )
    (pedido,) = servidor.pedidos
    assert pedido.method == "POST"
    assert str(pedido.url) == "https://graph.test/v21.0/999000111/message_templates"
    assert pedido.headers["authorization"] == "Bearer fake-token-for-tests"
    assert json.loads(pedido.read()) == {
        "name": "recordatorio_de_cobro",
        "language": "es_AR",
        "category": "UTILITY",
        "parameter_format": "named",
        "components": [
            {
                "type": "BODY",
                "text": CUERPO,
                "example": {
                    "body_text_named_params": [
                        {"param_name": "nombre", "example": "Ana"},
                        {"param_name": "concepto", "example": "Cuota de octubre"},
                    ]
                },
            }
        ],
    }


async def test_crear_una_plantilla_sin_variables_no_manda_ejemplos() -> None:
    servidor = Servidor(httpx.Response(200, json={"id": "1", "status": "PENDING"}))

    await _cliente(servidor).crear(
        nombre="x", idioma="es_AR", cuerpo="Hola, gracias por venir.", ejemplos={}
    )

    componente = json.loads(servidor.pedidos[0].read())["components"][0]
    assert "example" not in componente


async def test_editar_manda_los_componentes_completos_al_nodo_de_la_plantilla() -> None:
    servidor = Servidor(httpx.Response(200, json={"success": True}))

    respuesta = await _cliente(servidor).editar(
        meta_plantilla_id="555", cuerpo=CUERPO, ejemplos=EJEMPLOS
    )

    # Tras editar Meta no dice en qué estado queda (TODO 22.43): hasta que lo confirme, pendiente.
    assert (respuesta.meta_plantilla_id, respuesta.estado) == ("555", "PENDING")
    (pedido,) = servidor.pedidos
    assert str(pedido.url) == "https://graph.test/v21.0/555"
    cuerpo = json.loads(pedido.read())
    assert cuerpo["components"][0]["text"] == CUERPO
    assert "name" not in cuerpo
    assert "language" not in cuerpo


async def test_un_rechazo_lleva_el_texto_de_meta_y_el_subcodigo() -> None:
    servidor = Servidor(
        _error(
            400,
            100,
            error_subcode=2388023,
            error_user_msg="Ya existe una plantilla con ese nombre.",
            message="detalle técnico",
        )
    )

    with pytest.raises(MensajeRechazado) as salida:
        await _cliente(servidor).crear(nombre="x", idioma="es_AR", cuerpo=CUERPO, ejemplos=EJEMPLOS)

    assert salida.value.mensaje_para_el_usuario == "Ya existe una plantilla con ese nombre."
    assert salida.value.subcodigo in SUBCODIGOS_NOMBRE_EN_USO
    assert len(servidor.pedidos) == 1


async def test_el_texto_de_meta_no_aparece_en_ningun_log() -> None:
    servidor = Servidor(_error(400, 100, error_user_msg="Texto secreto de Meta"))

    with capture_logs() as registros, pytest.raises(MensajeRechazado):
        await _cliente(servidor).crear(nombre="x", idioma="es_AR", cuerpo=CUERPO, ejemplos=EJEMPLOS)

    volcado = json.dumps(registros, default=str)
    assert "Texto secreto de Meta" not in volcado
    assert "fake-token-for-tests" not in volcado
    assert "Cuota de octubre" not in volcado


async def test_un_503_tres_veces_levanta_saturada_con_espera() -> None:
    servidor = Servidor(httpx.Response(503))
    esperas = Esperas()

    with pytest.raises(MensajeriaSaturada):
        await _cliente(servidor, esperas).crear(
            nombre="x", idioma="es_AR", cuerpo=CUERPO, ejemplos=EJEMPLOS
        )

    assert len(servidor.pedidos) == 3
    assert esperas.segundos == [1.0, 2.0]


async def test_un_timeout_de_lectura_al_crear_es_incierto_con_un_solo_post() -> None:
    servidor = Servidor(httpx.ReadTimeout("lento"))

    with pytest.raises(EnvioIncierto):
        await _cliente(servidor).crear(nombre="x", idioma="es_AR", cuerpo=CUERPO, ejemplos=EJEMPLOS)

    assert len(servidor.pedidos) == 1


async def test_una_respuesta_de_creacion_sin_id_es_incierta() -> None:
    servidor = Servidor(httpx.Response(200, json={"status": "PENDING"}))

    with pytest.raises(EnvioIncierto):
        await _cliente(servidor).crear(nombre="x", idioma="es_AR", cuerpo=CUERPO, ejemplos=EJEMPLOS)


def _pagina(*ids: str, siguiente: str | None = None) -> httpx.Response:
    datos = [
        {
            "id": identificador,
            "name": f"plantilla_{identificador}",
            "language": "es_AR",
            "status": "REJECTED" if identificador == "2" else "APPROVED",
            "category": "UTILITY",
            "rejected_reason": "PROMOTIONAL" if identificador == "2" else "NONE",
            "components": [{"type": "BODY", "text": f"cuerpo {identificador}"}],
        }
        for identificador in ids
    ]
    paginacion: dict[str, object] = {"cursors": {"after": siguiente}} if siguiente else {}
    if siguiente:
        paginacion["next"] = f"https://graph.test/siguiente?after={siguiente}"
    return httpx.Response(200, json={"data": datos, "paging": paginacion})


async def test_estados_sigue_la_paginacion_y_lee_estado_motivo_y_cuerpo() -> None:
    servidor = Servidor(_pagina("1", "2", siguiente="CURSOR2"), _pagina("3"))

    estados = await _cliente(servidor).estados()

    assert [una.meta_plantilla_id for una in estados] == ["1", "2", "3"]
    rechazada = estados[1]
    assert rechazada.estado == "REJECTED"
    assert rechazada.motivo == "PROMOTIONAL"
    assert rechazada.cuerpo == "cuerpo 2"
    assert estados[0].motivo is None  # `NONE` no es un motivo
    assert (estados[0].nombre, estados[0].idioma) == ("plantilla_1", "es_AR")
    primero, segundo = servidor.pedidos
    assert primero.method == "GET"
    assert "after" not in primero.url.params
    assert segundo.url.params["after"] == "CURSOR2"
    assert "message_templates" in str(primero.url)


async def test_estados_corta_en_diez_paginas() -> None:
    servidor = Servidor(_pagina("1", siguiente="SIEMPRE"))

    await _cliente(servidor).estados()

    assert len(servidor.pedidos) == 10


async def test_estados_ignora_las_filas_con_forma_inesperada() -> None:
    servidor = Servidor(
        httpx.Response(
            200,
            json={
                "data": [
                    {"id": "1", "name": "ok", "language": "es_AR", "status": "APPROVED"},
                    {"name": "sin_id", "status": "APPROVED"},
                    "basura",
                ]
            },
        )
    )

    estados = await _cliente(servidor).estados()

    assert [una.meta_plantilla_id for una in estados] == ["1"]


async def test_un_timeout_al_leer_los_estados_es_incierto_sin_reintento() -> None:
    servidor = Servidor(httpx.ReadTimeout("lento"))

    with pytest.raises(EnvioIncierto):
        await _cliente(servidor).estados()

    assert len(servidor.pedidos) == 1


async def test_las_simuladas_aprueban_todo_sin_red() -> None:
    simuladas = PlantillasSimuladas(Entorno.LOCAL)

    creada = await simuladas.crear(nombre="x", idioma="es_AR", cuerpo=CUERPO, ejemplos=EJEMPLOS)
    editada = await simuladas.editar(meta_plantilla_id="1", cuerpo=CUERPO, ejemplos=EJEMPLOS)

    assert creada.estado == editada.estado == "APPROVED"
    assert creada.meta_plantilla_id.startswith("simulada-")
    assert await simuladas.estados() == []


async def test_las_simuladas_se_niegan_a_arrancar_en_produccion() -> None:
    with pytest.raises(RuntimeError):
        PlantillasSimuladas(Entorno.PRODUCTION)


async def test_sin_cuenta_de_meta_levanta_canal_no_conectado_en_todo() -> None:
    sin_cuenta = SinCuentaDeMeta()

    with pytest.raises(CanalNoConectado):
        await sin_cuenta.crear(nombre="x", idioma="es_AR", cuerpo=CUERPO, ejemplos=EJEMPLOS)
    with pytest.raises(CanalNoConectado):
        await sin_cuenta.editar(meta_plantilla_id="1", cuerpo=CUERPO, ejemplos=EJEMPLOS)
    with pytest.raises(CanalNoConectado):
        await sin_cuenta.estados()


async def test_leer_error_solo_conserva_el_mensaje_para_el_usuario_si_se_pide() -> None:
    respuesta = _error(400, 100, error_user_msg="texto", error_subcode=7)

    sin = leer_error(respuesta)
    con = leer_error(respuesta, con_mensaje=True)

    assert (sin.mensaje_para_el_usuario, sin.subcodigo) == (None, None)
    assert (con.mensaje_para_el_usuario, con.subcodigo) == ("texto", 7)


async def test_leer_error_recorta_el_mensaje_al_largo_del_detalle() -> None:
    respuesta = _error(400, 100, error_user_msg="x" * 900)

    assert len(leer_error(respuesta, con_mensaje=True).mensaje_para_el_usuario or "") == 500
