"""Los casos de uso de turnos (HU-E7-01, HU-E7-02, HU-E7-03 y HU-E7-06).

**Administrador y Operador gestionan; Solo Lectura mira** (HU-E7-01 RN-03). Los guardas están
acá y no sólo en el router.

Tres cosas que este archivo hace y conviene leer con atención:

1. **No pretende garantizar que la franja esté libre.** Comprueba lo que puede —que el recurso
   atienda a esa hora, que el servicio se preste ahí— y después intenta guardar. La garantía
   contra el doble booking es la restricción de exclusión de PostgreSQL (decisión **D28**), y
   el repositorio traduce su negativa a `FranjaOcupada`. Cualquier chequeo previo es una
   cortesía para dar un mensaje sin gastar una transacción, nunca la garantía.

2. **El aviso por WhatsApp va después de persistir y no puede voltear la operación.** Un turno
   cancelado sigue cancelado aunque Meta esté caída; lo contrario dejaría al negocio sin poder
   cancelar por un problema ajeno.

3. **Reprogramar conserva el estado** (RN-02), y por eso no hay un `estado` en su firma.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.scheduling.application.errors import (
    FueraDeHorario,
    RecursoInactivo,
    ServicioNoAdmitido,
    TurnoInexistente,
    TurnoNoModificable,
)
from cheatsheet.contexts.scheduling.application.ports import (
    DatosDeAviso,
    FiltrosDeAgenda,
    PortCatalogoDeServicios,
    PortDirectorioDeClientes,
    PortNotificadorDeTurnos,
    PortRepositorioRecurso,
    PortRepositorioTurno,
)
from cheatsheet.contexts.scheduling.application.recursos import VerRecurso
from cheatsheet.contexts.scheduling.domain.recurso import RecursoReservable
from cheatsheet.contexts.scheduling.domain.turno import (
    MENSAJE_HORARIO_OCUPADO,
    CanalDeReserva,
    Franja,
    Turno,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

MOTIVO_SIN_PERMISO = "Solo un Administrador u Operador puede gestionar turnos"
MENSAJE_RECURSO_INACTIVO = "El recurso está desactivado y no admite reservas nuevas."
MENSAJE_SERVICIO_NO_ADMITIDO = "El servicio seleccionado no se presta en ese recurso."
MENSAJE_FUERA_DE_HORARIO = "El recurso no atiende en el horario seleccionado."


def _exigir_gestor(rol: RolUsuario) -> None:
    if rol not in (RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR):
        raise EntradaInvalida(MOTIVO_SIN_PERMISO)


class Avisador:
    """Los tres avisos por WhatsApp de HU-E7-02 y HU-E7-06, en un solo lugar.

    Existe porque los tres casos de uso que avisan necesitaban los mismos cuatro
    colaboradores para armar el mismo mensaje, y cuatro parámetros repetidos en tres
    constructores son tres oportunidades de conectar uno mal en el composition root.

    **Ningún método levanta por no poder avisar.** Un cliente sin teléfono es un camino
    previsto —HU-E7-02 RN-03 dice «si tiene número registrado»—, y un turno cancelado sigue
    cancelado aunque Meta esté caída.
    """

    def __init__(
        self,
        *,
        clientes: PortDirectorioDeClientes,
        servicios: PortCatalogoDeServicios,
        notificador: PortNotificadorDeTurnos,
    ) -> None:
        self._clientes = clientes
        self._servicios = servicios
        self._notificador = notificador

    async def reserva(
        self, turno: Turno, recurso: RecursoReservable | None, servicio: str | None = None
    ) -> None:
        datos = await self._armar(turno, recurso, servicio)
        if datos is not None:
            await self._notificador.avisar_reserva(datos)

    async def cancelacion(self, turno: Turno, recurso: RecursoReservable | None) -> None:
        datos = await self._armar(turno, recurso, None)
        if datos is not None:
            await self._notificador.avisar_cancelacion(datos)

    async def reprogramacion(
        self, turno: Turno, recurso: RecursoReservable | None, *, anterior: datetime
    ) -> None:
        datos = await self._armar(turno, recurso, None, anterior=anterior)
        if datos is not None:
            await self._notificador.avisar_reprogramacion(datos)

    async def _armar(
        self,
        turno: Turno,
        recurso: RecursoReservable | None,
        servicio: str | None,
        *,
        anterior: datetime | None = None,
    ) -> DatosDeAviso | None:
        contacto = await self._clientes.contacto_de(turno.cliente_id)
        if contacto is None:
            return None
        nombre, telefono = contacto
        return DatosDeAviso(
            telefono=telefono,
            nombre_del_cliente=nombre,
            servicio=servicio or await self._nombre_de_servicio(turno.servicio_id),
            # El recurso ausente no deja el aviso sin texto: un turno cuyo recurso ya no se
            # puede leer sigue siendo un turno que el cliente tiene anotado.
            recurso=recurso.nombre if recurso is not None else "el recurso",
            inicio=turno.franja.inicio,
            inicio_anterior=anterior,
        )

    async def _nombre_de_servicio(self, servicio_id: UUID) -> str:
        servicio = await self._servicios.buscar_agendable(servicio_id)
        # Un servicio que dejó de ser agendable después de reservado sigue teniendo turnos, y
        # el aviso no puede quedarse sin texto por eso.
        return servicio.nombre if servicio is not None else "el servicio"


class VerAgenda:
    """PAN-AGE-01 (HU-E7-01). Todos los roles leen.

    El rango por defecto lo decide el **router**, no este caso de uso: «el día en curso» es una
    preferencia de presentación de RN-01 y depende de la zona horaria de quien mira, mientras
    que este servicio contesta por cualquier rango — que es lo que el reporte del épico 9 y el
    agente del épico 8 van a necesitar.
    """

    def __init__(self, turnos: PortRepositorioTurno) -> None:
        self._turnos = turnos

    async def ejecutar(self, filtros: FiltrosDeAgenda | None = None) -> list[Turno]:
        return await self._turnos.listar(filtros or FiltrosDeAgenda())


class VerTurno:
    """PAN-AGE-02. Levanta en vez de devolver `None`, como el resto del sistema."""

    def __init__(self, turnos: PortRepositorioTurno) -> None:
        self._turnos = turnos

    async def ejecutar(self, turno_id: UUID) -> Turno:
        turno = await self._turnos.buscar_por_id(turno_id)
        if turno is None:
            raise TurnoInexistente("El turno no existe")
        return turno


class ReservarTurno:
    """HU-E7-06 — crear un turno a mano desde el panel.

    El canal queda en `PANEL` (RN-02), que es lo que va a distinguir estos turnos de los que
    cree el agente del épico 8 por el mismo camino.

    **La duración sale del servicio**, no del formulario: `master_data` la exige para todo
    servicio agendable, y dejar que la pantalla la mande sería dejar que dos turnos del mismo
    servicio duren distinto porque alguien escribió otro número.
    """

    def __init__(
        self,
        *,
        turnos: PortRepositorioTurno,
        recursos: PortRepositorioRecurso,
        servicios: PortCatalogoDeServicios,
        avisador: Avisador,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._turnos = turnos
        self._recursos = recursos
        self._servicios = servicios
        self._avisador = avisador
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        # `None` significa **el sistema**, que es lo que el agente del épico 8 es: no hay un
        # usuario detrás de un mensaje de WhatsApp, y darle uno inventado sería una fila de
        # `usuario` que no corresponde a nadie. Quién fue lo dice el iniciador de la bitácora.
        usuario_id: UsuarioId | None,
        rol: RolUsuario,
        cliente_id: UUID,
        servicio_id: UUID,
        recurso_id: UUID,
        inicio: datetime,
        ahora: datetime,
        duracion_min: int | None = None,
        canal: str = CanalDeReserva.PANEL,
    ) -> Turno:
        _exigir_gestor(rol)
        recurso = await VerRecurso(self._recursos).ejecutar(recurso_id)
        servicio = await self._servicios.buscar_agendable(servicio_id)
        if servicio is None or not recurso.admite_servicio(servicio_id):
            # Las dos causas dan el mismo mensaje: para quien reserva, un servicio que no se
            # presta ahí y uno que no es agendable son lo mismo — no está disponible.
            raise ServicioNoAdmitido(MENSAJE_SERVICIO_NO_ADMITIDO)
        if not recurso.activo:
            raise RecursoInactivo(MENSAJE_RECURSO_INACTIVO)

        franja = Franja(inicio=inicio, duracion_min=duracion_min or servicio.duracion_estandar_min)
        if not recurso.esta_disponible_en(franja.inicio, franja.duracion_min):
            raise FueraDeHorario(MENSAJE_FUERA_DE_HORARIO)

        turno = Turno(
            id=uuid4(),
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            servicio_id=servicio_id,
            recurso_id=recurso_id,
            franja=franja,
            canal_reserva=canal,
            created_at=ahora,
            updated_at=ahora,
        )
        # Puede levantar `FranjaOcupada`: es la restricción de exclusión hablando, y es la
        # única afirmación confiable de que el horario estaba libre.
        await self._turnos.agregar(turno)

        await _auditar(self._publicador, empresa_id, usuario_id, turno, "reservar_turno", ahora)
        await self._avisador.reserva(turno, recurso, servicio.nombre)
        return turno


class CancelarTurno:
    """HU-E7-02. Cancela y avisa al cliente si tiene número (RN-03)."""

    def __init__(
        self,
        *,
        turnos: PortRepositorioTurno,
        recursos: PortRepositorioRecurso,
        avisador: Avisador,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._turnos = turnos
        self._recursos = recursos
        self._avisador = avisador
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId | None,
        rol: RolUsuario,
        turno_id: UUID,
        ahora: datetime,
    ) -> Turno:
        _exigir_gestor(rol)
        turno = await VerTurno(self._turnos).ejecutar(turno_id)
        try:
            turno.cancelar()
        except InvarianteViolada as exc:
            raise TurnoNoModificable(str(exc)) from exc
        turno.updated_at = ahora
        await self._turnos.guardar(turno)

        await _auditar(self._publicador, empresa_id, usuario_id, turno, "cancelar_turno", ahora)
        await self._avisador.cancelacion(
            turno, await self._recursos.buscar_por_id(turno.recurso_id)
        )
        return turno


class ReprogramarTurno:
    """HU-E7-02 RN-01 y RN-02: mueve la franja y **conserva el estado**.

    Cuando la franja nueva está ocupada, el turno **queda donde estaba** — que es el criterio
    de aceptación textual. Eso sale gratis del orden de las operaciones: si `guardar` levanta,
    la transacción se revierte y el objeto en memoria no llegó a persistirse.
    """

    def __init__(
        self,
        *,
        turnos: PortRepositorioTurno,
        recursos: PortRepositorioRecurso,
        avisador: Avisador,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._turnos = turnos
        self._recursos = recursos
        self._avisador = avisador
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        turno_id: UUID,
        inicio: datetime,
        ahora: datetime,
        duracion_min: int | None = None,
    ) -> Turno:
        _exigir_gestor(rol)
        turno = await VerTurno(self._turnos).ejecutar(turno_id)
        anterior = turno.franja.inicio
        recurso = await VerRecurso(self._recursos).ejecutar(turno.recurso_id)

        franja = Franja(inicio=inicio, duracion_min=duracion_min or turno.franja.duracion_min)
        if not recurso.esta_disponible_en(franja.inicio, franja.duracion_min):
            # La historia usa una sola frase para «ocupado» y este caso es «cerrado», que es
            # distinto — pero para quien reprograma el efecto es el mismo, así que se dice lo
            # que la historia escribió y el detalle queda en el tipo de la excepción.
            raise FueraDeHorario(MENSAJE_HORARIO_OCUPADO)

        try:
            turno.reprogramar(franja)
        except InvarianteViolada as exc:
            raise TurnoNoModificable(str(exc)) from exc
        turno.updated_at = ahora
        await self._turnos.guardar(turno)

        await _auditar(self._publicador, empresa_id, usuario_id, turno, "reprogramar_turno", ahora)
        await self._avisador.reprogramacion(turno, recurso, anterior=anterior)
        return turno


class RegistrarAsistencia:
    """HU-E7-03. Completado o no-show, y **sólo si el turno ya transcurrió** (RN-01).

    El «ya transcurrió» lo decide el agregado contra el reloj que se le pasa, no una columna:
    un flag guardado sería un dato derivado que hay que mantener, y que a las tres de la
    mañana de algún día iba a estar desactualizado.
    """

    def __init__(self, turnos: PortRepositorioTurno, publicador: PublicadorDeEventos) -> None:
        self._turnos = turnos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        turno_id: UUID,
        asistio: bool,
        ahora: datetime,
    ) -> Turno:
        _exigir_gestor(rol)
        turno = await VerTurno(self._turnos).ejecutar(turno_id)
        try:
            if asistio:
                turno.marcar_completado(ahora)
            else:
                turno.marcar_no_show(ahora)
        except InvarianteViolada as exc:
            raise TurnoNoModificable(str(exc)) from exc
        turno.updated_at = ahora
        await self._turnos.guardar(turno)
        await _auditar(
            self._publicador,
            empresa_id,
            usuario_id,
            turno,
            "marcar_turno_completado" if asistio else "marcar_turno_no_show",
            ahora,
        )
        return turno


class AsignarSenaAlTurno:
    """HU-E6-07 — asocia el cobro de una seña al turno.

    Lo llama el composition root después de que `payments` generó el cobro: `scheduling` no
    genera cobros, y `payments` no escribe en la tabla `turno`. El id cruza y nada más, que es
    lo que el hallazgo H4 del DER dejó dicho al declarar la columna sin FK.
    """

    def __init__(self, turnos: PortRepositorioTurno, publicador: PublicadorDeEventos) -> None:
        self._turnos = turnos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        turno_id: UUID,
        cobro_id: UUID,
        ahora: datetime,
    ) -> Turno:
        turno = await VerTurno(self._turnos).ejecutar(turno_id)
        turno.asignar_cobro(cobro_id)
        turno.updated_at = ahora
        await self._turnos.guardar(turno)
        await _auditar(self._publicador, empresa_id, usuario_id, turno, "asociar_sena", ahora)
        return turno


async def _auditar(
    publicador: PublicadorDeEventos,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId | None,
    turno: Turno,
    accion: str,
    ahora: datetime,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ocurrido_en=ahora,
            modulo=Modulo.SCHEDULING,
            accion=accion,
            entidad_afectada=f"Turno:{turno.id}",
            resultado=Resultado.COMPLETADO,
        )
    )


__all__ = [
    "AsignarSenaAlTurno",
    "Avisador",
    "CancelarTurno",
    "RegistrarAsistencia",
    "ReprogramarTurno",
    "ReservarTurno",
    "VerAgenda",
    "VerTurno",
]
