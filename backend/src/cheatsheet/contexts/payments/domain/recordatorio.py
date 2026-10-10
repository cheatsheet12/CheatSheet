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
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.externo_id import externo_id_o_ninguno

#: El largo de la columna `recordatorio.ultimo_error` (migración 0038).
LARGO_MAXIMO_ULTIMO_ERROR = 60

#: Intentos en total entre barridos (U7, D-U7-3), además de los 3 que ya hace el canal dentro de
#: cada llamada. El barrido es horario: con esperas de 1 h y 2 h un recordatorio caído se resuelve
#: en ~3 h o queda `FALLIDO`; más que eso convertiría un «a los 3 días» en «a los 4».
REINTENTOS_MAXIMOS = 3
#: La espera tras el intento `n` es `ESPERA_BASE * 2 ** (n - 1)`: 1 h, 2 h.
ESPERA_BASE = timedelta(hours=1)
#: Cuánto puede tardar un envío en curso antes de darlo por perdido, **medido desde que se reservó**
#: (reloj real, no el del inicio del barrido). Un envío son segundos (el canal tiene sus tiempos de
#: espera y 3 intentos propios); pasada la ventana, quien lo encuentre sabe que el proceso murió
#: **después de empezar** y no puede saber si Meta lo aceptó. Menor que el período del barrido
#: (1 h): el barrido siguiente ya la ve vencida.
VENTANA_DE_ENVIO = timedelta(minutes=30)
#: Motivos de `ultimo_error` que no son un código de Meta.
COBRO_CERRADO = "COBRO_CERRADO"
INCIERTO = "INCIERTO"


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
    #: Cuántos intentos de envío **empezaron** (U7, migración 0039). Se cuenta al empezar, no al
    #: terminar: si el proceso muere a mitad del envío, el intento ya figura.
    intentos: int = 0
    #: Según el estado de la fila: cuándo vence el envío en curso, o cuándo toca el reintento.
    proximo_intento_en: datetime | None = None

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
        self.proximo_intento_en = None
        self.ultimo_error = None

    # ------------------------------------------------------------ reintento (U7, D-U7-3)
    #
    # Estados de una fila, por sus columnas (`enviado_en` / `intentos` / `proximo_intento_en` /
    # `ultimo_error`): sin intentar (nulo/0/nulo/nulo), envío en curso (nulo/n/ventana/nulo),
    # esperando reintento (nulo/n/espera/código), enviada o fallida (con fecha) y descartada
    # (nulo/n/nulo/`COBRO_CERRADO`).

    def iniciar_intento(self, ahora: datetime) -> None:
        """Empieza un envío: cuenta el intento y abre la ventana. Se confirma **antes** de Meta."""
        self.intentos += 1
        self.proximo_intento_en = ahora + VENTANA_DE_ENVIO
        self.ultimo_error = None

    def registrar_falla(self, ahora: datetime, *, codigo: str, transitoria: bool) -> bool:
        """Cierra un intento fallido. Devuelve `True` si queda programado otro.

        Solo una falla **transitoria** con intentos disponibles espera. Una permanente (4xx de
        Meta) o una incierta (timeout de lectura: Meta pudo haberlo aceptado y no hay clave de
        idempotencia, ADR-0011 punto 6) deja la fila `FALLIDO` y despachada: la cadena sigue.
        """
        if transitoria and self.intentos < REINTENTOS_MAXIMOS:
            self.proximo_intento_en = ahora + ESPERA_BASE * 2 ** (self.intentos - 1)
            self.ultimo_error = codigo[:LARGO_MAXIMO_ULTIMO_ERROR]
            return True
        self.fallar(ahora, codigo)
        return False

    def fallar(self, ahora: datetime, codigo: str) -> None:
        """Termina la fila como `FALLIDO`, con su fecha: el paso se da por hecho."""
        self.enviado_en = ahora
        self.estado_entrega = EstadoEntrega.FALLIDO
        self.proximo_intento_en = None
        self.ultimo_error = codigo[:LARGO_MAXIMO_ULTIMO_ERROR]

    def descartar(self) -> None:
        """El cobro se cerró mientras la fila esperaba: no se manda nada y no es una falla."""
        self.enviado_en = None
        self.estado_entrega = None
        self.proximo_intento_en = None
        self.ultimo_error = COBRO_CERRADO

    @property
    def descartado(self) -> bool:
        return self.enviado_en is None and self.ultimo_error == COBRO_CERRADO

    @property
    def sin_intentar(self) -> bool:
        """Ningún envío empezó: mandarla es seguro (nada pudo haber salido)."""
        return self.enviado_en is None and self.intentos == 0 and not self.descartado

    @property
    def envio_en_curso(self) -> bool:
        return (
            self.enviado_en is None
            and self.intentos > 0
            and self.proximo_intento_en is not None
            and self.ultimo_error is None
        )

    @property
    def esperando_reintento(self) -> bool:
        return (
            self.enviado_en is None
            and self.proximo_intento_en is not None
            and self.ultimo_error is not None
            and not self.descartado
        )

    def envio_perdido(self, ahora: datetime) -> bool:
        """Un envío empezó y su ventana venció sin resultado: el proceso murió a mitad.

        Es el caso clásico del resultado **incierto**: Meta pudo haberlo aceptado. Se resuelve
        como `FALLIDO` `INCIERTO`, nunca se reenvía.
        """
        return (
            self.envio_en_curso
            and self.proximo_intento_en is not None
            and self.proximo_intento_en <= ahora
        )

    def corresponde_intentar(self, ahora: datetime) -> bool:
        """Si le toca a un barrido tocar esta fila: sin intentar, o con su fecha cumplida."""
        if self.sin_intentar:
            return True
        return (
            self.enviado_en is None
            and not self.descartado
            and self.proximo_intento_en is not None
            and self.proximo_intento_en <= ahora
        )

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


__all__ = [
    "COBRO_CERRADO",
    "ESPERA_BASE",
    "INCIERTO",
    "LARGO_MAXIMO_ULTIMO_ERROR",
    "REINTENTOS_MAXIMOS",
    "VENTANA_DE_ENVIO",
    "EstadoEntrega",
    "Recordatorio",
    "proximo_paso",
]
