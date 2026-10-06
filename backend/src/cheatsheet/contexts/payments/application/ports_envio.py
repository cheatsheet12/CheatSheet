"""Puertos de `payments` que el envío real de recordatorios necesita (U5, ADR-0011).

Salieron de `ports.py` y de `ports_de_recordatorios.py` para no crecer ninguno de los dos: cada
uno es un contrato del *consumidor* (`recordatorios.py` y el adaptador de envío).
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol


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


__all__ = ["PortAislamiento"]
