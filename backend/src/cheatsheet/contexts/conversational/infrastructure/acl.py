"""ACL sobre `scheduling` y `master_data`, en el vocabulario del agente.

**`AgendaViaScheduling` es la puerta angosta de la decisión D38.** Cuatro operaciones, y del
otro lado están los casos de uso deterministas del épico 7 — con su comprobación de horario,
su validación de servicio y, sobre todo, la restricción de exclusión que hace imposible el
doble booking (D28). El agente no reserva: le pide a esta clase que reserve, y esta clase le
pide al motor.

Que sea un ACL y no una llamada directa importa por una razón concreta: `reservar` recibe un
`HorarioOfrecible` que **salió de `horarios_ofrecibles`**, no una fecha que el modelo escribió.
El agente no puede inventar un horario porque no tiene cómo construir uno.

Nada de acá importa el dominio de los otros contextos: se llaman sus servicios de aplicación y
lo que devuelven se lee por atributo, igual que `SaldoViaBilling` del épico 6.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from cheatsheet.contexts.conversational.application.ports import (
    HorarioOfrecible,
    TurnoDelCliente,
)
from cheatsheet.contexts.master_data.application.clientes import (
    DatosDeCliente,
    OrigenDato,
    RegistrarCliente,
)
from cheatsheet.contexts.master_data.application.ports import PortPadron, PortRepositorioCliente
from cheatsheet.contexts.scheduling.application.disponibilidad import VerHorariosDisponibles
from cheatsheet.contexts.scheduling.application.errors import ServicioNoAdmitido
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
    ) -> None:
        self._turnos = turnos
        self._recursos = recursos
        self._servicios = servicios
        self._avisador = avisador
        self._publicador = publicador
        self._reloj = reloj
        self._empresa_id = empresa_id
        self._usuario_id = usuario_id

    async def horarios_ofrecibles(self, *, dia: date, limite: int = 4) -> list[HorarioOfrecible]:
        """HU-E8-01 RN-02: **sólo horarios efectivamente disponibles.**

        La grilla la calcula `VerHorariosDisponibles`, la misma que usa el panel: inicios por el
        paso del slot, el turno del servicio entra en la franja, y «ocupado» es solapamiento más
        intervalo entre turnos (D96). Se descartan los que ya pasaron (HU-E8-01 RN-06, D95). Lo
        que sale de acá es lo único que el agente puede nombrar.
        """
        ahora = self._reloj.ahora()
        grilla = VerHorariosDisponibles(
            turnos=self._turnos, recursos=self._recursos, servicios=self._servicios
        )
        ofrecibles: list[HorarioOfrecible] = []
        for recurso in await ListarRecursos(self._recursos).ejecutar(solo_activos=True):
            if not recurso.servicios:
                continue
            servicio_id = sorted(recurso.servicios)[0]
            try:
                horarios = await grilla.ejecutar(
                    recurso_id=recurso.id, servicio_id=servicio_id, fecha=dia, ahora=ahora
                )
            except ServicioNoAdmitido:
                # El servicio asociado dejó de ser agendable: sin servicio no hay duración, y
                # ofrecer un horario que `reservar` va a rechazar es lo que esto evita.
                continue
            for horario in horarios:
                if horario.ocupado:
                    continue
                ofrecibles.append(
                    HorarioOfrecible(
                        recurso_id=recurso.id, servicio_id=servicio_id, inicio=horario.inicio
                    )
                )
                if len(ofrecibles) >= limite:
                    return ofrecibles
        return ofrecibles

    async def reservar(self, *, cliente_id: UUID, horario: HorarioOfrecible) -> UUID:
        """HU-E8-01 RN-03: **el motor determinista.**

        Puede levantar `FranjaOcupada` si alguien se adelantó entre que se ofreció el horario y
        que el cliente lo eligió — que es exactamente el cuarto criterio de la historia: «dos
        clientes intentan el mismo horario casi simultáneamente». Quien decide es PostgreSQL.
        """
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
        return turno.id

    async def turnos_de(self, cliente_id: UUID) -> list[TurnoDelCliente]:
        """HU-E8-02 RN-01: los turnos del cliente, para saber cuál cancelar.

        Sólo los **futuros y abiertos**: cancelar un turno de la semana pasada no libera nada, y
        ofrecérselo al cliente es ofrecerle una acción sin efecto.
        """
        desde = self._reloj.ahora()
        turnos = await VerAgenda(self._turnos).ejecutar(FiltrosDeAgenda(desde=desde))
        nombres = {uno.id: uno.nombre for uno in await self._servicios.listar_agendables()}
        return [
            TurnoDelCliente(
                id=uno.id,
                servicio=nombres.get(uno.servicio_id, "el servicio"),
                inicio=uno.franja.inicio,
            )
            for uno in turnos
            if uno.cliente_id == cliente_id and uno.esta_abierto
        ]

    async def cancelar(self, turno_id: UUID) -> None:
        """HU-E8-02 RN-02: el horario queda liberado para nuevas reservas.

        Lo garantiza la cláusula `WHERE` de la restricción de exclusión, que sólo cuenta los
        turnos abiertos: cancelar saca al turno del conjunto que bloquea.
        """
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
