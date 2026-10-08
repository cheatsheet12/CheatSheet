"""Puertos del recordatorio de turno (unidad `recordatorio-de-turno`).

`ports.py` queda como está: estos puertos son del barrido y no de la agenda.

**El envío es en dos tiempos** (`preparar` y `mandar`), como el de los recordatorios de cobro.
`preparar` lee contacto, servicio y plantilla y corre dentro de la reserva; `mandar` solo habla
con el canal y **nunca levanta**: una falla del canal es un resultado, no una excepción. Así el
caso de uso puede llamar al canal sin escrituras sin confirmar ni locks (G5).

`PortAislamiento` y `PortTransaccion`, que el caso de uso del barrido necesita, viven en
`shared/transaccion.py`; no se declaran acá.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import RecordatorioDeTurno
from cheatsheet.contexts.scheduling.domain.turno import Turno


class PortRepositorioRecordatoriosDeTurno(Protocol):
    """Persistencia de las filas de recordatorio, siempre dentro de una empresa (RLS).

    **Sin `eliminar`**: la fila es la prueba de que un aviso ya se atendió, y borrarla permitiría
    mandarlo otra vez.
    """

    async def agregar(self, recordatorio: RecordatorioDeTurno) -> None:
        """Inserta la fila, o levanta `RecordatorioDeTurnoDuplicado` si otro barrido llegó antes.

        La unicidad la decide el índice de la base y no una consulta previa: entre el `SELECT` y
        el `INSERT` cabe otro barrido. El adaptador deja la transacción usable tras el rechazo.
        """
        ...

    async def guardar(self, recordatorio: RecordatorioDeTurno) -> None: ...

    async def buscar_para_actualizar(self, recordatorio_id: UUID) -> RecordatorioDeTurno | None:
        """La fila **bloqueada** y releída de la base (`SELECT ... FOR UPDATE`).

        Es lo que hace que dos barridos solapados no retomen el mismo reintento: el segundo espera
        el commit del primero y ve la ventana ya abierta.
        """
        ...

    async def de_turnos(self, turno_ids: list[UUID]) -> list[RecordatorioDeTurno]:
        """Todas las filas de esos turnos, de cualquier franja y estado."""
        ...

    async def pendientes(self, hasta: datetime) -> list[RecordatorioDeTurno]:
        """Las que no terminaron (`resultado` nulo) y cuyo `proximo_intento_en` ya llegó.

        Son las filas en curso (cuya ventana puede haber vencido) y las que esperan reintento.
        """
        ...


class PortTurnosPorRecordar(Protocol):
    """Lo que el barrido le pide a los turnos: los abiertos que empiezan en un rango."""

    async def abiertos_con_inicio_entre(self, desde: datetime, hasta: datetime) -> list[Turno]:
        """Turnos `RESERVADO` o `CONFIRMADO` con `desde < inicio <= hasta`, por inicio."""
        ...

    async def releer(self, turno_id: UUID) -> Turno | None:
        """El turno **como está ahora en la base**, no como quedó en la sesión.

        Es la relectura del barrido entre reservar y mandar: si se canceló o se movió mientras
        tanto, no se manda. Una lectura por clave de la sesión devolvería el objeto ya cargado.
        """
        ...


class PortAgendaDeNotificacion(Protocol):
    """ACL sobre la regla de agenda de `business_config`."""

    async def anticipaciones(self) -> tuple[int, ...]:
        """Las anticipaciones vigentes, en minutos. Vacía si los recordatorios están apagados."""
        ...


@dataclass(frozen=True, slots=True)
class PlantillaDelRecordatorio:
    """La plantilla **aprobada** por la que sale. Los parámetros llevan el nombre: sin `repr`."""

    nombre: str
    idioma: str
    parametros: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class RecordatorioListo:
    """Todo lo que `mandar` necesita, ya leído. Teléfono y texto quedan fuera del `repr`."""

    turno_id: UUID
    cliente_id: UUID
    anticipacion_min: int
    telefono: str = field(repr=False)
    texto: str = field(repr=False)
    #: La plantilla aprobada, si la hay; sin ella sale el texto de fábrica.
    plantilla: PlantillaDelRecordatorio | None = None


@dataclass(frozen=True, slots=True)
class SinTelefono:
    """El cliente no tiene teléfono: la fila nace `OMITIDO` y no se manda nada."""


@dataclass(frozen=True, slots=True)
class ResultadoDelEnvio:
    """Lo que contestó el canal. Nunca lleva el texto del proveedor, solo un código o clase."""

    enviado: bool
    #: Un código de Meta o una clase corta; nulo si se envió.
    falla: str | None = None
    #: Solo el canal sabe si reintentar sirve: una saturación sí; un timeout de lectura no.
    transitoria: bool = False


class PortEnvioDeRecordatorioDeTurno(Protocol):
    async def preparar(
        self, turno: Turno, anticipacion_min: int
    ) -> RecordatorioListo | SinTelefono:
        """Lee contacto, servicio y plantilla. Corre dentro de la reserva de la fila."""
        ...

    async def mandar(self, listo: RecordatorioListo) -> ResultadoDelEnvio:
        """Habla con el canal y nada más. **Nunca levanta.**"""
        ...


__all__ = [
    "PlantillaDelRecordatorio",
    "PortAgendaDeNotificacion",
    "PortEnvioDeRecordatorioDeTurno",
    "PortRepositorioRecordatoriosDeTurno",
    "PortTurnosPorRecordar",
    "RecordatorioListo",
    "ResultadoDelEnvio",
    "SinTelefono",
]
