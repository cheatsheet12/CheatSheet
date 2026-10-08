"""Las plantillas aprobadas llegan a los adaptadores por la raíz de composición (U6, ADR-0011).

De punta a punta y sin red: el caso de uso real de `business_config` (`ConsultarPlantillaParaEnviar`)
sobre un repositorio en memoria, los adaptadores reales de `payments` y `scheduling`, y el cliente
real de Meta sobre `httpx.MockTransport`. Lo que se afirma es lo que **sale**: `type: template`, los
parámetros por nombre y **solo** los que el cuerpo usa (Meta contesta 132000 si sobra o falta uno).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from cheatsheet.api.avisos_de_turno import CanalDeAvisosViaConversacion
from cheatsheet.api.plantillas_salientes import PlantillasViaConfiguracion
from cheatsheet.contexts.business_config.application.plantillas import (
    DE_FABRICA,
    ConsultarPlantillaParaEnviar,
)
from cheatsheet.contexts.business_config.domain.plantilla import (
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.contexts.conversational.application.notificaciones import NotificarAlCliente
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaWhatsApp,
)
from cheatsheet.contexts.payments.application.ports_envio import ContactoDeCobro
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.contexts.payments.infrastructure.envio import EnvioPorWhatsApp
from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso
from cheatsheet.contexts.scheduling.infrastructure.avisos import (
    AvisoPorWhatsApp,
    texto_de_cancelacion,
    texto_de_reprogramacion,
    texto_de_reserva,
    variables_de_aviso,
)
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.business_config.application.dobles_plantillas import (
    RepositorioPlantillasEnMemoria,
)
from tests.contexts.conversational.application.dobles import (
    RepositorioConversacionEnMemoria,
    RepositorioMensajeEnMemoria,
)
from tests.contexts.payments.application.test_cobros_y_recordatorios import enviar_de_punta_a_punta

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
AHORA = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
TELEFONO = "5491112345678"


def _aprobada(codigo: str, cuerpo: str | None = None) -> PlantillaDeNotificacion:
    canal, de_fabrica = DE_FABRICA[codigo]
    assert canal is CanalNotificacion.WHATSAPP
    return PlantillaDeNotificacion(
        id=uuid4(),
        empresa_id=EMPRESA,
        codigo=codigo,
        canal=canal,
        idioma="es_AR",
        cuerpo=cuerpo or de_fabrica,
        estado_aprobacion=EstadoDeAprobacion.APROBADA,
        nombre_en_meta=codigo,
    )


def _plantillas(*plantillas: PlantillaDeNotificacion) -> PlantillasViaConfiguracion:
    return PlantillasViaConfiguracion(
        ConsultarPlantillaParaEnviar(RepositorioPlantillasEnMemoria(*plantillas))
    )


class _Meta:
    def __init__(self) -> None:
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        return httpx.Response(200, json={"messages": [{"id": "wamid.OK"}]})

    def cuerpo(self, indice: int = 0) -> dict[str, object]:
        return json.loads(self.pedidos[indice].read())  # type: ignore[no-any-return]


def _canal(meta: _Meta) -> MensajeriaWhatsApp:
    return MensajeriaWhatsApp(
        ConfiguracionDeMensajeria(
            token="fake-token-for-tests",
            phone_number_id="999",
            graph_url="https://graph.test",
            graph_version="v21.0",
            timeout_segundos=1.0,
        ),
        transporte=httpx.MockTransport(meta),
    )


def _aviso(meta: _Meta, plantillas: PlantillasViaConfiguracion) -> AvisoPorWhatsApp:
    """El aviso de turno real: Meta falso, `NotificarAlCliente` real sobre repositorios en memoria."""
    caso = NotificarAlCliente(
        conversaciones=RepositorioConversacionEnMemoria(),
        mensajes=RepositorioMensajeEnMemoria(),
        mensajeria=_canal(meta),
    )
    return AvisoPorWhatsApp(
        CanalDeAvisosViaConversacion(caso, empresa_id=EMPRESA, reloj=_Reloj()), plantillas
    )


class _Reloj:
    def ahora(self) -> datetime:
        return AHORA


def _parametros(cuerpo: dict[str, object]) -> dict[str, str]:
    plantilla = cuerpo["template"]
    assert isinstance(plantilla, dict)
    return {p["parameter_name"]: p["text"] for p in plantilla["components"][0]["parameters"]}


DATOS = DatosDeAviso(
    cliente_id=uuid4(),
    telefono=TELEFONO,
    nombre_del_cliente="Ana Diaz",
    servicio="Corte",
    recurso="Consultorio 1",
    inicio=datetime(2026, 10, 15, 13, 30, tzinfo=UTC),
    inicio_anterior=datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
)


async def test_la_raiz_devuelve_la_aprobada_con_sus_parametros_y_none_si_no_lo_esta() -> None:
    sin_enviar = _aprobada("turno_cancelado")
    sin_enviar.estado_aprobacion = EstadoDeAprobacion.SIN_ENVIAR
    plantillas = _plantillas(_aprobada("turno_confirmado"), sin_enviar)
    variables = {"nombre": "Ana", "servicio": "Corte", "recurso": "Sala", "fecha": "1", "hora": "2"}

    aprobada = await plantillas.para("turno_confirmado", variables)
    no_aprobada = await plantillas.para("turno_cancelado", variables)

    assert aprobada is not None
    assert aprobada.nombre_en_meta == "turno_confirmado"
    assert aprobada.parametros == variables
    assert no_aprobada is None


# --- Los tres avisos de turno, por el cliente real ---------------------------------------------------------


async def test_la_cancelacion_aprobada_sale_como_template_con_los_parametros_que_el_cuerpo_usa() -> (
    None
):
    meta = _Meta()
    aviso = _aviso(meta, _plantillas(_aprobada("turno_cancelado")))

    await aviso.avisar_cancelacion(DATOS)

    cuerpo = meta.cuerpo()
    assert cuerpo["type"] == "template"
    assert cuerpo["to"] == TELEFONO
    # `turno_cancelado` no usa `{{recurso}}`: no se manda (Meta exige la cantidad exacta).
    assert _parametros(cuerpo) == {
        "nombre": "Ana Diaz",
        "servicio": "Corte",
        "fecha": "15/10/2026",
        "hora": "10:30",
    }


async def test_el_cuerpo_editado_por_el_administrador_cambia_los_parametros_que_salen() -> None:
    meta = _Meta()
    editada = _aprobada(
        "turno_confirmado", "Hola {{nombre}}, te esperamos el {{fecha}} a las {{hora}}. Gracias."
    )
    aviso = _aviso(meta, _plantillas(editada))

    await aviso.avisar_reserva(DATOS)

    assert set(_parametros(meta.cuerpo())) == {"nombre", "fecha", "hora"}


async def test_la_reprogramacion_lleva_el_horario_anterior() -> None:
    meta = _Meta()
    aviso = _aviso(meta, _plantillas(_aprobada("turno_reprogramado")))

    await aviso.avisar_reprogramacion(DATOS)

    parametros = _parametros(meta.cuerpo())
    assert (parametros["fecha_anterior"], parametros["hora_anterior"]) == ("14/10/2026", "09:00")


async def test_una_reprogramacion_sin_horario_anterior_sale_como_texto_y_no_como_plantilla() -> (
    None
):
    meta = _Meta()
    sin_anterior = DatosDeAviso(
        cliente_id=uuid4(),
        telefono=TELEFONO,
        nombre_del_cliente="Ana Diaz",
        servicio="Corte",
        recurso="Consultorio 1",
        inicio=DATOS.inicio,
    )
    aviso = _aviso(meta, _plantillas(_aprobada("turno_reprogramado")))

    await aviso.avisar_reprogramacion(sin_anterior)

    # La plantilla pide `{{fecha_anterior}}` y no hay con qué completarla: texto de fábrica.
    assert meta.cuerpo()["type"] == "text"


@pytest.mark.parametrize(
    ("codigo", "texto_del_adaptador"),
    [
        ("turno_confirmado", texto_de_reserva(DATOS)),
        ("turno_cancelado", texto_de_cancelacion(DATOS)),
        ("turno_reprogramado", texto_de_reprogramacion(DATOS)),
    ],
)
async def test_el_texto_de_fabrica_de_cada_aviso_dice_lo_mismo_que_la_plantilla_de_fabrica(
    codigo: str, texto_del_adaptador: str
) -> None:
    """El cliente recibe lo mismo salga por plantilla o como texto (revalidación, punto 16)."""
    plantillas = _plantillas(_aprobada(codigo))
    aprobada = await plantillas.para(codigo, variables_de_aviso(DATOS))

    assert aprobada is not None
    assert aprobada.texto == texto_del_adaptador


# --- El recordatorio de cobro, por el cliente real ------------------------------------------------------------


class _Contactos:
    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None:
        del cliente_id
        return ContactoDeCobro(nombre="Rosa Diaz", telefono=TELEFONO)


async def test_el_recordatorio_aprobado_sale_como_template_con_monto_en_formato_argentino() -> None:
    meta = _Meta()
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1234.5"),
        descripcion="Consulta de\noctubre",
        vence_el=AHORA,
        created_at=AHORA,
    )
    cobro.asignar_link(LinkDePago(preference_id="p", url="https://mp.example/checkout/p"), AHORA)
    envio = EnvioPorWhatsApp(
        _canal(meta), _Contactos(), _plantillas(_aprobada("recordatorio_de_cobro"))
    )

    resultado = await enviar_de_punta_a_punta(
        envio, empresa_id=EMPRESA, cobro=cobro, canal="WHATSAPP", paso=1
    )
    estado = resultado.estado

    assert estado is EstadoEntrega.ENVIADO
    cuerpo = meta.cuerpo()
    assert cuerpo["type"] == "template"
    # El cuerpo de fábrica no usa `{{vencimiento}}`: no se manda. Y el salto de línea se sanea.
    assert _parametros(cuerpo) == {
        "nombre": "Rosa Diaz",
        "concepto": "Consulta de octubre",
        "monto": "1.234,50",
        "link": "https://mp.example/checkout/p",
    }
