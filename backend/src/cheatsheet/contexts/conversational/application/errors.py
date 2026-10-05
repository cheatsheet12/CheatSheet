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


class HorarioNoDisponible(EntradaInvalida):
    """El motor de `scheduling` no aceptó el horario (HU-E8-01 CA4 y CA3).

    Se ocupó entre que se ofreció y que se eligió, o quedó fuera de horario, o el recurso dejó de
    prestar el servicio. Para el cliente significa lo mismo, así que el ACL las colapsa: no hay
    nada distinto que decirle.
    """


class HorarioEnElPasado(EntradaInvalida):
    """El horario ofrecido ya pasó mientras el cliente dudaba (HU-E8-01 CA7)."""


class TurnoNoCancelable(EntradaInvalida):
    """El turno ya no está abierto o no existe: otro lo canceló, o lo completó (HU-E8-02)."""


__all__ = [
    "AgenteNoDisponible",
    "ConversacionInexistente",
    "EscalamientoInexistente",
    "EscalamientoNoReabrible",
    "FAQInexistente",
    "HorarioEnElPasado",
    "HorarioNoDisponible",
    "MensajeYaProcesado",
    "MensajeriaNoDisponible",
    "TurnoNoCancelable",
]
