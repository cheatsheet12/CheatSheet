"""Puertos de `payments` que el envío real de recordatorios necesita (U5, ADR-0011).

Salieron de `ports.py` y de `ports_de_recordatorios.py` para no crecer ninguno de los dos: cada
uno es un contrato del *consumidor* (`recordatorios.py` y el adaptador de envío).
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class FallaDelCanal(Exception):
    """El canal de WhatsApp no aceptó el mensaje, con el motivo ya traducido (U7, D2).

    Es la excepción **de `payments`**: la raíz de composición traduce los errores tipados de
    `conversational` a esta (R3), y el adaptador de envío la lee sin importar a ese contexto.
    `codigo` es un código de Meta (`"131047"`) o una clase corta (`"INCIERTO"`); nunca el texto del
    error, que puede traer el número.
    """

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True, slots=True)
class ContactoDeCobro:
    """A quién se le escribe un recordatorio: el nombre y el teléfono, nada más."""

    nombre: str
    telefono: str


class PortContactoDeCliente(Protocol):
    """El contacto de un cliente, **sólo para el adaptador de envío**.

    Puerto aparte y no un método más de `PortClienteDeCobro`, a propósito: ese puerto no expone
    el contacto (D92) y el caso de uso de cobros sigue sin verlo. Mismo patrón que
    `scheduling` (`PortDirectorioDeClientes.contacto_de`).

    Devuelve `None` si el cliente no existe o no tiene un WhatsApp registrado.
    """

    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None: ...


class PortAislamiento(Protocol):
    """Pide un savepoint sin que `application/` importe SQLAlchemy (R2).

    Lo que pasa adentro del bloque se confirma o se deshace **solo**, sin tocar el resto de la
    transacción. Es lo que permite al barrido de recordatorios despachar varios cobros en una
    sola transacción sin que el fallo del K deshaga las filas de los K-1 cuyos mensajes ya
    salieron (si las deshiciera, el barrido siguiente los mandaría de nuevo).

    Si la base rechaza algo adentro, el bloque se deshace y **sale `DespachoNoPersistido`**;
    cualquier otra excepción se propaga tal cual, también deshaciendo el bloque.
    """

    def aislar(self) -> AbstractAsyncContextManager[None]: ...


__all__ = ["ContactoDeCobro", "FallaDelCanal", "PortAislamiento", "PortContactoDeCliente"]
