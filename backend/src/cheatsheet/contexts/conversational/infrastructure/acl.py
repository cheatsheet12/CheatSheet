"""ACL sobre `scheduling` y `master_data`, en el vocabulario del agente.

**`AgendaViaScheduling` es la puerta angosta de la decisión D38.** Cinco operaciones, y del
otro lado están los casos de uso deterministas del épico 7 — con su comprobación de horario,
su validación de servicio y, sobre todo, la restricción de exclusión que hace imposible el
doble booking (D28). El agente no reserva: le pide a esta clase que reserve, y esta clase le
pide al motor.

Que sea un ACL y no una llamada directa importa por una razón concreta: `reservar` recibe un
`HorarioOfrecible` que **salió de `horarios_libres`**, no una fecha que el modelo escribió.
El agente no puede inventar un horario porque no tiene cómo construir uno.

**Cada acción sobre la agenda corre en un savepoint** (T9). `FranjaOcupada` nace del
`IntegrityError` de la restricción de exclusión, y en PostgreSQL eso deja la transacción
abortada: sin savepoint, lo que el agente escriba después —el estado del diálogo, el mensaje
saliente, la bitácora— fallaría y el webhook terminaría en 500. Con savepoint, un rechazo del
motor revierte sólo ese intento.

Nada de acá importa el dominio de los otros contextos: se llaman sus servicios de aplicación y
lo que devuelven se lee por atributo, igual que `SaldoViaBilling` del épico 6.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, nullcontext
from datetime import date
from uuid import UUID

from cheatsheet.contexts.conversational.application.errors import (
    HorarioEnElPasado,
    HorarioNoDisponible,
    TurnoNoCancelable,
)
from cheatsheet.contexts.conversational.application.ports import (
    ServicioOfrecible,
    TurnoDelCliente,
)
from cheatsheet.contexts.conversational.domain.seleccion_de_horarios import HorarioOfrecible
from cheatsheet.contexts.master_data.application.clientes import (
    DatosDeCliente,
    OrigenDato,
    RegistrarCliente,
)
from cheatsheet.contexts.master_data.application.ports import PortPadron, PortRepositorioCliente
from cheatsheet.contexts.scheduling.application.disponibilidad import VerHorariosDisponibles
from cheatsheet.contexts.scheduling.application.errors import (
    FranjaOcupada,
    FueraDeHorario,
    RecursoInactivo,
    RecursoInexistente,
    ServicioNoAdmitido,
    TurnoEnElPasado,
    TurnoInexistente,
    TurnoNoModificable,
)
from cheatsheet.contexts.scheduling.application.ports import (
    FiltrosDeAgenda,
    PortCatalogoDeServicios,
    PortRepositorioRecurso,
    PortRepositorioTurno,
)
from cheatsheet.contexts.scheduling.application.recursos import ListarRecursos
from cheatsheet.contexts.scheduling.application.turnos import (
    Avisador,
    CancelarTurno,
    ReservarTurno,
    VerAgenda,
)
from cheatsheet.shared.clock import Reloj
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

#: Con qué rol actúa el agente cuando llama a `scheduling`.
#:
#: `OPERADOR` y no `ADMINISTRADOR`: es exactamente lo que el agente necesita —reservar y
#: cancelar turnos— y nada de lo que no. Darle el rol máximo a un componente cuya entrada la
#: escribe un desconocido es el atajo que después no se puede revertir.
ROL_DEL_AGENTE = RolUsuario.OPERADOR

#: Lo que el motor rechaza y para el cliente significa «ese horario no se puede».
_RECHAZOS_DEL_MOTOR = (
    FranjaOcupada,
    FueraDeHorario,
    RecursoInactivo,
    RecursoInexistente,
    ServicioNoAdmitido,
)


class AgendaViaScheduling:
    """`PortAgenda`, respaldado por los casos de uso publicados de `scheduling`."""

    def __init__(
        self,
        *,
        turnos: PortRepositorioTurno,
        recursos: PortRepositorioRecurso,
        servicios: PortCatalogoDeServicios,
        avisador: Avisador,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId | None,
        aislar: Callable[[], AbstractAsyncContextManager[object]] = nullcontext,
    ) -> None:
        self._turnos = turnos
        self._recursos = recursos
        self._servicios = servicios
        self._avisador = avisador
        self._publicador = publicador
        self._reloj = reloj
        self._empresa_id = empresa_id
        self._usuario_id = usuario_id
        #: Abre un savepoint. El composition root le pasa `sesion.begin_nested`.
        self._aislar = aislar

    async def servicios_ofrecibles(self) -> list[ServicioOfrecible]:
        """Los servicios agendables que algún recurso activo presta (pendiente #17)."""
        prestados = {
            servicio
            for recurso in await ListarRecursos(self._recursos).ejecutar(solo_activos=True)
            for servicio in recurso.servicios
        }
        agendables = await self._servicios.listar_agendables()
        ofrecibles = [
            ServicioOfrecible(id=uno.id, nombre=uno.nombre)
            for uno in agendables
            if uno.id in prestados
        ]
        return sorted(ofrecibles, key=lambda uno: uno.nombre.lower())

    async def horarios_libres(self, *, servicio_id: UUID, dia: date) -> list[HorarioOfrecible]:
        """HU-E8-01 RN-02: **sólo horarios efectivamente disponibles.**

        La grilla la calcula `VerHorariosDisponibles`, la misma que usa el panel: inicios por el
        paso del slot, el turno del servicio entra en la franja, y «ocupado» es solapamiento más
        intervalo entre turnos (D96). Se descartan los que ya pasaron (HU-E8-01 RN-06, D95). Lo
        que sale de acá es lo único que el agente puede nombrar. **No corta ni elige**: devuelve
        todos los libres de todos los recursos que prestan el servicio.
        """
        ahora = self._reloj.ahora()
        grilla = VerHorariosDisponibles(
            turnos=self._turnos, recursos=self._recursos, servicios=self._servicios
        )
        libres: list[HorarioOfrecible] = []
        for recurso in await ListarRecursos(self._recursos).ejecutar(solo_activos=True):
            if servicio_id not in recurso.servicios:
                continue
            try:
                horarios = await grilla.ejecutar(
                    recurso_id=recurso.id, servicio_id=servicio_id, fecha=dia, ahora=ahora
                )
            except ServicioNoAdmitido:
                # El servicio dejó de ser agendable: sin servicio no hay duración, y ofrecer un
                # horario que `reservar` va a rechazar es lo que esto evita.
                continue
            libres.extend(
                HorarioOfrecible(
                    recurso_id=recurso.id, servicio_id=servicio_id, inicio=horario.inicio
                )
                for horario in horarios
                if not horario.ocupado
            )
        return libres

    async def reservar(self, *, cliente_id: UUID, horario: HorarioOfrecible) -> UUID:
        """HU-E8-01 RN-03: **el motor determinista.**

        Puede rechazar si alguien se adelantó entre que se ofreció el horario y que el cliente lo
        eligió — que es exactamente el cuarto criterio de la historia: «dos clientes intentan el
        mismo horario casi simultáneamente». Quien decide es PostgreSQL. Los rechazos se
        traducen al vocabulario del agente, y el savepoint deja la transacción usable.
        """
        try:
            async with self._aislar():
                turno = await ReservarTurno(
                    turnos=self._turnos,
                    recursos=self._recursos,
                    servicios=self._servicios,
                    avisador=self._avisador,
                    publicador=self._publicador,
                ).ejecutar(
                    empresa_id=self._empresa_id,
                    usuario_id=self._usuario_id,
                    rol=ROL_DEL_AGENTE,
                    cliente_id=cliente_id,
                    servicio_id=horario.servicio_id,
                    recurso_id=horario.recurso_id,
                    inicio=horario.inicio,
                    ahora=self._reloj.ahora(),
                    canal="AGENTE",
                )
        except TurnoEnElPasado as exc:
            raise HorarioEnElPasado(str(exc)) from exc
        except _RECHAZOS_DEL_MOTOR as exc:
            raise HorarioNoDisponible(str(exc)) from exc
        return turno.id

    async def turnos_de(self, cliente_id: UUID) -> list[TurnoDelCliente]:
        """HU-E8-02 RN-01: los turnos del cliente, para saber cuál cancelar.

        Sólo los **futuros y abiertos**: cancelar un turno de la semana pasada no libera nada, y
        ofrecérselo al cliente es ofrecerle una acción sin efecto. El estado se lee por atributo
        (`esta_abierto`) porque filtrarlo con `FiltrosDeAgenda(estados=…)` exigiría importar el
        enum del dominio de `scheduling` (R3).
        """
        desde = self._reloj.ahora()
        turnos = await VerAgenda(self._turnos).ejecutar(FiltrosDeAgenda(desde=desde))
        nombres = {uno.id: uno.nombre for uno in await self._servicios.listar_agendables()}
        return [
            TurnoDelCliente(
                id=uno.id,
                servicio=nombres.get(uno.servicio_id, "el servicio"),
                inicio=uno.franja.inicio,
                tiene_sena=uno.cobro_id is not None,
            )
            for uno in turnos
            if uno.cliente_id == cliente_id and uno.esta_abierto
        ]

    async def cancelar(self, turno_id: UUID) -> None:
        """HU-E8-02 RN-02: el horario queda liberado para nuevas reservas.

        Lo garantiza la cláusula `WHERE` de la restricción de exclusión, que sólo cuenta los
        turnos abiertos: cancelar saca al turno del conjunto que bloquea.
        """
        try:
            async with self._aislar():
                await CancelarTurno(
                    turnos=self._turnos,
                    recursos=self._recursos,
                    avisador=self._avisador,
                    publicador=self._publicador,
                ).ejecutar(
                    empresa_id=self._empresa_id,
                    usuario_id=self._usuario_id,
                    rol=ROL_DEL_AGENTE,
                    turno_id=turno_id,
                    ahora=self._reloj.ahora(),
                )
        except (TurnoNoModificable, TurnoInexistente) as exc:
            raise TurnoNoCancelable(str(exc)) from exc


class DirectorioViaMasterData:
    """`PortDirectorio`. Quién es el número que escribió, y cómo darlo de alta si no está.

    **El alta rápida guarda el teléfono y un nombre provisorio, y nada más.** No hay CUIT, ni
    condición fiscal, ni dirección: son datos que el cliente no dio, y el sistema no los
    necesita para contestarle una pregunta.
    """

    def __init__(
        self,
        clientes: PortRepositorioCliente,
        *,
        padron: PortPadron,
        publicador: PublicadorDeEventos,
        reloj: Reloj,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId | None,
    ) -> None:
        self._clientes = clientes
        self._padron = padron
        self._publicador = publicador
        self._reloj = reloj
        self._empresa_id = empresa_id
        self._usuario_id = usuario_id

    async def cliente_de(self, telefono: str) -> tuple[UUID, str] | None:
        cliente = await self._clientes.buscar_por_telefono(telefono)
        return (cliente.id, cliente.nombre) if cliente is not None else None

    async def telefono_de(self, cliente_id: UUID) -> str | None:
        """El WhatsApp del cliente. Un cliente dado de baja **sí** se resuelve: ver HU-E9-01."""
        cliente = await self._clientes.buscar_por_id(cliente_id)
        if cliente is None or cliente.contacto_whatsapp is None:
            return None
        return str(cliente.contacto_whatsapp)

    async def alta_rapida(self, *, telefono: str, nombre: str) -> UUID:
        """Crea el cliente mínimo. **Origen `AGENTE`**, que es lo que el DER reserva para esto.

        Pasa por el caso de uso de `master_data` y no por el agregado: construirlo acá sería
        importar el dominio de otro contexto, que es lo que R3 prohíbe — y también saltearse
        el evento de auditoría y la validación de contacto que ese caso de uso ya hace.
        """
        vista = await RegistrarCliente(
            clientes=self._clientes,
            padron=self._padron,
            publicador=self._publicador,
            reloj=self._reloj,
        ).ejecutar(
            empresa_id=self._empresa_id,
            usuario_id=self._usuario_id,
            rol=ROL_DEL_AGENTE,
            datos=DatosDeCliente(nombre=nombre, contacto_whatsapp=telefono),
            origen=OrigenDato.AGENTE,
        )
        return vista.cliente.id


__all__ = ["ROL_DEL_AGENTE", "AgendaViaScheduling", "DirectorioViaMasterData"]
