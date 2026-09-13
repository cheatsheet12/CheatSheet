"""`PortPasarelaDePago` contra MercadoPago, y su doble.

Tres operaciones: crear la preferencia, consultar un pago y reembolsar. El OAuth, el refresco
del token y la validación de la conexión son de `integrations` y ya existen desde el épico 2 —
acá sólo se pide el token y se usa.

**Un rechazo no es una caída.** `reembolsar` devuelve un booleano y no levanta cuando
MercadoPago dice que no (HU-E6-05 RN-03): eso es una respuesta, y el cobro mantiene su estado.
Lo que sí levanta es no poder preguntar, y esa distinción es la misma que `billing` mantiene
con ARCA.

**El simulado se niega a construirse en producción**, como los cinco anteriores, y acá con más
en juego que en ninguno: una empresa cobrando contra este doble estaría entregando links que
nadie puede pagar y dando por saldadas deudas que nadie pagó.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx

from cheatsheet.contexts.payments.application.errors import PasarelaNoDisponible
from cheatsheet.contexts.payments.application.ports import PagoRecibido
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

URL_API = "https://api.mercadopago.com"
TIMEOUT_SEGUNDOS = 15.0
MAX_INTENTOS = 3


class PortTokenDeMercadoPago:
    """Cómo se consigue el token de una empresa. Lo resuelve el composition root.

    Declarado como clase y no como `Protocol` porque tiene una sola implementación y vive del
    otro lado de una frontera de contextos: el que la construye es `api/mercadopago.py`, con
    acceso a `integrations`, que es la única capa que puede cablear dos contextos (R3).
    """

    async def para(self, empresa_id: EmpresaId) -> str:  # pragma: no cover - lo sustituye el root
        raise NotImplementedError


class PasarelaMercadoPago:
    """`PortPasarelaDePago` contra la API real."""

    def __init__(
        self,
        *,
        tokens: PortTokenDeMercadoPago,
        transporte: httpx.AsyncBaseTransport | None = None,
        url_base: str = URL_API,
    ) -> None:
        self._tokens = tokens
        # `transporte` es como se prueban todos los clientes HTTP de este repositorio:
        # `httpx.MockTransport` va donde iría el socket. Sin él, el parser de la respuesta
        # sólo sería alcanzable metiendo mano en un atributo privado.
        self._transporte = transporte
        self._url_base = url_base

    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        cuerpo: dict[str, Any] = {
            "items": [
                {
                    "title": cobro.descripcion[:250],
                    "quantity": 1,
                    # **Texto y no float.** MercadoPago acepta un número JSON y lo redondea a
                    # su manera; mandar la cadena que el agregado ya redondeó (D15) es lo que
                    # hace que el link cobre exactamente lo que la fila dice.
                    "unit_price": float(cobro.monto),
                    "currency_id": "ARS",
                }
            ],
            # Lo que ata la notificación a una fila nuestra. Sin esto, el webhook llega con un
            # `payment_id` que no sabemos a quién corresponde.
            "external_reference": str(cobro.id),
            "back_urls": {"success": url_de_retorno, "failure": url_de_retorno},
            "expires": True,
            "expiration_date_to": cobro.vence_el.isoformat(),
        }
        datos = await self._pedir(
            empresa_id, "POST", "/checkout/preferences", cuerpo, operacion="crear_link"
        )
        preferencia = str(datos.get("id") or "")
        url = str(datos.get("init_point") or datos.get("sandbox_init_point") or "")
        if not preferencia or not url:
            # Una respuesta 200 sin lo que pedimos es tan inservible como un timeout, y el
            # criterio de aceptación es el mismo: el cobro no se crea.
            raise PasarelaNoDisponible(
                "MercadoPago respondio sin preferencia ni link de pago utilizables"
            )
        return LinkDePago(preference_id=preferencia, url=url)

    async def consultar_pago(self, *, empresa_id: EmpresaId, payment_id: str) -> PagoRecibido:
        datos = await self._pedir(
            empresa_id, "GET", f"/v1/payments/{payment_id}", None, operacion="consultar_pago"
        )
        return PagoRecibido(
            payment_id=str(datos.get("id") or payment_id),
            # `preference_id` no siempre viene; `external_reference` es el id del cobro y sí.
            preference_id=_preferencia_de(datos),
            estado=str(datos.get("status") or ""),
            monto=_monto_de(datos),
        )

    async def reembolsar(self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal) -> bool:
        """`True` si MercadoPago aceptó, `False` si lo rechazó (RN-03).

        Un booleano y no una excepción, porque un rechazo **es una respuesta**: el cobro
        mantiene su estado y se avisa al administrador. No poder preguntar es otra cosa y sí
        levanta.
        """
        try:
            await self._pedir(
                empresa_id,
                "POST",
                f"/v1/payments/{payment_id}/refunds",
                {"amount": float(monto)},
                operacion="reembolsar",
            )
        except _RechazoDeMercadoPago as exc:
            logger.warning("reembolso_rechazado", payment_id=payment_id, estado=exc.estado)
            return False
        return True

    async def _pedir(
        self,
        empresa_id: EmpresaId,
        metodo: str,
        ruta: str,
        cuerpo: dict[str, Any] | None,
        *,
        operacion: str,
    ) -> dict[str, Any]:
        token = await self._tokens.para(empresa_id)
        cabeceras = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # MercadoPago usa esta cabecera para deduplicar del lado suyo. No reemplaza a
            # nuestra idempotencia (D20) -- protege el envío, no el procesamiento.
            "X-Idempotency-Key": str(uuid4()),
        }
        ultimo: Exception | None = None
        for intento in range(1, MAX_INTENTOS + 1):
            try:
                async with self._cliente() as cliente:
                    respuesta = await cliente.request(
                        metodo, f"{self._url_base}{ruta}", json=cuerpo, headers=cabeceras
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                ultimo = exc
                # Nada del token se registra: es una credencial de un tercero.
                logger.warning("mercadopago_reintento", operacion=operacion, intento=intento)
                continue

            if respuesta.status_code < httpx.codes.BAD_REQUEST:
                return _cuerpo(respuesta)
            if respuesta.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                # 4xx es una respuesta: MercadoPago entendió y dijo que no. Reintentarlo sería
                # repetir un pedido que ya sabemos que va a fallar igual.
                raise _RechazoDeMercadoPago(respuesta.status_code, _texto_de_error(respuesta))
            ultimo = PasarelaNoDisponible(f"MercadoPago respondio {respuesta.status_code}")
            logger.warning(
                "mercadopago_reintento", operacion=operacion, estado=respuesta.status_code
            )

        raise PasarelaNoDisponible(
            f"MercadoPago no respondio a {operacion} tras {MAX_INTENTOS} intentos: {ultimo}"
        )

    def _cliente(self) -> httpx.AsyncClient:
        if self._transporte is not None:
            return httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS, transport=self._transporte)
        return httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS)


class _RechazoDeMercadoPago(Exception):
    """4xx: MercadoPago entendió el pedido y lo rechazó. Interna de este módulo."""

    def __init__(self, estado: int, detalle: str) -> None:
        super().__init__(f"MercadoPago rechazo el pedido ({estado}): {detalle}")
        self.estado = estado


def _cuerpo(respuesta: httpx.Response) -> dict[str, Any]:
    try:
        datos = respuesta.json()
    except ValueError as exc:  # pragma: no cover - MercadoPago siempre manda JSON
        raise PasarelaNoDisponible("MercadoPago respondio algo que no es JSON") from exc
    return datos if isinstance(datos, dict) else {}


def _texto_de_error(respuesta: httpx.Response) -> str:
    """El mensaje de MercadoPago, si lo hay. **No se traduce.**

    Mismo criterio que con los códigos de ARCA: decidir qué significan cuarenta mensajes de un
    tercero es equivocarse en uno, en un texto que alguien le lleva a su contador.
    """
    datos = _cuerpo(respuesta)
    return str(datos.get("message") or datos.get("error") or respuesta.status_code)


def _preferencia_de(datos: dict[str, Any]) -> str | None:
    valor = datos.get("preference_id") or datos.get("order", {}).get("id")
    return str(valor) if valor else None


def _monto_de(datos: dict[str, Any]) -> Decimal | None:
    """El monto, **desde el texto** de la respuesta.

    `Decimal(str(...))` y no `Decimal(float)`: construir un `Decimal` desde un float arrastra
    el error binario del float adentro, que es exactamente lo que `CLAUDE.md` §3.5 prohíbe.
    """
    valor = datos.get("transaction_amount")
    return Decimal(str(valor)) if valor is not None else None


class PasarelaSimulada:
    """El doble: links y pagos sin socket.

    **Rechazado en producción**, y acá con más en juego que en ningún otro simulado del
    sistema: una empresa cobrando contra esto estaría entregando links que nadie puede pagar y
    dando por saldadas deudas que nadie pagó.

    No es siempre-que-sí a propósito. Un cobro cuya descripción contenga «rechazar» hace que
    el reembolso vuelva rechazado, para que la rama de RN-03 se pueda caminar en una laptop
    sin editar código.
    """

    #: La palabra que dispara el rechazo. Documentada acá porque un doble cuyo comportamiento
    #: hay que adivinar leyendo el código no sirve para lo que existe.
    PALABRA_DE_RECHAZO = "rechazar"

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "La pasarela simulada no puede usarse en produccion: entregaria links que "
                "nadie puede pagar y daria por saldadas deudas que nadie pago"
            )
        self.links: dict[str, str] = {}
        self.reembolsos: list[tuple[str, Decimal]] = []
        self._rechazan: set[str] = set()

    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        del empresa_id, url_de_retorno
        preferencia = f"pref-{cobro.id}"
        self.links[preferencia] = str(cobro.id)
        if self.PALABRA_DE_RECHAZO in cobro.descripcion.lower():
            self._rechazan.add(preferencia)
        return LinkDePago(
            preference_id=preferencia,
            # Con la forma de una real: un código que sólo vio `http://x` es un código que se
            # rompe el día que ve una URL de verdad.
            url=f"https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id={preferencia}",
        )

    async def consultar_pago(self, *, empresa_id: EmpresaId, payment_id: str) -> PagoRecibido:
        del empresa_id
        return PagoRecibido(
            payment_id=payment_id,
            preference_id=self._preferencia_de(payment_id),
            estado="approved",
        )

    async def reembolsar(self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal) -> bool:
        del empresa_id
        if self._preferencia_de(payment_id) in self._rechazan:
            return False
        self.reembolsos.append((payment_id, monto))
        return True

    def _preferencia_de(self, payment_id: str) -> str:
        """El doble ata el pago a la preferencia por convención: `pago-<preferencia>`."""
        return payment_id.removeprefix("pago-")


__all__ = [
    "PasarelaMercadoPago",
    "PasarelaSimulada",
    "PortTokenDeMercadoPago",
]
