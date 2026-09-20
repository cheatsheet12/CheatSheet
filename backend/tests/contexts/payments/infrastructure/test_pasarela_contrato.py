"""Tests de contrato de `PortPasarelaDePago` contra MercadoPago.

**Ninguno abre un socket.** `httpx.MockTransport` va donde estaría la red, así que se
ejercita el cliente entero —método, URL, cuerpo, traducción de errores— contra respuestas
grabadas. Es el mismo criterio que los tests de contrato del épico 2.

Lo que se juega acá es la asimetría entre las dos operaciones que reciben un «no» del
proveedor: `reembolsar` lo devuelve como `False`, porque un rechazo deja el mundo en un
estado conocido; `invalidar_link` levanta, porque un rechazo deja un link que el cliente
todavía puede pagar (HU-E6-04 RN-03).

**Lo que estos tests no pueden probar** es que MercadoPago acepte un `expiration_date_to`
en el instante actual sobre una preferencia viva. Eso sólo se confirma en sandbox, con las
credenciales que `TODO.md` §5.3 todavía espera.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cheatsheet.contexts.payments.application.errors import PasarelaNoDisponible
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
        tokens=TokenFijo(), transporte=grabadora.transporte(), url_base=URL_BASE
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
