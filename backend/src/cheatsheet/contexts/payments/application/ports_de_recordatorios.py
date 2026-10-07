"""Puertos de `payments` para los recordatorios (HS-T3).

Salieron de `ports.py`, que llegó al tope de 400 líneas (`CLAUDE.md` §5): es un bloque cohesivo
que solo usa `recordatorios.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.shared.empresa import EmpresaId


@dataclass(frozen=True, slots=True)
class ResultadoDeEnvio:
    """Cómo terminó un envío: el estado, el `wamid` si Meta lo aceptó y el motivo si falló (U7).

    `externo_id` es lo que permite que un callback `statuses[]` encuentre su recordatorio.
    `codigo` es un código de Meta o una clase corta (`INCIERTO`, `SIN_TELEFONO`...): nunca el texto
    de un error, que puede traer el número.
    """

    estado: EstadoEntrega
    externo_id: str | None = None
    codigo: str | None = None
    #: Solo con `FALLIDO`: si vale otro intento en un barrido posterior (D-U7-3). Un rechazo
    #: permanente, un resultado incierto o un error propio nunca lo son.
    transitoria: bool = False


@dataclass(frozen=True, slots=True)
class PlantillaLista:
    """Una plantilla aprobada ya resuelta: cómo se llama en Meta, su idioma y sus parámetros."""

    nombre_en_meta: str
    idioma: str
    parametros: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class MensajeListo:
    """Un recordatorio **ya armado**, que sale por el canal sin una lectura más (U7, S1).

    Lo produce `PortEnvioDeRecordatorio.preparar` (que lee el contacto y la plantilla) y lo consume
    `mandar` (que solo habla con el canal). Lleva `texto` **o** `plantilla`. Es dato personal: el
    teléfono, el texto y los parámetros quedan fuera del `repr`, para que ningún log los arrastre.
    """

    cobro_id: UUID
    paso: int
    canal: str
    telefono: str = field(repr=False)
    texto: str | None = field(default=None, repr=False)
    plantilla: PlantillaLista | None = field(default=None, repr=False)


class PortEnvioDeRecordatorio(Protocol):
    """Por dónde sale un recordatorio (HS-T3 RN-02), en dos tiempos (U7, S1).

    **Preparar** lee lo que el mensaje necesita (contacto, plantilla) y **mandar** solo habla con el
    canal. Se separan para que la llamada a Meta no haga E/S contra la base: un error de base
    después de reservar abortaría la transacción de todo el barrido, y el envío quedaría
    resuelto `INCIERTO` sin que nada hubiera salido.

    `mandar` devuelve el resultado del canal, para que RN-04 tenga qué registrar y el callback de
    estado pueda encontrar el recordatorio después. **Nunca levanta.**
    """

    async def preparar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> MensajeListo | ResultadoDeEnvio:
        """El mensaje listo, o el resultado `FALLIDO` si ya se sabe que no puede salir.

        Corre **dentro del savepoint de la reserva**: lo único que puede levantar es lo que la base
        rechaza (se deshace el savepoint y no queda fila). Cualquier otra falla es un
        `ResultadoDeEnvio` `FALLIDO`; un cobro sin teléfono es `SIN_TELEFONO`.
        """
        ...

    async def mandar(self, mensaje: MensajeListo) -> ResultadoDeEnvio: ...


@dataclass(frozen=True, slots=True)
class PasoDeCadena:
    """Un eslabón de la cadena de escalamiento, en el vocabulario de `payments`.

    **`business_config` tiene su propia clase con la misma forma**, y esa duplicación es la
    correcta: un puerto es el contrato del *consumidor*. La regla R3 impide que este contexto
    importe el dominio del otro, y la traducción vive en el ACL de `infrastructure/` -- que es
    exactamente lo que ADR-0003 pide.

    `dias` se cuenta desde el **vencimiento** del cobro, no desde el paso anterior.
    """

    dias: int
    canal: str


class PortCadenaDeEscalamiento(Protocol):
    """Cuál es la cadena de recordatorios de esta empresa (HU-E11-01 RN-02).

    Devuelve los pasos ya ordenados y ya resueltos por prioridad: la resolución de RN-05 es
    cosa de `business_config`, y este contexto recibe la respuesta, no las filas.

    **Nunca devuelve una lista vacía.** Sin regla configurada devuelve el default, porque
    HS-T3 tiene como precondición que exista una cadena y una empresa que nunca entró a
    PAN-CFG-RN no puede quedarse sin recordatorios y sin enterarse.
    """

    async def pasos(self, *, empresa_id: EmpresaId) -> tuple[PasoDeCadena, ...]: ...


__all__ = [
    "MensajeListo",
    "PasoDeCadena",
    "PlantillaLista",
    "PortCadenaDeEscalamiento",
    "PortEnvioDeRecordatorio",
    "ResultadoDeEnvio",
]
