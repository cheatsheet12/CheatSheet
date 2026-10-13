"""Ports of the observability context.

Note what each port refuses to offer, because that is where the guarantees live.

`PortRegistroDeAuditoria` has no `actualizar` and no `eliminar`: HS-T5 RN-03 makes audit
records immutable, and the cheapest place to enforce that is the shape of the interface.
A repository that cannot express deletion cannot be talked into it by a future caller in
a hurry.

`PortRepositorioTareaAsincrona` does offer `actualizar` -- a task is execution state and
mutates on every attempt -- but still refuses `eliminar`, for its own reason: HS-T6 RN-04
keeps exhausted tasks for analysis and replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.observability.domain.notificacion import Notificacion
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.contexts.observability.domain.solicitud_de_soporte import SolicitudDeSoporte
from cheatsheet.contexts.observability.domain.tarea_asincrona import TareaAsincrona
from cheatsheet.shared.auditoria import Iniciador, Modulo, Resultado
from cheatsheet.shared.empresa import UsuarioId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia


@dataclass(frozen=True, slots=True)
class FiltrosDeBitacora:
    """What a reader of the log may narrow it down by.

    Introduced by epic 9, which needs "how many operations happened in this period" for
    the dashboard, and reused by the audit panel of epic 10. Every field optional; absent
    means "do not filter by this".

    `limite` is not optional and is not unbounded: this table grows with every operation
    the system performs, and a read without a ceiling is the one query that takes the
    process down on the busiest company.
    """

    desde: datetime | None = None
    hasta: datetime | None = None
    modulos: tuple[Modulo, ...] = ()
    #: HU-E12-01 RN-03: por estado y por iniciador.
    resultados: tuple[Resultado, ...] = ()
    iniciadores: tuple[Iniciador, ...] = ()
    #: «Búsqueda por operación, cliente o archivo» (RN-03). Se busca sobre `accion` y
    #: `entidad_afectada`, que es donde esas tres cosas están escritas: la acción dice qué se
    #: hizo, y la entidad dice sobre qué —`Cliente:<id>`, `Planilla:<id>`—. Buscar el
    #: **nombre** de un cliente exigiría un join contra otro contexto, que R3 no permite y que
    #: además convertiría la bitácora en una vista de clientes.
    texto: str | None = None
    #: Los clientes cuyo nombre coincide con `texto`, resueltos por la pantalla contra
    #: `master_data` (#176). La búsqueda trae además las operaciones sobre `Cliente:<id>` y las
    #: que guardan ese `cliente_id` en su detalle —los turnos—. Ids y nunca nombres: el nombre
    #: no entra en la bitácora (D72), y este contexto no conoce a `master_data` (R3).
    clientes: tuple[UUID, ...] = ()
    limite: int = 500
    #: Desde qué fila continuar. Un desplazamiento y no un cursor porque la pantalla del panel
    #: es una tabla con paginado clásico, y un `OFFSET` sobre un índice por timestamp es
    #: barato en las primeras páginas — que son las que alguien mira.
    desplazamiento: int = 0


class PortRegistroDeAuditoria(Protocol):
    """Persistence of the audit log. Append and read; nothing else exists."""

    async def agregar(self, registro: RegistroDeAuditoria) -> None:
        """Persist a new record.

        Raises `RegistroDuplicado` when `evento_id` is already stored, so that a
        redelivery is a detectable condition rather than a second row.
        """
        ...

    async def buscar_por_evento(self, evento_id: UUID) -> RegistroDeAuditoria | None:
        """The record produced by an occurrence, if it was already registered."""
        ...

    async def buscar_por_id(self, registro_id: UUID) -> RegistroDeAuditoria | None: ...

    async def listar(self, filtros: FiltrosDeBitacora) -> list[RegistroDeAuditoria]:
        """The records matching the filters, most recent first.

        Reading is not writing: this addition keeps the port append-and-read, which is
        what HS-T5 RN-03 asks of it.
        """
        ...

    async def listar_de_entidad(self, entidad: str) -> list[RegistroDeAuditoria]:
        """Todo lo que le pasó a una entidad, de lo más viejo a lo más nuevo.

        Es el timeline de HU-E12-02: cada paso ya escribió su fila nombrando la misma entidad,
        así que el timeline se lee en vez de construirse. Sin límite y a propósito — una
        entidad de negocio deja media docena de filas en toda su vida, y cortar el timeline es
        cortar justo la parte que alguien fue a buscar.
        """
        ...

    async def contar(self, filtros: FiltrosDeBitacora) -> int:
        """How many records match — **without** materialising them.

        A separate method rather than `len(await listar(...))` because the caller that
        needs the number is a dashboard metric over a whole month, and hydrating tens of
        thousands of aggregates to count them would be work done to be thrown away.
        `limite` is ignored here: a count is not a page.
        """
        ...


class PortRepositorioNotificaciones(Protocol):
    """Persistencia del centro de notificaciones (HU-E11-03).

    **Sin `eliminar`.** Una notificación leída es la evidencia de que el sistema avisó; la que
    molesta se marca leída, que es lo que RN-03 pide.
    """

    async def agregar(self, notificacion: Notificacion) -> None: ...

    async def guardar(self, notificacion: Notificacion) -> None: ...

    async def buscar_por_id(self, notificacion_id: UUID) -> Notificacion | None: ...

    async def listar_de(
        self, destinatario_id: UsuarioId, *, solo_no_leidas: bool = False, limite: int = 50
    ) -> list[Notificacion]:
        """Las de una persona, de la más nueva a la más vieja.

        El destinatario es un argumento y no algo que el repositorio deduzca: RLS acota a la
        empresa, y adentro de una empresa hay varias personas que no comparten bandeja.
        """
        ...

    async def contar_no_leidas(self, destinatario_id: UsuarioId) -> int:
        """El número del globito. Un `count` y no `len(listar(...))`: es lo que se pide en
        cada carga del panel, y traer cincuenta filas para contarlas es trabajo tirado."""
        ...


class PortRepositorioSolicitudes(Protocol):
    """Persistencia de las solicitudes de soporte (HU-E9-03).

    **Sin `eliminar`.** Un pedido de ayuda borrado es un pedido que nadie puede demostrar que
    hizo, y RN-04 pide poder consultar el estado de lo abierto.
    """

    async def agregar(self, solicitud: SolicitudDeSoporte) -> None: ...

    async def guardar(self, solicitud: SolicitudDeSoporte) -> None: ...

    async def buscar_por_id(self, solicitud_id: UUID) -> SolicitudDeSoporte | None: ...

    async def listar(
        self, *, solo_abiertas: bool = False, limite: int = 50
    ) -> list[SolicitudDeSoporte]: ...


class PortDestinatarios(Protocol):
    """A quién le corresponde una notificación, según sus preferencias (HU-E11-03 RN-02).

    ACL sobre `identity`, de **sólo lectura**: devuelve ids de usuario y nada más. No devuelve
    usuarios porque este contexto no tiene nada que hacer con un email o un rol — lo único que
    necesita saber es a quién escribirle.
    """

    async def suscriptos_a(self, categoria: str) -> list[UsuarioId]:
        """Quiénes eligieron recibir esa categoría **en el panel**.

        El canal está fijo en `PANEL` porque esto alimenta el centro de notificaciones. Quien
        además la quiera por mail la recibe por el camino del épico 2, que es otro adaptador.
        """
        ...


class PortRepositorioTareaAsincrona(Protocol):
    """Persistence of async task state.

    Unlike `PortRegistroDeAuditoria` above, this one **does** offer `actualizar`: a task
    is execution state and mutates on every attempt. What it still does not offer is
    `eliminar` — HS-T6 RN-04 wants exhausted tasks kept for analysis and eventual replay,
    and a repository that can delete them is one `cleanup` job away from losing exactly
    the rows somebody needed.
    """

    async def agregar(self, tarea: TareaAsincrona) -> None: ...

    async def actualizar(self, tarea: TareaAsincrona) -> None: ...

    async def buscar_por_id(self, tarea_id: UUID) -> TareaAsincrona | None: ...

    async def buscar_por_clave(self, clave: ClaveDeIdempotencia) -> TareaAsincrona | None:
        """The task a given intended effect already produced, if any."""
        ...

    async def listar_fallidas(self, *, limite: int) -> list[TareaAsincrona]:
        """Tasks sitting in `FALLIDA`, oldest first — the sweep's only query.

        Bounded on purpose: an incident that fails ten thousand tasks must not turn the
        sweep into the thing that runs out of memory. What the batch leaves behind, the
        next run picks up.
        """
        ...
