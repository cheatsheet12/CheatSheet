"""Errores de `payments`.

Casi todos derivan de `EntradaInvalida`, y no es un accidente de la herencia: `api/main.py`
mapea el primero a **422 reenviando su texto** y `InvarianteViolada` a un 409 cuyo detalle el
BFF descarta. Cada mensaje de acá lo escribe una historia palabra por palabra —«El monto debe
ser mayor a cero.»— así que tiene que llegar a la pantalla.

Las dos excepciones son deliberadas. `CobroNoCancelable` y `CobroNoReembolsable` son
`InvarianteViolada` porque describen un **estado imposible**, no una entrada mal escrita: el
usuario no puede corregir nada, y su texto igual viaja porque los routers de este contexto lo
reenvían explícitamente.
"""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


class CobroInexistente(EntradaInvalida):
    """No es de esta empresa, o nunca existió. Bajo RLS son la misma respuesta, a propósito:
    distinguirlas le diría a una empresa que el id de un cobro ajeno es real."""


class CobroNoCancelable(InvarianteViolada):
    """HU-E6-04 RN-01: un cobro pagado no se cancela, se reembolsa."""


class CobroNoReembolsable(InvarianteViolada):
    """HU-E6-05 RN-01: solo se reembolsa lo que está aprobado."""


class MontoExcedeSaldo(EntradaInvalida):
    """HU-E6-06 RN-02: el cobro no puede superar el saldo pendiente del comprobante."""


class PasarelaNoDisponible(EntradaInvalida):
    """MercadoPago no respondió. **Distinto de que haya dicho que no.**

    La diferencia es la misma que `billing` mantiene con ARCA, y por el mismo motivo: no poder
    preguntar es reintentable y no dice nada sobre la operación; un rechazo es una respuesta.
    Colapsarlas convertiría una caída de MercadoPago en un reembolso rechazado.
    """


class ReembolsoRechazado(EntradaInvalida):
    """MercadoPago rechazó el reembolso (RN-03). El cobro mantiene su estado `APROBADO`."""


class RecordatorioDuplicado(EntradaInvalida):
    """El índice único `(cobro_id, paso)` frenó un segundo despacho del mismo paso.

    Es la idempotencia de HS-T3 RN-05 hecha excepción: el barrido la atrapa y sigue con el
    cobro siguiente, porque significa «esto ya salió», que no es un error.
    """


class WebhookNoAutentico(EntradaInvalida):
    """HS-T1 RN-01. Se registra y se descarta **con 200** (decisión D22).

    Un 401 le diría a MercadoPago «reintentá», y reintentaría durante horas una notificación
    que nunca va a validar.
    """


__all__ = [
    "CobroInexistente",
    "CobroNoCancelable",
    "CobroNoReembolsable",
    "MontoExcedeSaldo",
    "PasarelaNoDisponible",
    "RecordatorioDuplicado",
    "ReembolsoRechazado",
    "WebhookNoAutentico",
]
