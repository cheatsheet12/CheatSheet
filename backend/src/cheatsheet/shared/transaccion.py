"""Envío en tres tiempos: los contratos que comparten `payments` y `scheduling` (U7, U8).

Los dos `Protocol` y el error que levantan no tienen framework ni lógica de un contexto: son del
Shared Kernel (R4). Sus adaptadores sobre SQLAlchemy viven en `platform/transaccion.py`; el
orquestador de cada contexto (`payments/application/reintentos.py`,
`scheduling/application/envio_de_recordatorios.py`) queda donde está.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from cheatsheet.shared.errors import ErrorDeDominio


class DespachoNoPersistido(ErrorDeDominio):
    """La base rechazó algo dentro del savepoint de un ítem del barrido (U5, H1).

    Lo levanta el adaptador del aislamiento cuando un `SQLAlchemyError` sale del bloque. El
    barrido lo registra y sigue con el cobro siguiente: sólo se deshacen las filas de **ese**
    cobro. No lleva datos de la excepción original: puede traer valores de la fila.
    """


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


class PortTransaccion(Protocol):
    """Confirma lo hecho hasta ahora, **antes** de hablar con Meta (U7, D-U7-3, H1).

    El barrido de recordatorios corre en la unidad de trabajo de la empresa, que confirma recién al
    final: un callback `failed` o `delivered` que llegara antes del commit no encontraría la fila y
    se perdería. Con este puerto cada recordatorio confirma su fila antes de la E/S a Meta y su
    resultado después, en una transacción corta aparte.

    **Qué garantiza y qué no (N1).** La llamada a Meta corre **sin escrituras sin confirmar y sin
    locks**, y sin leer la base. No corre «sin transacción abierta»: la implementación vuelve a
    declarar la empresa de la sesión (el `SET LOCAL` muere con el commit), y eso abre una
    transacción nueva y vacía.

    Si la base rechaza el commit, levanta `DespachoNoPersistido` y lo no confirmado se deshizo (N5:
    p. ej. los cobros que `VencerCobros` movió en el mismo barrido se rehacen en el siguiente). Si el
    commit sale bien y no puede volver a declarar la empresa, puede escapar un `SQLAlchemyError`
    crudo (N6): con la empresa sin declarar RLS no muestra ni deja escribir nada, así que es seguro.
    """

    async def confirmar(self) -> None: ...


__all__ = ["DespachoNoPersistido", "PortAislamiento", "PortTransaccion"]
