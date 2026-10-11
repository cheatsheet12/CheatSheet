"""Puertos de `scheduling`.

Donde cada uno se niega es donde están las garantías.

`PortRepositorioTurno.agregar` **puede fallar con `FranjaOcupada`**, y eso es parte del
contrato, no un detalle del adaptador: la restricción de exclusión de PostgreSQL es la única
cosa del sistema que puede afirmar que una franja está libre sin una carrera (decisión
**D28**), así que el puerto tiene que dejar pasar su negativa.

`PortCatalogoDeServicios` es el ACL contra `master_data`. Pregunta dos cosas —¿es agendable? y
¿cuánto dura?— y ninguna más: `scheduling` no ve el precio del servicio, ni sus categorías, ni
su origen. La regla R3 lo obliga y el tamaño del puerto lo hace evidente.

`PortNotificadorDeTurnos` es el canal de WhatsApp de HU-E7-02 RN-03/RN-04 y HU-E7-06 RN-04.
Su adaptador real lo construye el **épico 8**, igual que el de los recordatorios de cobro; acá
tiene el mismo doble de consola, que se niega a arrancar en producción.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.scheduling.domain.recurso import RecursoReservable
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno, Turno


@dataclass(frozen=True, slots=True)
class FiltrosDeAgenda:
    """HU-E7-01 RN-01: por recurso y por rango de fechas.

    Vive en la capa de aplicación y no en `domain/` por lo que el guarda de arquitectura le
    enseñó al épico 4: un filtro es un pedido de afuera, no un concepto del agregado.
    """

    recurso_id: UUID | None = None
    desde: datetime | None = None
    hasta: datetime | None = None
    estados: tuple[EstadoTurno, ...] = ()


@dataclass(frozen=True, slots=True)
class ServicioAgendable:
    """Lo que `scheduling` necesita saber de un servicio, y nada más.

    `duracion_estandar_min` es lo que hace que el panel no tenga que preguntar cuánto dura un
    turno: el servicio ya lo sabe, y `master_data` lo exige para todo servicio agendable.
    """

    id: UUID
    nombre: str
    duracion_estandar_min: int


@dataclass(frozen=True, slots=True)
class DatosDeAviso:
    """Lo que se le cuenta al cliente por WhatsApp.

    Sin el objeto `Turno` adentro: el notificador es infraestructura y no tiene por qué poder
    tocar el agregado. Lo que cruza es texto y fechas — lo que un mensaje necesita.
    """

    #: El cliente del turno: el aviso se guarda en **su** conversación (U7, D-U7-4).
    cliente_id: UUID
    telefono: str
    nombre_del_cliente: str
    servicio: str
    recurso: str
    inicio: datetime
    inicio_anterior: datetime | None = None


class PortRepositorioRecurso(Protocol):
    """Persistencia de recursos reservables, siempre dentro de una empresa (RLS).

    **Sin `eliminar`.** HU-E7-04 RN-03 pide desactivar, y por el mismo motivo que las reglas de
    negocio del épico 6: un recurso borrado deja los turnos que se prestaron en él apuntando a
    algo que ya no existe.
    """

    async def agregar(self, recurso: RecursoReservable) -> None: ...

    async def guardar(self, recurso: RecursoReservable) -> None: ...

    async def buscar_por_id(self, recurso_id: UUID) -> RecursoReservable | None: ...

    async def listar(self, solo_activos: bool = False) -> list[RecursoReservable]: ...


class PortRepositorioTurno(Protocol):
    """Persistencia de turnos, siempre dentro de una empresa (RLS)."""

    async def agregar(self, turno: Turno) -> None:
        """Guarda el turno, o levanta `FranjaOcupada` si el motor lo rechaza.

        **Es acá donde el doble booking se vuelve imposible.** El adaptador traduce la
        violación de la restricción de exclusión; ninguna comprobación previa reemplaza esto,
        porque entre el `SELECT` y el `INSERT` cabe otro request.
        """
        ...

    async def guardar(self, turno: Turno) -> None:
        """Ídem para una reprogramación: mover la franja puede chocar igual que crearla."""
        ...

    async def buscar_por_id(self, turno_id: UUID) -> Turno | None: ...

    async def listar(self, filtros: FiltrosDeAgenda) -> list[Turno]: ...

    async def ocupados_en(self, recurso_id: UUID, dia: date) -> list[Turno]:
        """Los turnos que ocupan la franja de ese recurso ese día: abiertos y completados.

        Lo usa el selector de horarios para tachar los que ya están tomados. Es una ayuda de
        interfaz, no una garantía: la garantía sigue siendo la restricción de exclusión.
        """
        ...


class PortCatalogoDeServicios(Protocol):
    """ACL sobre `master_data`. Dos preguntas y ninguna más."""

    async def buscar_agendable(self, servicio_id: UUID) -> ServicioAgendable | None:
        """El servicio, si existe y es agendable. `None` en cualquier otro caso.

        Un servicio no agendable y uno inexistente se colapsan a propósito: para un turno los
        dos significan lo mismo, y distinguirlos no le daría a nadie una acción distinta.
        """
        ...

    async def listar_agendables(self) -> list[ServicioAgendable]: ...


class PortDirectorioDeClientes(Protocol):
    """ACL sobre `master_data` para saber a quién avisarle.

    Devuelve `None` cuando el cliente no tiene teléfono registrado, que es la condición literal
    de HU-E7-02 RN-03: «notifica al cliente por WhatsApp **si tiene número registrado**».
    """

    async def contacto_de(self, cliente_id: UUID) -> tuple[str, str] | None:
        """`(nombre, telefono)`, o `None` si no hay número al que escribir."""
        ...


class PortNotificadorDeTurnos(Protocol):
    """El canal de WhatsApp de HU-E7-02 y HU-E7-06.

    Los tres métodos son los tres avisos que las historias piden. Ninguno devuelve nada: el
    aviso es un efecto de mejor esfuerzo y **no puede voltear la operación** — un turno
    cancelado sigue cancelado aunque WhatsApp esté caído, y lo contrario dejaría al negocio sin
    poder cancelar cuando Meta tiene un problema.
    """

    async def avisar_reserva(self, datos: DatosDeAviso) -> None: ...

    async def avisar_cancelacion(self, datos: DatosDeAviso) -> None: ...

    async def avisar_reprogramacion(self, datos: DatosDeAviso) -> None: ...


class PortSenaDeTurno(Protocol):
    """ACL sobre `payments` para la seña de HU-E6-07.

    Una sola operación: generá un cobro por este turno y devolveme su id. `scheduling` no ve el
    link, ni la pasarela, ni el estado del cobro — sólo necesita el id que va en
    `turno.cobro_id`.
    """

    async def generar_sena(
        self, turno_id: UUID, cliente_id: UUID, monto: str, descripcion: str
    ) -> UUID: ...


__all__ = [
    "DatosDeAviso",
    "FiltrosDeAgenda",
    "PortCatalogoDeServicios",
    "PortDirectorioDeClientes",
    "PortNotificadorDeTurnos",
    "PortRepositorioRecurso",
    "PortRepositorioTurno",
    "PortSenaDeTurno",
    "ServicioAgendable",
]
