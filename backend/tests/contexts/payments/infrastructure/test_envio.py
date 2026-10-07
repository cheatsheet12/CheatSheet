"""`EnvioPorWhatsApp`: el recordatorio de cobro por el canal real, sin red (U5, HS-T3 RN-02).

El canal es un doble o el cliente real de Meta sobre `httpx.MockTransport`: **ningún test toca la
red ni duerme**. Lo que se afirma es el texto (con el monto en `Decimal`), que el adaptador
**nunca levanta**, que un fallo deja el paso registrado y no se reenvía, y que ningún log lleva
datos personales.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from cheatsheet.contexts.conversational.application.errors import CanalNoConectado
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaSimulada,
    MensajeriaWhatsApp,
    SinCanal,
)
from cheatsheet.contexts.payments.application.ports_envio import ContactoDeCobro
from cheatsheet.contexts.payments.application.recordatorios import DespacharRecordatorios
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.contexts.payments.infrastructure.envio import (
    EnvioPorWhatsApp,
    texto_de_recordatorio,
)
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.empresa import EmpresaId
from structlog.testing import capture_logs

from tests.contexts.payments.application.test_cobros_y_recordatorios import (
    AislamientoFalso,
    CadenaFalsa,
    RecordatoriosFalsos,
)
from tests.contexts.payments.application.test_confirmacion import CobrosFalsos, PublicadorFalso

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
TELEFONO = "5491155550000"
NOMBRE = "Rosa Diaz"
LINK = LinkDePago(preference_id="pref-1", url="https://mp.example/checkout/pref-1")


def _cobro(*, monto: str = "1210.00", con_link: bool = True, vence_en_dias: int = 0) -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal(monto),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=vence_en_dias),
        created_at=AHORA,
    )
    if con_link:
        cobro.asignar_link(LINK, AHORA)
    return cobro


class ContactosFalsos:
    def __init__(self, contacto: ContactoDeCobro | None = None) -> None:
        self.contacto = contacto

    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None:
        del cliente_id
        return self.contacto


CONTACTO = ContactoDeCobro(nombre=NOMBRE, telefono=TELEFONO)


class SinPlantillas:
    """`PlantillasAprobadas` sin ninguna aprobada: el adaptador manda su texto de fábrica."""

    async def para(self, codigo: str, variables: object) -> None:
        del codigo, variables
        return


class CanalGrabador:
    def __init__(self, *, falla: Exception | None = None) -> None:
        self.enviados: list[tuple[str, str]] = []
        self._falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        if self._falla is not None:
            raise self._falla
        self.enviados.append((telefono, texto))
        return "wamid.OK"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        raise AssertionError("sin plantilla aprobada nunca se manda una plantilla")


async def _enviar(
    envio: EnvioPorWhatsApp, cobro: Cobro, *, canal: str = "WHATSAPP"
) -> EstadoEntrega:
    return await envio.enviar(empresa_id=EMPRESA, cobro=cobro, canal=canal, paso=1)


# --- Caso 16 y 17: el texto ----------------------------------------------------------------


async def test_el_texto_lleva_nombre_concepto_monto_con_dos_decimales_y_el_link() -> None:
    texto = texto_de_recordatorio(nombre=NOMBRE, cobro=_cobro(monto="1234.5"))

    assert NOMBRE in texto
    assert "Consulta de septiembre" in texto
    assert "$ 1234.50" in texto
    assert LINK.url in texto


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [("0.005", "0.01"), ("10.004", "10.00"), ("2.675", "2.68"), ("1210", "1210.00")],
)
async def test_el_monto_se_redondea_half_up_con_decimal(monto: str, esperado: str) -> None:
    # `Cobro` ya redondea al crearse; el texto no puede reintroducir un `float` ni otro modo.
    assert f"$ {esperado}." in texto_de_recordatorio(nombre=NOMBRE, cobro=_cobro(monto=monto))


async def test_un_cobro_sin_link_no_dice_nada_del_link_ni_none() -> None:
    texto = texto_de_recordatorio(nombre=NOMBRE, cobro=_cobro(con_link=False))

    assert "None" not in texto
    assert "pagarlo" not in texto
    assert texto.endswith("$ 1210.00.")


async def test_el_envio_manda_el_texto_al_telefono_del_cliente_y_devuelve_enviado() -> None:
    canal = CanalGrabador()

    estado = await _enviar(
        EnvioPorWhatsApp(canal, ContactosFalsos(CONTACTO), SinPlantillas()), _cobro()
    )

    assert estado is EstadoEntrega.ENVIADO
    assert [telefono for telefono, _ in canal.enviados] == [TELEFONO]
    assert "Consulta de septiembre" in canal.enviados[0][1]


# --- Caso 18 y 19: lo que no se manda ------------------------------------------------------


async def test_un_cliente_sin_telefono_queda_fallido_sin_llamar_al_canal() -> None:
    canal = CanalGrabador()

    estado = await _enviar(
        EnvioPorWhatsApp(canal, ContactosFalsos(None), SinPlantillas()), _cobro()
    )

    assert estado is EstadoEntrega.FALLIDO
    assert canal.enviados == []


@pytest.mark.parametrize("canal_del_paso", ["EMAIL", "PANEL"])
async def test_un_paso_que_no_es_whatsapp_queda_fallido_con_su_log(canal_del_paso: str) -> None:
    canal = CanalGrabador()
    envio = EnvioPorWhatsApp(canal, ContactosFalsos(CONTACTO), SinPlantillas())

    with capture_logs() as registros:
        estado = await _enviar(envio, _cobro(), canal=canal_del_paso)

    assert estado is EstadoEntrega.FALLIDO
    assert canal.enviados == []
    avisos = [r for r in registros if r["event"] == "recordatorio_canal_sin_adaptador"]
    assert len(avisos) == 1
    assert avisos[0]["canal"] == canal_del_paso


# --- Caso 23: nunca levanta ----------------------------------------------------------------


@pytest.mark.parametrize(
    "falla", [RuntimeError("explotó"), CanalNoConectado("sin canal"), ValueError("raro")]
)
async def test_un_canal_que_levanta_deja_el_recordatorio_fallido_y_nunca_levanta(
    falla: Exception,
) -> None:
    envio = EnvioPorWhatsApp(CanalGrabador(falla=falla), ContactosFalsos(CONTACTO), SinPlantillas())

    assert await _enviar(envio, _cobro()) is EstadoEntrega.FALLIDO


async def test_si_el_directorio_de_contactos_levanta_tampoco_levanta_el_envio() -> None:
    class ContactosRotos:
        async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None:
            del cliente_id
            raise RuntimeError("la base se cayó")

    envio = EnvioPorWhatsApp(CanalGrabador(), ContactosRotos(), SinPlantillas())

    assert await _enviar(envio, _cobro()) is EstadoEntrega.FALLIDO


# --- Caso 27: sin datos personales en el log ----------------------------------------------


async def test_ningun_log_lleva_telefono_nombre_ni_texto() -> None:
    cobro = _cobro()
    texto = texto_de_recordatorio(nombre=NOMBRE, cobro=cobro)
    casos = [
        EnvioPorWhatsApp(CanalGrabador(), ContactosFalsos(CONTACTO), SinPlantillas()),
        EnvioPorWhatsApp(CanalGrabador(), ContactosFalsos(None), SinPlantillas()),
        EnvioPorWhatsApp(
            CanalGrabador(falla=RuntimeError(f"fallo con {TELEFONO} y {NOMBRE}")),
            ContactosFalsos(CONTACTO),
            SinPlantillas(),
        ),
    ]

    with capture_logs() as registros:
        for envio in casos:
            await _enviar(envio, cobro)
        await _enviar(casos[0], cobro, canal="EMAIL")

    volcado = repr(registros)
    assert registros  # el test no pasa por no haber registrado nada
    for dato in (TELEFONO, NOMBRE, texto, LINK.url):
        assert dato not in volcado


# --- Caso 30: el simulado detrás del adaptador real ----------------------------------------


async def test_con_el_canal_simulado_el_recordatorio_queda_enviado_como_hoy() -> None:
    simulado = MensajeriaSimulada(Entorno.STAGING)

    estado = await _enviar(
        EnvioPorWhatsApp(simulado, ContactosFalsos(CONTACTO), SinPlantillas()), _cobro()
    )

    assert estado is EstadoEntrega.ENVIADO
    assert len(simulado.enviados) == 1


async def test_sin_canal_en_produccion_el_recordatorio_queda_fallido() -> None:
    estado = await _enviar(
        EnvioPorWhatsApp(SinCanal(), ContactosFalsos(CONTACTO), SinPlantillas()), _cobro()
    )

    assert estado is EstadoEntrega.FALLIDO


# --- Casos 13, 20, 21 y 22: el barrido con el cliente real de Meta sobre MockTransport -----


class Meta:
    """Un Meta falso: contesta lo que le toque, en orden (el último se repite), y cuenta."""

    def __init__(self, *respuestas: httpx.Response | Exception) -> None:
        self._respuestas = list(respuestas)
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        respuesta = self._respuestas[min(len(self.pedidos), len(self._respuestas)) - 1]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


async def _sin_esperar(segundos: float) -> None:
    del segundos


def _barrido(
    meta: Meta, cobros: CobrosFalsos, recordatorios: RecordatoriosFalsos
) -> DespacharRecordatorios:
    canal = MensajeriaWhatsApp(
        ConfiguracionDeMensajeria(
            token="fake-token-for-tests",
            phone_number_id="999",
            graph_url="https://graph.test",
            graph_version="v21.0",
            timeout_segundos=1.0,
        ),
        transporte=httpx.MockTransport(meta),
        esperar=_sin_esperar,
    )
    return DespacharRecordatorios(
        cobros=cobros,
        recordatorios=recordatorios,
        envio=EnvioPorWhatsApp(canal, ContactosFalsos(CONTACTO), SinPlantillas()),
        cadena=CadenaFalsa(),
        publicador=PublicadorFalso(),
        aislamiento=AislamientoFalso(),
    )


def _ok() -> httpx.Response:
    return httpx.Response(200, json={"messages": [{"id": "wamid.OK"}]})


async def test_el_primer_paso_de_un_cobro_vencido_llega_a_la_cloud_api() -> None:
    """**Caso 13.** Antes ningún recordatorio llegaba a `MensajeriaWhatsApp`."""
    cobros, recordatorios, meta = CobrosFalsos(), RecordatoriosFalsos(), Meta(_ok())
    await cobros.agregar(_cobro())

    resultado = await _barrido(meta, cobros, recordatorios).ejecutar(
        empresa_id=EMPRESA, ahora=AHORA + timedelta(days=4)
    )

    assert resultado.procesados == 1
    assert len(meta.pedidos) == 1
    pedido = meta.pedidos[0]
    assert str(pedido.url) == "https://graph.test/v21.0/999/messages"
    assert b'"to":"5491155550000"' in pedido.read().replace(b" ", b"")
    assert recordatorios.guardados[0].estado_entrega is EstadoEntrega.ENVIADO


async def test_un_400_deja_fallido_con_un_solo_post_y_el_barrido_sigue() -> None:
    """**Caso 20.** El primer cobro lo rechaza Meta; el segundo sale."""
    cobros, recordatorios = CobrosFalsos(), RecordatoriosFalsos()
    meta = Meta(httpx.Response(400, json={"error": {"code": 131026}}), _ok())
    primero, segundo = _cobro(), _cobro()
    await cobros.agregar(primero)
    await cobros.agregar(segundo)

    await _barrido(meta, cobros, recordatorios).ejecutar(
        empresa_id=EMPRESA, ahora=AHORA + timedelta(days=4)
    )

    assert len(meta.pedidos) == 2  # uno rechazado (sin reintento) y uno aceptado
    estados = sorted(r.estado_entrega.value for r in recordatorios.guardados if r.estado_entrega)
    assert estados == ["ENVIADO", "FALLIDO"]


async def test_tres_503_dejan_fallido_tras_tres_posts_y_el_barrido_siguiente_no_lo_reenvia() -> (
    None
):
    """**Caso 21 (D25).**"""
    cobros, recordatorios, meta = CobrosFalsos(), RecordatoriosFalsos(), Meta(httpx.Response(503))
    await cobros.agregar(_cobro())
    barrido = _barrido(meta, cobros, recordatorios)
    ahora = AHORA + timedelta(days=4)

    primero = await barrido.ejecutar(empresa_id=EMPRESA, ahora=ahora)
    assert (primero.procesados, primero.fallidos) == (0, 1)
    assert len(meta.pedidos) == 3
    assert recordatorios.guardados[0].estado_entrega is EstadoEntrega.FALLIDO

    await barrido.ejecutar(empresa_id=EMPRESA, ahora=ahora)
    assert len(meta.pedidos) == 3


async def test_un_timeout_de_lectura_deja_fallido_tras_un_post_y_no_se_reenvia() -> None:
    """**Caso 22.** Meta pudo haberlo aceptado: un duplicado es peor que un recordatorio que falta."""
    cobros, recordatorios = CobrosFalsos(), RecordatoriosFalsos()
    meta = Meta(httpx.ReadTimeout("lento"))
    await cobros.agregar(_cobro())
    barrido = _barrido(meta, cobros, recordatorios)
    ahora = AHORA + timedelta(days=4)

    await barrido.ejecutar(empresa_id=EMPRESA, ahora=ahora)
    await barrido.ejecutar(empresa_id=EMPRESA, ahora=ahora)

    assert len(meta.pedidos) == 1
    assert recordatorios.guardados[0].estado_entrega is EstadoEntrega.FALLIDO
