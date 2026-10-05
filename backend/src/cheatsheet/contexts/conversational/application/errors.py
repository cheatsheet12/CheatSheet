"""Errores de `conversational`.

Como en el resto del sistema, casi todos derivan de `EntradaInvalida` porque `api/main.py`
mapea ése a **422 reenviando el texto**, y varios de estos mensajes los escriben las historias.

`MensajeYaProcesado` es la única que no es un error de verdad: es la idempotencia del webhook
de Meta hecha excepción, y quien la atrapa la trata como «esto ya pasó» y contesta 200.
"""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida


class ConversacionInexistente(EntradaInvalida):
    """No es de esta empresa, o nunca existió. Bajo RLS son la misma respuesta, a propósito."""


class EscalamientoInexistente(EntradaInvalida):
    """Ídem."""


class FAQInexistente(EntradaInvalida):
    """Ídem."""


class EscalamientoNoReabrible(EntradaInvalida):
    """HU-E9-02 RN-04: un escalamiento cerrado no se reabre.

    **`EntradaInvalida` y no `InvarianteViolada`**, aunque describa un estado imposible más que
    una entrada mal escrita. El motivo es concreto y se midió: el BFF reenvía el `detalle` sólo
    en un 422 (`respuestaDeError` en `app/api/auth/_sesion.ts`), y la historia no pide sólo
    negar la operación — pide que el sistema **indique** que un nuevo pedido del cliente genera
    un escalamiento nuevo. Con un 409, esa frase no llega a la pantalla.
    """


class MensajeYaProcesado(EntradaInvalida):
    """Meta reintentó una notificación que ya procesamos.

    **No es un error**: es la garantía funcionando. Quien la atrapa contesta 200 sin hacer
    nada, igual que el webhook de MercadoPago del épico 6.
    """


class AgenteNoDisponible(EntradaInvalida):
    """El modelo no contestó. **Distinto de que haya dicho que no entiende.**

    La diferencia es la misma que `billing` mantiene con ARCA y `payments` con MercadoPago: no
    poder preguntar es reintentable y no dice nada sobre el mensaje; «no entendí» es una
    respuesta, y su consecuencia es un escalamiento.
    """


class MensajeriaNoDisponible(EntradaInvalida):
    """WhatsApp no aceptó el mensaje saliente.

    Se registra y **no voltea** lo que ya pasó: un turno reservado sigue reservado aunque la
    confirmación no haya salido. Es la misma decisión D33 del épico 7.
    """


class ClienteSinWhatsApp(EntradaInvalida):
    """El cliente dueño del hilo no tiene un WhatsApp registrado en `master_data`.

    El destino del operador sale del cliente de la conversación y de ningún otro lado: sin
    número, no hay a dónde escribir, y no se envía ni se guarda nada.
    """


__all__ = [
    "AgenteNoDisponible",
    "ClienteSinWhatsApp",
    "ConversacionInexistente",
    "EscalamientoInexistente",
    "EscalamientoNoReabrible",
    "FAQInexistente",
    "MensajeYaProcesado",
    "MensajeriaNoDisponible",
]
