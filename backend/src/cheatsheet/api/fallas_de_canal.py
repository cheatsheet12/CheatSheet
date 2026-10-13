"""Los fallos del canal de WhatsApp, traducidos al vocabulario de cada consumidor (U7, D2).

`conversational` levanta errores tipados (`MensajeRechazado`, `MensajeriaSaturada`, `EnvioIncierto`,
`CanalNoConectado`) con el código de Meta. `payments` y `scheduling` no pueden importarlos (R3) y
necesitan el **motivo** para mostrarlo (PAN-COB-02, el hilo). Solo la raíz de composición ve los dos
lados, así que acá se envuelve el canal: lo que el contexto consumidor recibe es **su propia**
excepción, declarada en su módulo de puertos, con el motivo ya traducido.

El patrón es el de `_RevisionViaMeta` en `mensajeria.py`. El motivo es un código o una clase corta
(`motivo_de_falla_de`): nunca el texto del error, que puede traer el número del cliente.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from cheatsheet.contexts.conversational.application.errors import (
    MensajeriaNoDisponible,
    MensajeriaSaturada,
    motivo_de_falla_de,
)


class _Canal(Protocol):
    """Lo que se envuelve: las dos operaciones de un canal de WhatsApp (`PortMensajeria`)."""

    async def enviar(self, *, telefono: str, texto: str) -> str: ...

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str: ...


class _FabricaDeFalla(Protocol):
    def __call__(self, codigo: str, *, transitoria: bool) -> Exception: ...


def _traducir(error: MensajeriaNoDisponible, falla: _FabricaDeFalla) -> Exception:
    """El motivo, más si vale otro intento: solo la saturación lo es (D-U7-3).

    Un código de Meta no alcanza para decidirlo (131056 puede venir de un 429 o de un rechazo): lo
    dice la clase del error. `EnvioIncierto` (timeout de lectura) nunca es transitorio.
    """
    return falla(motivo_de_falla_de(error), transitoria=isinstance(error, MensajeriaSaturada))


class CanalConFallasTraducidas:
    """Un canal que levanta `falla(codigo, transitoria=...)` y no los errores de `conversational`.

    Cualquier otra excepción se propaga tal cual: el adaptador consumidor ya sabe tratarla.
    """

    def __init__(self, canal: _Canal, falla: _FabricaDeFalla) -> None:
        self._canal = canal
        self._falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        try:
            return await self._canal.enviar(telefono=telefono, texto=texto)
        except MensajeriaNoDisponible as exc:
            raise _traducir(exc, self._falla) from exc

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        try:
            return await self._canal.enviar_plantilla(
                telefono=telefono, nombre=nombre, idioma=idioma, parametros=parametros
            )
        except MensajeriaNoDisponible as exc:
            raise _traducir(exc, self._falla) from exc


__all__ = ["CanalConFallasTraducidas"]
