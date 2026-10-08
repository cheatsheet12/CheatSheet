"""`PortPasarelaDePago` contra MercadoPago, y su doble.

Cinco operaciones: crear la preferencia, invalidarla, consultar un pago, reembolsar y consultar
un reembolso. El OAuth, el refresco del token y la validación de la conexión son de
`integrations` y ya existen desde el épico 2 — acá sólo se pide el token y se usa.

**Un rechazo no es una caída.** `reembolsar` devuelve `RECHAZADO` y no levanta cuando
MercadoPago dice que no (HU-E6-05 RN-03): eso es una respuesta, y el cobro mantiene su estado.
Lo que sí levanta es no poder preguntar, y esa distinción es la misma que `billing` mantiene
con ARCA.

**La clave de idempotencia del reembolso viene de afuera.** Se genera una vez por solicitud, se
guarda, y se reusa en cada reintento (incluso entre requests): una clave nueva por llamada le
permitiría a MercadoPago ejecutar un segundo reembolso.

**`invalidar_link` está del otro lado de esa línea, y a propósito.** Ahí un rechazo no deja el
mundo en un estado conocido: deja un link que el cliente todavía puede pagar (HU-E6-04 RN-03).
Por eso levanta ante cualquier cosa que no sea la confirmación de que la preferencia murió, y
la cancelación entera no ocurre.

**El simulado se niega a construirse en producción**, como los cinco anteriores, y acá con más
en juego que en ninguno: una empresa cobrando contra este doble estaría entregando links que
nadie puede pagar y dando por saldadas deudas que nadie pagó.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx

from cheatsheet.contexts.payments.application.errors import PasarelaNoDisponible
from cheatsheet.contexts.payments.application.ports import (
    EstadoDeReembolso,
    PagoRecibido,
    RespuestaDeReembolso,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.contexts.payments.infrastructure.pasarela_respuestas import (
    fecha_de_aprobacion,
    moneda_de,
    monto_de,
    preferencia_de,
    referencia_de,
    respuesta_de_reembolso,
)
from cheatsheet.contexts.payments.infrastructure.pasarela_simulada import PasarelaSimulada
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId

logger = obtener_logger(__name__)

URL_API = "https://api.mercadopago.com"
TIMEOUT_SEGUNDOS = 15.0
MAX_INTENTOS = 3

#: 4xx que **no** son un rechazo de negocio al pedir un reembolso: no dicen que MercadoPago no
#: lo hizo. 401/403 son credenciales (no llegó a evaluarse); 408/425/429 son "no ahora"; y 409
#: es "clave en uso / ya procesado", que tras un timeout puede significar que el reembolso YA
#: existe. Tomarlos como rechazo borraría la clave y un reintento con clave nueva reembolsaría
#: dos veces, así que se tratan como "no se pudo saber": el reembolso queda en vuelo.
ESTADOS_AMBIGUOS_AL_REEMBOLSAR = frozenset({401, 403, 408, 409, 425, 429})


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
        url_de_notificaciones: str,
        transporte: httpx.AsyncBaseTransport | None = None,
        url_base: str = URL_API,
    ) -> None:
        self._tokens = tokens
        self._url_de_notificaciones = url_de_notificaciones.rstrip("/")
        # `transporte` es como se prueban todos los clientes HTTP de este repositorio:
        # `httpx.MockTransport` va donde iría el socket. Sin él, el parser de la respuesta
        # sólo sería alcanzable metiendo mano en un atributo privado.
        self._transporte = transporte
        self._url_base = url_base

    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        # El monto viaja como el literal exacto del `Decimal`, nunca como `float`
        # (`TODO.md` §20.6): se serializa todo lo demás y después se pone el número en el
        # lugar de una marca que ninguna descripción puede contener.
        marca = f"monto-{uuid4().hex}"
        cuerpo: dict[str, Any] = {
            "items": [
                {
                    "title": cobro.descripcion[:250],
                    "quantity": 1,
                    "unit_price": marca,
                    "currency_id": "ARS",
                }
            ],
            # Lo que ata la notificación a una fila nuestra. Sin esto, el webhook llega con un
            # `payment_id` que no sabemos a quién corresponde.
            "external_reference": str(cobro.id),
            # HS-T1. La URL de la preferencia tiene prioridad sobre la de la aplicación en
            # MercadoPago, que es una sola y no puede llevar la empresa.
            "notification_url": f"{self._url_de_notificaciones}/webhooks/mercadopago/{empresa_id}",
            "back_urls": {"success": url_de_retorno, "failure": url_de_retorno},
            "expires": True,
            "expiration_date_to": cobro.vence_el.isoformat(),
        }
        texto = json.dumps(cuerpo).replace(json.dumps(marca), _numero_json(cobro.monto))
        datos = await self._pedir(
            empresa_id, "POST", "/checkout/preferences", texto, operacion="crear_link"
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
            # El pago de Checkout Pro no trae `preference_id`: se lo ata por `external_reference`
            # (el id del cobro). `preference_id` queda solo por compatibilidad (§20.17).
            preference_id=preferencia_de(datos),
            referencia_externa=referencia_de(datos),
            estado=str(datos.get("status") or ""),
            monto=monto_de(datos),
            moneda=moneda_de(datos),
            fecha_aprobacion=fecha_de_aprobacion(datos),
        )

    async def invalidar_link(
        self, *, empresa_id: EmpresaId, preference_id: str, ahora: datetime
    ) -> None:
        """Adelanta el vencimiento de la preferencia al instante actual (HU-E6-04 RN-03).

        **MercadoPago no tiene un DELETE de preferencias**, y ésta es la operación que sí
        existe: la preferencia se creó con `expires: true`, así que mover `expiration_date_to`
        al ahora deja de aceptar pagos por ese link. Se manda `expires` de nuevo porque el PUT
        reemplaza los campos que toca y la preferencia sin él dejaría de vencer nunca.

        Un rechazo **no** se traga como respuesta, al revés que en `reembolsar`: si
        MercadoPago dijo que no, el link puede seguir cobrando, y la cancelación entera tiene
        que fallar. La única excepción es el 404 — una preferencia que MercadoPago no conoce
        no le puede cobrar a nadie.
        """
        try:
            await self._pedir(
                empresa_id,
                "PUT",
                f"/checkout/preferences/{preference_id}",
                {"expires": True, "expiration_date_to": ahora.isoformat()},
                operacion="invalidar_link",
            )
        except _RechazoDeMercadoPago as exc:
            if exc.estado == httpx.codes.NOT_FOUND:
                logger.info("preferencia_inexistente_al_invalidar", preference_id=preference_id)
                return
            raise PasarelaNoDisponible(f"MercadoPago no invalido el link de pago: {exc}") from exc

    async def reembolsar(
        self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal, clave: UUID
    ) -> RespuestaDeReembolso:
        """Pide el reembolso **de `monto`** (nunca sin `amount`: sería total) con la `clave` dada.

        Un rechazo de negocio (4xx salvo `ESTADOS_AMBIGUOS_AL_REEMBOLSAR`) **es una respuesta** y
        vuelve como `RECHAZADO` con el mensaje de MercadoPago; no poder preguntar (5xx, timeout,
        o un 4xx ambiguo) sí levanta. El `amount` viaja como número
        JSON armado desde el `Decimal`, sin `float`.
        """
        try:
            datos = await self._pedir(
                empresa_id,
                "POST",
                f"/v1/payments/{payment_id}/refunds",
                f'{{"amount": {_numero_json(monto)}}}',
                operacion="reembolsar",
                clave=clave,
            )
        except _RechazoDeMercadoPago as exc:
            if exc.estado in ESTADOS_AMBIGUOS_AL_REEMBOLSAR:
                logger.warning("reembolso_incierto", payment_id=payment_id, estado=exc.estado)
                raise PasarelaNoDisponible(f"MercadoPago no confirmo el reembolso: {exc}") from exc
            logger.warning("reembolso_rechazado", payment_id=payment_id, estado=exc.estado)
            return RespuestaDeReembolso(estado=EstadoDeReembolso.RECHAZADO, motivo=exc.detalle)
        return respuesta_de_reembolso(datos)

    async def consultar_reembolso(
        self, *, empresa_id: EmpresaId, payment_id: str, refund_id: str
    ) -> RespuestaDeReembolso:
        """El estado de un reembolso ya pedido. Un 4xx no dice nada de él: levanta."""
        try:
            datos = await self._pedir(
                empresa_id,
                "GET",
                f"/v1/payments/{payment_id}/refunds/{refund_id}",
                None,
                operacion="consultar_reembolso",
            )
        except _RechazoDeMercadoPago as exc:
            raise PasarelaNoDisponible(f"MercadoPago no informo el reembolso: {exc}") from exc
        return respuesta_de_reembolso(datos, id_conocido=refund_id)

    async def _pedir(
        self,
        empresa_id: EmpresaId,
        metodo: str,
        ruta: str,
        cuerpo: dict[str, Any] | str | None,
        *,
        operacion: str,
        clave: UUID | None = None,
    ) -> dict[str, Any]:
        """`cuerpo` es un dict (se serializa) o **texto ya armado**: un número JSON exacto desde
        un `Decimal` no se puede pedir a `json=`, que no serializa `Decimal` y obligaría a `float`.
        """
        cabeceras = await self._cabeceras(empresa_id, clave)
        # Texto ya armado (`content`) o estructura a serializar (`json`): uno solo de los dos.
        contenido = cuerpo.encode() if isinstance(cuerpo, str) else None
        estructura = None if isinstance(cuerpo, str) else cuerpo
        ultimo: Exception | None = None
        for intento in range(1, MAX_INTENTOS + 1):
            try:
                async with self._cliente() as cliente:
                    respuesta = await cliente.request(
                        metodo,
                        f"{self._url_base}{ruta}",
                        content=contenido,
                        json=estructura,
                        headers=cabeceras,
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

    async def _cabeceras(self, empresa_id: EmpresaId, clave: UUID | None) -> dict[str, str]:
        token = await self._tokens.para(empresa_id)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # MercadoPago usa esta cabecera para deduplicar del lado suyo. No reemplaza a
            # nuestra idempotencia (D20) -- protege el envío, no el procesamiento. La misma
            # clave en los tres intentos; en un reembolso, además, la misma entre requests.
            "X-Idempotency-Key": str(clave or uuid4()),
        }

    def _cliente(self) -> httpx.AsyncClient:
        if self._transporte is not None:
            return httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS, transport=self._transporte)
        return httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS)


class _RechazoDeMercadoPago(Exception):
    """4xx: MercadoPago entendió el pedido y lo rechazó. Interna de este módulo."""

    def __init__(self, estado: int, detalle: str) -> None:
        super().__init__(f"MercadoPago rechazo el pedido ({estado}): {detalle}")
        self.estado = estado
        #: El mensaje de MercadoPago tal cual, para mostrarlo sin traducir.
        self.detalle = detalle


def _cuerpo(respuesta: httpx.Response) -> dict[str, Any]:
    try:
        # `parse_float=Decimal`: un monto se lee desde su texto, sin el error binario del `float`.
        datos = respuesta.json(parse_float=Decimal)
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


def _numero_json(monto: Decimal) -> str:
    """El `Decimal` como literal numérico JSON exacto (`1234.56`), sin pasar por `float`.

    Lo usan el reembolso y el monto de `crear_link` (`TODO.md` §20.6).
    """
    if not monto.is_finite():
        raise ValueError("Un monto no finito no es un numero JSON")
    return format(monto, "f")


__all__ = [
    "PasarelaMercadoPago",
    "PasarelaSimulada",
    "PortTokenDeMercadoPago",
]
