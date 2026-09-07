"""Dónde quedan los reportes y los paquetes: el mismo almacenamiento del resto del sistema.

`platform/almacenamiento.py` ya sirve a `spreadsheet_sync` (la planilla subida) y a `billing`
(el PDF del comprobante). Este contexto es el tercer consumidor y **no trae otro adaptador**:
lo que se comparte es el adaptador, y el puerto lo declara cada consumidor —que es lo que
hexagonal pide y lo que la regla R3 permite—.

La traducción que hace esta clase es de una línea y vale la pena: el almacenamiento devuelve
un `ArchivoGuardado` con la clave y el tamaño, y `PortArchivos` sólo quiere la referencia con
la que después va a pedir los bytes. Guardar el objeto entero obligaría al dominio de
`reporting` a conocer un tipo de `platform/`.
"""

from __future__ import annotations

from typing import Protocol

from cheatsheet.platform.almacenamiento import ArchivoGuardado


class AlmacenamientoDeArchivos(Protocol):
    """La forma que `platform/almacenamiento.py` expone. Declarada acá para no importar sus
    clases concretas: lo que este módulo necesita es la operación, no la implementación."""

    async def guardar(
        self, *, clave: str, contenido: bytes, tipo_de_contenido: str
    ) -> ArchivoGuardado: ...

    async def leer(self, clave: str) -> bytes: ...


class ArchivosDeReporteria:
    """`PortArchivos` sobre el almacenamiento de objetos.

    **La referencia que devuelve es la clave.** No una URL: una URL firmada vence, y lo que se
    guarda en la fila del reporte tiene que seguir sirviendo dentro de un año, que es cuando
    alguien va a volver a bajar el reporte de un ejercicio cerrado.
    """

    def __init__(self, almacenamiento: AlmacenamientoDeArchivos) -> None:
        self._almacenamiento = almacenamiento

    async def guardar(self, *, clave: str, contenido: bytes, tipo: str) -> str:
        guardado = await self._almacenamiento.guardar(
            clave=clave, contenido=contenido, tipo_de_contenido=tipo
        )
        return guardado.clave

    async def leer(self, clave: str) -> bytes:
        return await self._almacenamiento.leer(clave)


__all__ = ["AlmacenamientoDeArchivos", "ArchivosDeReporteria"]
