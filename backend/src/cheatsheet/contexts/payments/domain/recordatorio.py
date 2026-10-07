"""`Recordatorio` — un eslabón de la cadena de escalamiento (HS-T3).

Entidad interna del agregado `Cobro`: no se consulta suelta y no tiene ciclo de vida propio.
Lo que la hace importante es la columna `paso`, y el DER lo dice: «es lo que hace verificable
la cadena de escalamiento de HS-T3: el recordatorio número N se envía una sola vez».

**La idempotencia de RN-05 vive en el índice único `(cobro_id, paso)`**, no en una ventana de
tiempo. Es la decisión **D25** y la diferencia se nota cuando el planificador se atrasa: un
barrido basado en fechas manda los tres pasos atrasados de golpe; uno basado en el paso manda
el que falta, y el siguiente en la corrida siguiente. Un cliente que recibe tres mensajes en
un minuto es peor que uno que los recibe tarde.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.externo_id import externo_id_o_ninguno

#: El largo de la columna `recordatorio.ultimo_error` (migración 0037).
LARGO_MAXIMO_ULTIMO_ERROR = 60


class EstadoEntrega(StrEnum):
    """El enum `estado_entrega` del DER (HS-T3 RN-04).

    Los cuatro estados son los que WhatsApp Business reporta, y por eso `LEIDO` existe aunque
    ningún email lo informe: el canal que más se usa sí lo hace, y HU-E6-02 RN-01 pide
    mostrar «estado de lectura» en el detalle.
    """

    ENVIADO = "ENVIADO"
    ENTREGADO = "ENTREGADO"
    LEIDO = "LEIDO"
    FALLIDO = "FALLIDO"


@dataclass(slots=True)
class Recordatorio:
    """Un mensaje de la cadena, con su lugar en ella.

    `enviado_en` nulo significa **programado y todavía no despachado**. No es un estado
    aparte: la ausencia de fecha ya lo dice, y agregar un enum de tres valores para
    representar lo que un `NULL` representa sería duplicar la misma información en dos
    columnas que pueden discrepar.
    """

    id: UUID
    cobro_id: UUID
    paso: int
    canal: str
    enviado_en: datetime | None = None
    estado_entrega: EstadoEntrega | None = None
    #: El `wamid` con el que Meta aceptó el mensaje: así un callback `statuses[]` lo encuentra.
    externo_id: str | None = None
    #: Por qué falló: un código de Meta o una clase corta. Nunca el texto que devolvió el canal.
    ultimo_error: str | None = None

    def __post_init__(self) -> None:
        if self.paso < 1:
            # Contar desde 1 y no desde 0: `paso` es una columna que alguien va a leer en una
            # consulta, y «paso 0» no significa nada para quien la mire.
            raise EntradaInvalida("El paso de un recordatorio empieza en 1")

    def marcar_enviado(self, ahora: datetime, externo_id: str | None = None) -> None:
        """Salió por el canal. El proveedor confirmará la entrega después, o no.

        Un `externo_id` vacío o que no entra en la columna se guarda como `None`, nunca cortado: el
        mensaje salió y el paso se da por despachado igual (si no, el barrido lo mandaría otra vez
        y el cliente recibiría el recordatorio dos veces). Solo se pierde el estado de entrega.
        """
        self.enviado_en = ahora
        self.estado_entrega = EstadoEntrega.ENVIADO
        self.externo_id = externo_id_o_ninguno(externo_id)

    def marcar_entrega(self, estado: EstadoEntrega, *, motivo: str | None = None) -> bool:
        """Lo que el proveedor informó (RN-04). **Solo avanza**; devuelve si cambió algo (U7).

        Orden: `ENVIADO < ENTREGADO < LEIDO < FALLIDO`. WhatsApp no garantiza el orden de los
        callbacks, y con «lo último que llega vale» un `delivered` retrasado pisaría un `read`.
        El orden admite saltos (`LEIDO` sin `ENTREGADO`: Meta no manda `delivered` cuando las dos
        cosas pasan a la vez) y solo prohíbe retroceder o repetir. `FALLIDO` es el veredicto
        final de Meta sobre ese `wamid`. Es la misma regla que `Mensaje` en `conversational`; la
        tabla de orden se duplica a propósito (R3). `motivo` solo se guarda al pasar a `FALLIDO`.
        """
        orden = {
            EstadoEntrega.ENVIADO: 0,
            EstadoEntrega.ENTREGADO: 1,
            EstadoEntrega.LEIDO: 2,
            EstadoEntrega.FALLIDO: 3,
        }
        if self.estado_entrega is not None and orden[estado] <= orden[self.estado_entrega]:
            return False
        self.estado_entrega = estado
        if estado is EstadoEntrega.FALLIDO and motivo:
            self.ultimo_error = motivo[:LARGO_MAXIMO_ULTIMO_ERROR]
        return True

    @property
    def fue_despachado(self) -> bool:
        return self.enviado_en is not None


def proximo_paso(recordatorios: list[Recordatorio]) -> int:
    """Cuál es el paso que sigue. **Decisión D25.**

    Pregunta «cuál es el máximo ya enviado» y devuelve el siguiente, en vez de mirar cuándo
    fue el último. Con la lista vacía devuelve 1, que es lo que corresponde a un cobro que
    todavía no recibió nada.

    Cuenta los **despachados**, no los creados: una fila sin `enviado_en` es un recordatorio
    que se programó y no salió, y darlo por hecho saltearía un eslabón de la cadena.
    """
    despachados = [uno.paso for uno in recordatorios if uno.fue_despachado]
    return max(despachados, default=0) + 1


__all__ = ["LARGO_MAXIMO_ULTIMO_ERROR", "EstadoEntrega", "Recordatorio", "proximo_paso"]
