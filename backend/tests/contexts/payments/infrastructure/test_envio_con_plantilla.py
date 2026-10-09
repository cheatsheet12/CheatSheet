"""`EnvioPorWhatsApp` con la plantilla aprobada de Meta (U6, casos 2, 21, 24 y 27).

Fuera de la ventana de 24 h Meta solo acepta plantillas: si la empresa tiene la de
`recordatorio_de_cobro` aprobada, el recordatorio sale como `type: template`; si no, sigue saliendo
el texto de fábrica del adaptador. **Nunca el cuerpo editado de una plantilla no aprobada** (RN-04).
Sin red: el canal es un doble, o el cliente real de Meta sobre `httpx.MockTransport`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from cheatsheet.contexts.conversational.application.errors import MensajeRechazado
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaWhatsApp,
)
from cheatsheet.contexts.payments.application.ports_envio import ContactoDeCobro
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.contexts.payments.domain.dinero import formatear_es_ar
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.contexts.payments.infrastructure import envio as modulo_envio
from cheatsheet.contexts.payments.infrastructure.envio import (
    CODIGO_RECORDATORIO,
    SIN_LINK,
    EnvioPorWhatsApp,
    texto_de_recordatorio,
    variables_de_recordatorio,
)
from cheatsheet.shared.empresa import EmpresaId
from structlog.testing import capture_logs

from tests.logs import logger_nuevo

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
TELEFONO = "5491155550000"
NOMBRE = "Rosa Diaz"
LINK = LinkDePago(preference_id="pref-1", url="https://mp.example/checkout/pref-1")
CONTACTO = ContactoDeCobro(nombre=NOMBRE, telefono=TELEFONO)


def _cobro(*, monto: str = "1210.00", con_link: bool = True, vence: datetime = AHORA) -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal(monto),
        descripcion="Consulta de septiembre",
        vence_el=vence,
        created_at=AHORA,
    )
    if con_link:
        cobro.asignar_link(LINK, AHORA)
    return cobro


class ContactosFalsos:
    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None:
        del cliente_id
        return CONTACTO


@dataclass(frozen=True)
class _Aprobada:
    nombre_en_meta: str
    idioma: str
    parametros: Mapping[str, str]


class PlantillasFalsas:
    """`PlantillasAprobadas`: aprobada solo si se la nombra; anota qué variables le pasaron."""

    def __init__(self, *aprobadas: str, falla: Exception | None = None) -> None:
        self._aprobadas = set(aprobadas)
        self._falla = falla
        self.pedidos: list[tuple[str, dict[str, str]]] = []

    async def para(self, codigo: str, variables: Mapping[str, str]) -> _Aprobada | None:
        self.pedidos.append((codigo, dict(variables)))
        if self._falla is not None:
            raise self._falla
        if codigo not in self._aprobadas:
            return None
        return _Aprobada(nombre_en_meta=codigo, idioma="es_AR", parametros=dict(variables))


class CanalGrabador:
    def __init__(self, *, falla: Exception | None = None) -> None:
        self.textos: list[tuple[str, str]] = []
        self.plantillas: list[tuple[str, str, str, dict[str, str]]] = []
        self._falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        if self._falla is not None:
            raise self._falla
        self.textos.append((telefono, texto))
        return "wamid.TEXTO"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        if self._falla is not None:
            raise self._falla
        self.plantillas.append((telefono, nombre, idioma, dict(parametros)))
        return "wamid.PLANTILLA"


async def _enviar(envio: EnvioPorWhatsApp, cobro: Cobro) -> EstadoEntrega:
    return (await envio.enviar(empresa_id=EMPRESA, cobro=cobro, canal="WHATSAPP", paso=1)).estado


# --- Caso 2: con la plantilla aprobada, sale como plantilla ---------------------------------------------


async def test_con_la_plantilla_aprobada_el_recordatorio_sale_como_plantilla_y_no_como_texto() -> (
    None
):
    canal = CanalGrabador()
    plantillas = PlantillasFalsas(CODIGO_RECORDATORIO)

    estado = await _enviar(
        EnvioPorWhatsApp(canal, ContactosFalsos(), plantillas), _cobro(monto="1234.5")
    )

    assert estado is EstadoEntrega.ENVIADO
    assert canal.textos == []
    ((telefono, nombre, idioma, parametros),) = canal.plantillas
    assert (telefono, nombre, idioma) == (TELEFONO, "recordatorio_de_cobro", "es_AR")
    assert parametros == {
        "nombre": NOMBRE,
        "concepto": "Consulta de septiembre",
        "monto": "1.234,50",
        "link": LINK.url,
        "vencimiento": "07/09/2026",
    }


async def test_la_plantilla_sale_por_el_cliente_real_como_type_template_con_parameter_name() -> (
    None
):
    """Contra el cliente de Meta sobre `MockTransport`: la forma exacta del `POST`."""
    pedidos: list[httpx.Request] = []

    def servidor(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, json={"messages": [{"id": "wamid.OK"}]})

    canal = MensajeriaWhatsApp(
        ConfiguracionDeMensajeria(
            token="fake-token-for-tests",
            phone_number_id="1234567890",
            graph_url="https://graph.test",
            graph_version="v21.0",
            timeout_segundos=5.0,
        ),
        transporte=httpx.MockTransport(servidor),
    )

    estado = await _enviar(
        EnvioPorWhatsApp(canal, ContactosFalsos(), PlantillasFalsas(CODIGO_RECORDATORIO)),
        _cobro(),
    )

    assert estado is EstadoEntrega.ENVIADO
    (pedido,) = pedidos
    cuerpo = json.loads(pedido.read())
    assert cuerpo["type"] == "template"
    assert cuerpo["template"]["name"] == "recordatorio_de_cobro"
    assert cuerpo["template"]["language"] == {"code": "es_AR"}
    nombres = [p["parameter_name"] for p in cuerpo["template"]["components"][0]["parameters"]]
    assert nombres == ["nombre", "concepto", "monto", "link", "vencimiento"]


# --- Caso 21: sin plantilla aprobada, el texto de fábrica del adaptador --------------------------------


async def test_sin_plantilla_aprobada_sale_el_texto_de_fabrica_del_adaptador() -> None:
    canal = CanalGrabador()
    cobro = _cobro()

    estado = await _enviar(EnvioPorWhatsApp(canal, ContactosFalsos(), PlantillasFalsas()), cobro)

    assert estado is EstadoEntrega.ENVIADO
    assert canal.plantillas == []
    assert canal.textos == [(TELEFONO, texto_de_recordatorio(nombre=NOMBRE, cobro=cobro))]


async def test_se_le_pide_a_business_config_la_plantilla_del_recordatorio_de_cobro() -> None:
    plantillas = PlantillasFalsas()

    await _enviar(EnvioPorWhatsApp(CanalGrabador(), ContactosFalsos(), plantillas), _cobro())

    assert [codigo for codigo, _ in plantillas.pedidos] == ["recordatorio_de_cobro"]


async def test_si_meta_la_rechaza_el_paso_queda_fallido_y_no_levanta() -> None:
    canal = CanalGrabador(falla=MensajeRechazado("fuera de ventana", codigo=132001))

    estado = await _enviar(
        EnvioPorWhatsApp(canal, ContactosFalsos(), PlantillasFalsas(CODIGO_RECORDATORIO)),
        _cobro(),
    )

    assert estado is EstadoEntrega.FALLIDO


async def test_si_no_se_puede_consultar_la_plantilla_el_paso_queda_fallido_y_no_levanta() -> None:
    estado = await _enviar(
        EnvioPorWhatsApp(
            CanalGrabador(), ContactosFalsos(), PlantillasFalsas(falla=RuntimeError("sin base"))
        ),
        _cobro(),
    )

    assert estado is EstadoEntrega.FALLIDO


# --- Caso 24: el monto y el link como parámetros -----------------------------------------------------------


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [
        ("1234.5", "1.234,50"),
        ("12500", "12.500,00"),
        ("0.005", "0,01"),
        ("2.675", "2,68"),
        ("1234567.891", "1.234.567,89"),
        ("100", "100,00"),
    ],
)
async def test_el_monto_va_con_decimal_half_up_y_formato_argentino(
    monto: str, esperado: str
) -> None:
    assert formatear_es_ar(Decimal(monto)) == esperado


async def test_un_cobro_sin_link_manda_un_parametro_no_vacio() -> None:
    variables = variables_de_recordatorio(nombre=NOMBRE, cobro=_cobro(con_link=False))

    assert variables["link"] == SIN_LINK
    assert variables["link"].strip()
    assert "None" not in " ".join(variables.values())


async def test_el_vencimiento_sale_en_la_fecha_argentina_y_no_en_la_de_utc() -> None:
    # 02:30 UTC del 10/10 son las 23:30 del 09/10 en Buenos Aires.
    cobro = _cobro(vence=datetime(2026, 10, 10, 2, 30, tzinfo=UTC) + timedelta(0))

    assert variables_de_recordatorio(nombre=NOMBRE, cobro=cobro)["vencimiento"] == "09/10/2026"


# --- Caso 27: sin datos personales en los logs -------------------------------------------------------------------


async def test_ningun_log_de_la_via_de_plantilla_lleva_telefono_nombre_ni_monto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger_nuevo(monkeypatch, modulo_envio)
    canal = CanalGrabador(falla=RuntimeError(f"falló {TELEFONO} {NOMBRE}"))

    with capture_logs() as registros:
        await _enviar(
            EnvioPorWhatsApp(canal, ContactosFalsos(), PlantillasFalsas(CODIGO_RECORDATORIO)),
            _cobro(monto="9999.99"),
        )

    volcado = json.dumps(registros, default=str)
    assert registros  # el test no pasa por no haber registrado nada
    assert TELEFONO not in volcado
    assert NOMBRE not in volcado
    assert "9.999,99" not in volcado
