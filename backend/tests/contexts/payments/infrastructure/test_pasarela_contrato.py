"""Tests de contrato de `PortPasarelaDePago` contra MercadoPago.

**Ninguno abre un socket.** `httpx.MockTransport` va donde estaría la red, así que se
ejercita el cliente entero —método, URL, cuerpo, traducción de errores— contra respuestas
grabadas. Es el mismo criterio que los tests de contrato del épico 2.

Lo que se juega acá es la asimetría entre las dos operaciones que reciben un «no» del
proveedor: `reembolsar` lo devuelve como `RECHAZADO`, porque un rechazo deja el mundo en un
estado conocido; `invalidar_link` levanta, porque un rechazo deja un link que el cliente
todavía puede pagar (HU-E6-04 RN-03).

**Lo que estos tests no pueden probar** es que MercadoPago acepte un `expiration_date_to`
en el instante actual sobre una preferencia viva. Eso sólo se confirma en sandbox, con las
credenciales que `TODO.md` §5.3 todavía espera.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from cheatsheet.contexts.payments.application.errors import PasarelaNoDisponible
from cheatsheet.contexts.payments.application.ports import (
    EstadoDeReembolso,
    RespuestaDeReembolso,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.infrastructure.pasarela import (
    PasarelaMercadoPago,
    PasarelaSimulada,
    PortTokenDeMercadoPago,
)
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
URL_BASE = "https://api.test"
URL_NOTIFICACIONES = "https://cheatsheet-api.test"
PREFERENCIA = "1234567890-abcdef"


class TokenFijo(PortTokenDeMercadoPago):
    async def para(self, empresa_id: EmpresaId) -> str:
        del empresa_id
        return "APP_USR-token-de-prueba"


class Grabadora:
    """Responde lo que se le dijo y anota cada pedido que vio."""

    def __init__(self, *respuestas: httpx.Response | Exception) -> None:
        self.respuestas = list(respuestas)
        self.pedidos: list[httpx.Request] = []

    def transporte(self) -> httpx.MockTransport:
        def manejar(pedido: httpx.Request) -> httpx.Response:
            self.pedidos.append(pedido)
            indice = min(len(self.pedidos) - 1, len(self.respuestas) - 1)
            respuesta = self.respuestas[indice]
            if isinstance(respuesta, Exception):
                raise respuesta
            return respuesta

        return httpx.MockTransport(manejar)


def _pasarela(grabadora: Grabadora) -> PasarelaMercadoPago:
    return PasarelaMercadoPago(
        tokens=TokenFijo(),
        url_de_notificaciones=URL_NOTIFICACIONES,
        transporte=grabadora.transporte(),
        url_base=URL_BASE,
    )


def _cuerpo(pedido: httpx.Request) -> dict[str, Any]:
    datos: dict[str, Any] = json.loads(pedido.content.decode())
    return datos


# ------------------------------------------------------------------ invalidar el link


async def test_invalidar_adelanta_el_vencimiento_de_la_preferencia() -> None:
    """La operación que MercadoPago sí tiene: no hay DELETE de preferencias."""
    grabadora = Grabadora(httpx.Response(200, json={"id": PREFERENCIA}))

    await _pasarela(grabadora).invalidar_link(
        empresa_id=EMPRESA, preference_id=PREFERENCIA, ahora=AHORA
    )

    pedido = grabadora.pedidos[0]
    assert pedido.method == "PUT"
    assert str(pedido.url) == f"{URL_BASE}/checkout/preferences/{PREFERENCIA}"
    cuerpo = _cuerpo(pedido)
    assert cuerpo["expires"] is True
    # El instante actual, no una fecha futura: es lo que deja de aceptar pagos ya mismo.
    assert cuerpo["expiration_date_to"] == AHORA.isoformat()


async def test_una_preferencia_que_mercadopago_no_conoce_cuenta_como_invalidada() -> None:
    """Un 404 no puede cobrarle a nadie, así que no bloquea la cancelación."""
    grabadora = Grabadora(httpx.Response(404, json={"message": "Preference not found"}))

    await _pasarela(grabadora).invalidar_link(
        empresa_id=EMPRESA, preference_id=PREFERENCIA, ahora=AHORA
    )

    assert len(grabadora.pedidos) == 1


async def test_un_rechazo_al_invalidar_no_se_traga_como_respuesta() -> None:
    """La diferencia con `reembolsar`: acá un «no» deja un link vivo.

    El 400 no se reintenta —MercadoPago entendió y dijo que no— pero sí levanta, y eso es lo
    que hace que la cancelación entera no ocurra.
    """
    grabadora = Grabadora(httpx.Response(400, json={"message": "invalid expiration_date_to"}))

    with pytest.raises(PasarelaNoDisponible):
        await _pasarela(grabadora).invalidar_link(
            empresa_id=EMPRESA, preference_id=PREFERENCIA, ahora=AHORA
        )

    assert len(grabadora.pedidos) == 1


async def test_si_mercadopago_se_cae_al_invalidar_se_reintenta_y_despues_levanta() -> None:
    """Un 5xx sí es transitorio: se reintenta, y agotados los intentos no se da por muerta."""
    grabadora = Grabadora(httpx.Response(500, json={"message": "internal error"}))

    with pytest.raises(PasarelaNoDisponible):
        await _pasarela(grabadora).invalidar_link(
            empresa_id=EMPRESA, preference_id=PREFERENCIA, ahora=AHORA
        )

    assert len(grabadora.pedidos) == 3


async def test_un_timeout_al_invalidar_tampoco_da_el_link_por_muerto() -> None:
    grabadora = Grabadora(httpx.ConnectTimeout("sin respuesta"))

    with pytest.raises(PasarelaNoDisponible):
        await _pasarela(grabadora).invalidar_link(
            empresa_id=EMPRESA, preference_id=PREFERENCIA, ahora=AHORA
        )

    assert len(grabadora.pedidos) == 3


async def test_el_token_no_viaja_en_el_log_pero_si_en_la_cabecera() -> None:
    grabadora = Grabadora(httpx.Response(200, json={"id": PREFERENCIA}))

    await _pasarela(grabadora).invalidar_link(
        empresa_id=EMPRESA, preference_id=PREFERENCIA, ahora=AHORA
    )

    cabeceras = grabadora.pedidos[0].headers
    assert cabeceras["Authorization"].startswith("Bearer ")
    # MercadoPago deduplica del lado suyo con esto (no reemplaza a D20).
    assert cabeceras["X-Idempotency-Key"]


# ------------------------------------------------------------------ el doble


async def test_el_simulado_invalida_y_lo_deja_anotado() -> None:
    pasarela = PasarelaSimulada(Entorno.LOCAL)

    await pasarela.invalidar_link(empresa_id=EMPRESA, preference_id="pref-1", ahora=AHORA)

    assert pasarela.invalidados == ["pref-1"]
    assert "pref-1" not in pasarela.links


async def test_el_simulado_deja_caminar_la_rama_de_error_sin_editar_codigo() -> None:
    """La convención del doble: «rechazar» en la descripción hace fallar la invalidación."""
    pasarela = PasarelaSimulada(Entorno.LOCAL)
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion="Consulta que MercadoPago va a rechazar",
        vence_el=AHORA,
        created_at=AHORA,
    )
    link = await pasarela.crear_link(empresa_id=EMPRESA, cobro=cobro, url_de_retorno="https://x")

    with pytest.raises(PasarelaNoDisponible):
        await pasarela.invalidar_link(
            empresa_id=EMPRESA, preference_id=link.preference_id, ahora=AHORA
        )


# ------------------------------------------------------------- consultar el pago · D91


def _pago(**campos: Any) -> httpx.Response:
    return httpx.Response(200, json={"id": 1, "status": "approved", **campos})


async def _fecha_aprobada(**campos: Any) -> datetime | None:
    pago = await _pasarela(Grabadora(_pago(**campos))).consultar_pago(
        empresa_id=EMPRESA, payment_id="1"
    )
    return pago.fecha_aprobacion


async def test_date_approved_con_offset_y_con_z_dan_la_misma_hora_utc() -> None:
    """`08:00-04:00` y `12:00Z` son el mismo instante: 12:00 UTC."""
    con_offset = await _fecha_aprobada(date_approved="2026-09-19T08:00:00.000-04:00")
    con_z = await _fecha_aprobada(date_approved="2026-09-19T12:00:00.000Z")

    esperada = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    assert con_offset == esperada
    assert con_z == esperada
    assert con_offset is not None
    assert con_offset.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "campos",
    [
        pytest.param({"date_approved": None}, id="null"),
        pytest.param({}, id="ausente"),
        pytest.param({"date_approved": ""}, id="vacio"),
        pytest.param({"date_approved": "no es una fecha"}, id="basura"),
        pytest.param({"date_approved": 20260919}, id="numero"),
        pytest.param({"date_approved": "2026-09-19T08:00:00"}, id="sin-zona-horaria"),
        # Valid ISO dates whose conversion to UTC leaves `datetime`'s range: `astimezone`
        # raises `OverflowError`, not `ValueError`.
        pytest.param({"date_approved": "9999-12-31T23:59:59-03:00"}, id="desborda-arriba"),
        pytest.param({"date_approved": "0001-01-01T00:00:00+03:00"}, id="desborda-abajo"),
    ],
)
async def test_date_approved_ilegible_se_traduce_a_none_y_no_rompe(campos: dict[str, Any]) -> None:
    """Un formato que no entendemos no puede tumbar el webhook: la fecha queda aproximada."""
    assert await _fecha_aprobada(**campos) is None


async def test_el_monto_del_pago_sigue_leyendose_como_decimal() -> None:
    pago = await _pasarela(Grabadora(_pago(transaction_amount=1210.5))).consultar_pago(
        empresa_id=EMPRESA, payment_id="1"
    )

    assert pago.monto == Decimal("1210.5")
    assert pago.esta_aprobado


async def test_el_pago_real_se_ata_por_external_reference_y_no_por_la_orden() -> None:
    """Caso 1. El cuerpo de un pago de Checkout Pro trae `external_reference` y `order`, y **no**
    `preference_id`: `order.id` es la merchant order, no la preferencia (SDK oficial,
    `payment/commonTypes.ts`; a confirmar en sandbox, `TODO.md` §20.17)."""
    cobro_id = uuid4()
    pago = await _pasarela(
        Grabadora(
            _pago(
                external_reference=str(cobro_id),
                order={"id": 98765, "type": "mercadopago"},
                transaction_amount=1210.5,
            )
        )
    ).consultar_pago(empresa_id=EMPRESA, payment_id="1")

    assert pago.referencia_externa == str(cobro_id)
    assert pago.preference_id is None
    assert pago.monto == Decimal("1210.5")


@pytest.mark.parametrize(
    ("campos", "esperada"),
    [
        pytest.param({"currency_id": "ARS"}, "ARS", id="pesos"),
        pytest.param({"currency_id": " usd "}, "USD", id="se-normaliza"),
        pytest.param({}, None, id="ausente"),
        pytest.param({"currency_id": None}, None, id="null"),
        pytest.param({"currency_id": ""}, None, id="vacia"),
    ],
)
async def test_la_moneda_del_pago_se_lee_de_currency_id(
    campos: dict[str, Any], esperada: str | None
) -> None:
    pago = await _pasarela(Grabadora(_pago(**campos))).consultar_pago(
        empresa_id=EMPRESA, payment_id="1"
    )

    assert pago.moneda == esperada


@pytest.mark.parametrize(
    "campos",
    [
        pytest.param({}, id="ausente"),
        pytest.param({"external_reference": None}, id="null"),
        pytest.param({"external_reference": ""}, id="vacia"),
    ],
)
async def test_una_referencia_ausente_o_vacia_es_none(campos: dict[str, Any]) -> None:
    pago = await _pasarela(Grabadora(_pago(**campos))).consultar_pago(
        empresa_id=EMPRESA, payment_id="1"
    )

    assert pago.referencia_externa is None


async def test_el_preference_id_explicito_se_sigue_leyendo() -> None:
    """Compatibilidad: si el cuerpo trae `preference_id`, se usa tal cual."""
    pago = await _pasarela(Grabadora(_pago(preference_id=PREFERENCIA))).consultar_pago(
        empresa_id=EMPRESA, payment_id="1"
    )

    assert pago.preference_id == PREFERENCIA


async def test_el_simulado_informa_la_referencia_del_cobro_que_creo_el_link() -> None:
    """El camino feliz local sigue funcionando: el doble devuelve el id del cobro."""
    simulada = PasarelaSimulada(Entorno.LOCAL)
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion="Consulta",
        vence_el=AHORA,
        created_at=AHORA,
    )
    link = await simulada.crear_link(empresa_id=EMPRESA, cobro=cobro, url_de_retorno="https://x")

    pago = await simulada.consultar_pago(
        empresa_id=EMPRESA, payment_id=f"pago-{link.preference_id}"
    )

    assert pago.referencia_externa == str(cobro.id)


async def test_el_simulado_informa_una_fecha_de_aprobacion_real() -> None:
    """Una demo local no debe mostrar «aproximada»: el doble devuelve la hora actual en UTC."""
    antes = datetime.now(UTC)
    pago = await PasarelaSimulada(Entorno.LOCAL).consultar_pago(
        empresa_id=EMPRESA, payment_id="pago-pref-1"
    )
    despues = datetime.now(UTC)

    assert pago.fecha_aprobacion is not None
    assert pago.fecha_aprobacion.utcoffset() == timedelta(0)
    assert antes <= pago.fecha_aprobacion <= despues


# ------------------------------------------------------------------ reembolsar · P3, P2


CLAVE = UUID("33333333-3333-4333-8333-333333333333")
REEMBOLSO_OK = {
    "id": 987654,
    "payment_id": 1,
    "amount": 1234.56,
    "status": "approved",
    "date_created": "2026-09-19T09:00:00.000-03:00",
}


async def _reembolsar(grabadora: Grabadora, monto: str = "1234.56") -> RespuestaDeReembolso:
    return await _pasarela(grabadora).reembolsar(
        empresa_id=EMPRESA, payment_id="1", monto=Decimal(monto), clave=CLAVE
    )


@pytest.mark.parametrize("monto", ["1234.56", "0.10", "100.00", "0.01", "99999999.99"])
async def test_el_reembolso_manda_el_monto_como_numero_json_exacto_sin_float(monto: str) -> None:
    """Caso 20. `amount` es un número JSON armado desde el `Decimal`: la cadena que viaja es la
    que el agregado redondeó, sin pasar por `float` (que agregaría error binario)."""
    grabadora = Grabadora(httpx.Response(200, json=REEMBOLSO_OK))

    await _reembolsar(grabadora, monto)

    pedido = grabadora.pedidos[0]
    assert pedido.method == "POST"
    assert str(pedido.url) == f"{URL_BASE}/v1/payments/1/refunds"
    assert pedido.content.decode() == '{"amount": ' + monto + "}"
    leido = json.loads(pedido.content.decode(), parse_float=Decimal)
    assert leido["amount"] == Decimal(monto)
    assert pedido.headers["Content-Type"] == "application/json"


async def test_el_reembolso_reusa_la_clave_recibida_en_los_reintentos() -> None:
    """Caso 20. La clave viene de afuera (se guardó en T1): una nueva por llamada permitiría un
    segundo reembolso."""
    grabadora = Grabadora(
        httpx.Response(500, json={"message": "boom"}),
        httpx.ConnectTimeout("sin respuesta"),
        httpx.Response(200, json=REEMBOLSO_OK),
    )

    await _reembolsar(grabadora)

    claves = [p.headers["X-Idempotency-Key"] for p in grabadora.pedidos]
    assert claves == [str(CLAVE)] * 3


async def test_un_reembolso_aprobado_se_traduce_con_su_id_su_monto_y_su_fecha_en_utc() -> None:
    grabadora = Grabadora(httpx.Response(200, json=REEMBOLSO_OK))

    respuesta = await _reembolsar(grabadora)

    assert respuesta.estado is EstadoDeReembolso.ACEPTADO
    assert respuesta.mp_refund_id == "987654"
    assert respuesta.monto == Decimal("1234.56")
    assert respuesta.fecha == datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("cuerpo", "esperado"),
    [
        pytest.param({"status": "approved"}, EstadoDeReembolso.ACEPTADO, id="approved"),
        pytest.param({"status": "APPROVED"}, EstadoDeReembolso.ACEPTADO, id="mayusculas"),
        pytest.param({"status": "rejected"}, EstadoDeReembolso.RECHAZADO, id="rejected"),
        pytest.param({"status": "cancelled"}, EstadoDeReembolso.RECHAZADO, id="cancelled"),
        pytest.param({"status": "in_process"}, EstadoDeReembolso.EN_PROCESO, id="in_process"),
        pytest.param({"status": "pending"}, EstadoDeReembolso.EN_PROCESO, id="desconocido"),
        pytest.param({"status": None}, EstadoDeReembolso.EN_PROCESO, id="null"),
        pytest.param({}, EstadoDeReembolso.EN_PROCESO, id="ausente"),
        pytest.param({"status": 7}, EstadoDeReembolso.EN_PROCESO, id="numero"),
    ],
)
async def test_el_status_de_mercadopago_se_traduce_y_nunca_es_aceptado_por_defecto(
    cuerpo: dict[str, Any], esperado: EstadoDeReembolso
) -> None:
    """Caso 21. Solo `approved` acepta: un valor que no conocemos jamás da por devuelta la plata."""
    respuesta = await _reembolsar(Grabadora(httpx.Response(200, json=cuerpo)))

    assert respuesta.estado is esperado


async def test_un_4xx_es_un_rechazo_con_el_mensaje_de_mercadopago_sin_traducir() -> None:
    """Caso 21: es una respuesta, no una caída; el texto es el de MercadoPago."""
    grabadora = Grabadora(
        httpx.Response(400, json={"message": "Partial refunds not supported", "error": "4295"})
    )

    respuesta = await _reembolsar(grabadora)

    assert respuesta.estado is EstadoDeReembolso.RECHAZADO
    assert respuesta.motivo == "Partial refunds not supported"
    assert len(grabadora.pedidos) == 1


@pytest.mark.parametrize("estado", [401, 403, 408, 409, 425, 429])
async def test_un_4xx_ambiguo_al_reembolsar_no_es_un_rechazo_y_levanta(estado: int) -> None:
    """Un 409/429/... tras un timeout puede significar que MercadoPago ya lo procesó: tomarlo
    como rechazo borraría la clave y un reintento con clave nueva reembolsaría dos veces."""
    grabadora = Grabadora(httpx.Response(estado, json={"message": "key in use"}))

    with pytest.raises(PasarelaNoDisponible):
        await _reembolsar(grabadora)


@pytest.mark.parametrize("estado", [400, 404, 422])
async def test_un_4xx_de_negocio_al_reembolsar_sigue_siendo_un_rechazo(estado: int) -> None:
    grabadora = Grabadora(httpx.Response(estado, json={"message": "no"}))

    respuesta = await _reembolsar(grabadora)

    assert respuesta.estado is EstadoDeReembolso.RECHAZADO


async def test_un_5xx_o_un_timeout_al_reembolsar_levantan_despues_de_los_intentos() -> None:
    for falla in (httpx.Response(503, json={}), httpx.ConnectTimeout("sin respuesta")):
        grabadora = Grabadora(falla)

        with pytest.raises(PasarelaNoDisponible):
            await _reembolsar(grabadora)

        assert len(grabadora.pedidos) == 3


async def test_consultar_un_reembolso_es_un_get_y_se_traduce_igual() -> None:
    grabadora = Grabadora(httpx.Response(200, json={**REEMBOLSO_OK, "status": "in_process"}))

    respuesta = await _pasarela(grabadora).consultar_reembolso(
        empresa_id=EMPRESA, payment_id="1", refund_id="987654"
    )

    pedido = grabadora.pedidos[0]
    assert pedido.method == "GET"
    assert str(pedido.url) == f"{URL_BASE}/v1/payments/1/refunds/987654"
    assert respuesta.estado is EstadoDeReembolso.EN_PROCESO
    assert respuesta.mp_refund_id == "987654"


async def test_un_4xx_al_consultar_no_dice_nada_del_reembolso_y_levanta() -> None:
    """Un 404 no significa que el reembolso fue rechazado: no se puede afirmar nada."""
    grabadora = Grabadora(httpx.Response(404, json={"message": "Refund not found"}))

    with pytest.raises(PasarelaNoDisponible):
        await _pasarela(grabadora).consultar_reembolso(
            empresa_id=EMPRESA, payment_id="1", refund_id="987654"
        )


# ------------------------------------------------------------------ crear el link


def _respuesta_de_preferencia() -> httpx.Response:
    return httpx.Response(201, json={"id": PREFERENCIA, "init_point": "https://mp.test/checkout/1"})


async def test_la_preferencia_le_dice_a_mercadopago_a_donde_avisar_el_pago() -> None:
    """HS-T1. Sin `notification_url`, MercadoPago avisa sólo a la URL única de la aplicación,
    que no puede llevar la empresa, y ningún pago aprobado llegaba al sistema."""
    grabadora = Grabadora(_respuesta_de_preferencia())

    await _pasarela(grabadora).crear_link(
        empresa_id=EMPRESA, cobro=_cobro_con("Consulta"), url_de_retorno="https://x"
    )

    cuerpo = _cuerpo(grabadora.pedidos[0])
    assert cuerpo["notification_url"] == f"{URL_NOTIFICACIONES}/webhooks/mercadopago/{EMPRESA}"


async def test_el_monto_del_link_viaja_exacto_y_no_como_float() -> None:
    """`TODO.md` §20.6. El literal del cuerpo es el del `Decimal`, sin pasar por `float`."""
    grabadora = Grabadora(_respuesta_de_preferencia())
    cobro = replace(_cobro_con("Consulta"), monto=Decimal("1234.56"))

    await _pasarela(grabadora).crear_link(
        empresa_id=EMPRESA, cobro=cobro, url_de_retorno="https://x"
    )

    texto = grabadora.pedidos[0].content.decode()
    assert '"unit_price": 1234.56' in texto
    assert _cuerpo(grabadora.pedidos[0])["items"][0]["unit_price"] == 1234.56


async def test_una_descripcion_con_comillas_no_rompe_el_cuerpo() -> None:
    """El monto se inserta en texto ya armado: lo demás tiene que seguir siendo JSON válido."""
    grabadora = Grabadora(_respuesta_de_preferencia())

    await _pasarela(grabadora).crear_link(
        empresa_id=EMPRESA,
        cobro=_cobro_con('Sesión "intensiva" de 2\\3 horas'),
        url_de_retorno="https://x",
    )

    assert _cuerpo(grabadora.pedidos[0])["items"][0]["title"] == 'Sesión "intensiva" de 2\\3 horas'


# ------------------------------------------------------------------ el doble · caso 22


def _cobro_con(descripcion: str) -> Cobro:
    return Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion=descripcion,
        vence_el=AHORA,
        created_at=AHORA,
    )


async def _simulada_con(descripcion: str) -> tuple[PasarelaSimulada, str]:
    pasarela = PasarelaSimulada(Entorno.LOCAL)
    link = await pasarela.crear_link(
        empresa_id=EMPRESA, cobro=_cobro_con(descripcion), url_de_retorno="https://x"
    )
    return pasarela, f"pago-{link.preference_id}"


async def test_el_simulado_acepta_y_es_idempotente_con_la_misma_clave() -> None:
    pasarela, pago = await _simulada_con("Consulta")

    primera = await pasarela.reembolsar(
        empresa_id=EMPRESA, payment_id=pago, monto=Decimal("100.00"), clave=CLAVE
    )
    segunda = await pasarela.reembolsar(
        empresa_id=EMPRESA, payment_id=pago, monto=Decimal("100.00"), clave=CLAVE
    )

    assert primera.estado is EstadoDeReembolso.ACEPTADO
    assert segunda == primera
    assert pasarela.reembolsos == [(pago, Decimal("100.00"))]


async def test_el_simulado_rechaza_cuando_la_descripcion_dice_rechazar() -> None:
    pasarela, pago = await _simulada_con("Consulta que MercadoPago va a rechazar")

    respuesta = await pasarela.reembolsar(
        empresa_id=EMPRESA, payment_id=pago, monto=Decimal("100.00"), clave=CLAVE
    )

    assert respuesta.estado is EstadoDeReembolso.RECHAZADO
    assert respuesta.motivo
    assert pasarela.reembolsos == []


async def test_el_simulado_demora_hasta_la_primera_consulta() -> None:
    """Para caminar «Reembolso en proceso» y «Actualizar estado» en una laptop."""
    pasarela, pago = await _simulada_con("Consulta que va a demorar")

    pedido = await pasarela.reembolsar(
        empresa_id=EMPRESA, payment_id=pago, monto=Decimal("100.00"), clave=CLAVE
    )
    assert pedido.estado is EstadoDeReembolso.EN_PROCESO
    assert pedido.mp_refund_id is not None
    assert pasarela.reembolsos == []

    consulta = await pasarela.consultar_reembolso(
        empresa_id=EMPRESA, payment_id=pago, refund_id=pedido.mp_refund_id
    )

    assert consulta.estado is EstadoDeReembolso.ACEPTADO
    assert consulta.monto == Decimal("100.00")
    assert pasarela.reembolsos == [(pago, Decimal("100.00"))]
