"""El webhook de MercadoPago (HS-T1).

**Es la única ruta del sistema sin `EmpresaMiddleware` delante**, y eso hay que decirlo
fuerte: MercadoPago no manda una sesión ni un JWT. La empresa se deduce de la URL —el webhook
se registra por empresa al conectar la cuenta— y la autenticidad, de la firma.

Tres decisiones del épico se ven acá:

- **D22 — una firma inválida se registra y contesta 200.** Un 401 le diría a MercadoPago
  «reintentá», y reintentaría durante horas una notificación que nunca va a validar. La firma
  inválida no es un error transitorio.
- **D21 — el pago se persiste dentro del request.** Contestar 200 y encolar todo es más rápido
  y pierde el pago si el encolado falla. Un webhook que contestó 200 es un webhook cuyo pago
  está guardado.
- **D20 — la idempotencia es el `payment_id`.** Vive en el caso de uso y en el índice único,
  no acá.

**Nada de lo que MercadoPago manda se cree sin verificar.** El cuerpo trae un id; el estado se
consulta contra la API con nuestro token. Un atacante que adivine un id de pago no puede
hacer que un cobro pase a aprobado, porque el estado no sale de su mensaje.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mercadopago import armar_pasarela, armar_saldos
from cheatsheet.contexts.payments.application.confirmacion import (
    ConfirmarPago,
    RegistrarWebhookRechazado,
)
from cheatsheet.contexts.payments.application.errors import PasarelaNoDisponible
from cheatsheet.contexts.payments.infrastructure.ensamblado import Cobros
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from fastapi import APIRouter, Request, Response, status

logger = obtener_logger(__name__)

#: Las cabeceras con las que MercadoPago firma. `x-signature` trae `ts=...,v1=...`.
CABECERA_FIRMA = "x-signature"
CABECERA_PEDIDO = "x-request-id"


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["payments"])
    router.include_router(_rutas(recursos), prefix="/webhooks")
    return router


def _rutas(recursos: Recursos) -> APIRouter:
    router = APIRouter()

    @router.post("/mercadopago/{empresa_id}", status_code=status.HTTP_200_OK)
    async def recibir(request: Request, empresa_id: UUID) -> Response:
        """Recibe una notificación de pago.

        **Contesta 200 en todos los caminos que no sean un fallo nuestro**, y eso es
        deliberado: MercadoPago reintenta ante cualquier cosa que no sea 2xx, y hay
        exactamente un motivo legítimo para querer que reintente — que nosotros no hayamos
        podido procesarlo. Una firma inválida (D22), un pago que no es nuestro o una
        notificación repetida no son eso.
        """
        empresa = EmpresaId(empresa_id)
        crudo = await request.body()

        if not _firma_valida(request, crudo, recursos.settings.mercadopago_webhook_secret):
            # HS-T1 RN-01. Se registra el intento y se contesta 200 (D22).
            async for unidad in unidad_de_trabajo(recursos, empresa):
                await RegistrarWebhookRechazado(unidad.publicador).ejecutar(
                    empresa_id=empresa, motivo="firma_invalida", ahora=unidad.reloj.ahora()
                )
            return Response(status_code=status.HTTP_200_OK)

        payment_id = _payment_id_de(await _json(request, crudo))
        if payment_id is None:
            # MercadoPago manda eventos de muchos tipos por el mismo endpoint —
            # `merchant_order`, `plan`, `subscription`. Los que no son un pago no son un
            # error y no deben provocar un reintento.
            logger.info("webhook_sin_pago", empresa_id=str(empresa))
            return Response(status_code=status.HTTP_200_OK)

        try:
            async for unidad in unidad_de_trabajo(recursos, empresa):
                piezas = Cobros.armar(unidad)
                await ConfirmarPago(
                    cobros=piezas.cobros,
                    pasarela=armar_pasarela(unidad, recursos.settings),
                    saldos=armar_saldos(unidad),
                    publicador=unidad.publicador,
                ).ejecutar(empresa_id=empresa, payment_id=payment_id, ahora=unidad.reloj.ahora())
        except PasarelaNoDisponible:
            # **El único caso en que queremos que reintente.** No pudimos preguntarle a
            # MercadoPago qué pasó, así que todavía no sabemos si hay un pago que registrar.
            logger.warning("webhook_sin_poder_consultar", payment_id=payment_id)
            return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(status_code=status.HTTP_200_OK)

    return router


def _firma_valida(request: Request, cuerpo: bytes, secreto: str) -> bool:
    """HS-T1 RN-01 — HMAC-SHA256 sobre el manifiesto que MercadoPago arma.

    **Sin secreto configurado, ninguna firma vale.** Es lo contrario de lo cómodo: lo cómodo
    sería aceptar todo mientras no haya secreto, y eso convierte un despliegue mal configurado
    en un endpoint público que mueve el estado de los cobros.

    La comparación es `compare_digest` y no `==`: comparar HMACs con `==` filtra por tiempo
    cuántos bytes coinciden, que es lo que permite construir una firma válida a fuerza de
    intentos.
    """
    if not secreto:
        return False

    firma = request.headers.get(CABECERA_FIRMA, "")
    partes = dict(pieza.split("=", 1) for pieza in firma.split(",") if "=" in pieza)
    marca, recibida = partes.get("ts", "").strip(), partes.get("v1", "").strip()
    if not marca or not recibida:
        return False

    # El manifiesto es el que MercadoPago documenta: id del recurso, id del pedido y marca de
    # tiempo. Se arma con lo que llega, y la firma es lo que dice si eso llegó de ellos.
    recurso = request.query_params.get("data.id") or request.query_params.get("id") or ""
    pedido = request.headers.get(CABECERA_PEDIDO, "")
    manifiesto = f"id:{recurso};request-id:{pedido};ts:{marca};"
    esperada = hmac.new(secreto.encode(), manifiesto.encode(), hashlib.sha256).hexdigest()

    if hmac.compare_digest(esperada, recibida):
        return True

    # Algunos entornos de MercadoPago firman el cuerpo crudo en vez del manifiesto. Se acepta
    # cualquiera de las dos, y **ninguna otra**: probar dos formas conocidas no es lo mismo
    # que aceptar lo que venga.
    alternativa = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(alternativa, recibida)


async def _json(request: Request, crudo: bytes) -> dict[str, Any]:
    """El cuerpo, o un diccionario vacío. Un JSON roto no es una excepción del servidor."""
    del request
    if not crudo:
        return {}
    try:
        import json

        datos = json.loads(crudo)
    except ValueError:
        logger.warning("webhook_cuerpo_ilegible")
        return {}
    return datos if isinstance(datos, dict) else {}


def _payment_id_de(cuerpo: dict[str, Any]) -> str | None:
    """El id del pago, si la notificación es de un pago.

    MercadoPago manda dos formas —`{"type": "payment", "data": {"id": …}}` y el viejo
    `{"topic": "payment", "resource": …}`— y las dos siguen llegando. Leer sólo una haría que
    la mitad de las notificaciones se descartaran en silencio.
    """
    tipo = str(cuerpo.get("type") or cuerpo.get("topic") or "")
    if tipo != "payment":
        return None
    datos = cuerpo.get("data")
    if isinstance(datos, dict) and datos.get("id"):
        return str(datos["id"])
    recurso = cuerpo.get("resource") or cuerpo.get("id")
    return str(recurso).rsplit("/", 1)[-1] if recurso else None
