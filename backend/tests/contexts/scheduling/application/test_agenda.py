"""Los casos de uso de la agenda (HU-E7-01 … HU-E7-06).

Cuatro cosas se prueban acá y las cuatro son decisiones del épico:

- **D28** — el caso de uso **no pretende** garantizar que la franja esté libre. Lo que se
  afirma es que deja pasar el `FranjaOcupada` del repositorio con la frase de la historia, y
  que un turno cuya reprogramación fue rechazada **queda donde estaba** (criterio textual).
- **D30** — reprogramar conserva el estado. Ya está probado en el dominio; acá se prueba que
  el caso de uso no lo pisa al pasar por el aviso y la bitácora.
- **D33** — el aviso por WhatsApp es de mejor esfuerzo. Un cliente sin teléfono es un camino
  previsto (RN-03 dice «si tiene número registrado»), y cancelar tiene que funcionar igual.
- **HU-E7-04 RN-02/RN-03** — un servicio no asociado y un recurso desactivado se rechazan
  **antes** de tocar el repositorio.

Los permisos se prueban una vez por familia y no por método: el guarda es la misma función en
los cinco casos de uso, y cinco copias del mismo test no encuentran un bug más.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
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
from cheatsheet.contexts.scheduling.application.ports import FiltrosDeAgenda, ServicioAgendable
from cheatsheet.contexts.scheduling.application.recursos import (
    MOTIVO_SOLO_ADMIN,
    AsociarServicios,
    CambiarEstadoDeRecurso,
    ConfigurarDisponibilidad,
    ListarRecursos,
    QuitarExcepcion,
    RegistrarExcepcion,
    RegistrarRecurso,
    VerRecurso,
)
from cheatsheet.contexts.scheduling.application.turnos import (
    MOTIVO_SIN_PERMISO,
    MOTIVO_SOLO_ADMIN_A_POSTERIORI,
    AsignarSenaAlTurno,
    Avisador,
    CancelarTurno,
    RegistrarAsistencia,
    ReprogramarTurno,
    ReservarTurno,
    VerAgenda,
    VerTurno,
)
from cheatsheet.contexts.scheduling.domain.recurso import (
    ZONA_DE_LA_AGENDA,
    ExcepcionDeDisponibilidad,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoExcepcion,
    TipoRecurso,
)
from cheatsheet.contexts.scheduling.domain.turno import (
    MENSAJE_DURACION_DE_TURNO,
    MENSAJE_HORARIO_OCUPADO,
    MENSAJE_REPROGRAMAR_AL_PASADO,
    MENSAJE_TURNO_EN_EL_PASADO,
    MENSAJE_TURNO_NO_TRANSCURRIO,
    CanalDeReserva,
    EstadoTurno,
    Franja,
    Turno,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida
from cheatsheet.shared.roles import RolUsuario

from tests.contexts.scheduling.application.dobles import (
    CatalogoEnMemoria,
    DirectorioEnMemoria,
    NotificadorEnMemoria,
    PublicadorEnMemoria,
    RepositorioRecursoEnMemoria,
    RepositorioTurnoEnMemoria,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
#: Martes 8 de septiembre de 2026, 15:00 hora de la agenda.
MARTES = date(2026, 9, 8)
AHORA = datetime(2026, 9, 1, 12, 0, tzinfo=ZONA_DE_LA_AGENDA)
CORTE = ServicioAgendable(id=uuid4(), nombre="Corte", duracion_estandar_min=30)
COLOR = ServicioAgendable(id=uuid4(), nombre="Color", duracion_estandar_min=90)


def local(hora: int, minuto: int = 0, dia: date = MARTES) -> datetime:
    return datetime.combine(dia, time(hora, minuto), tzinfo=ZONA_DE_LA_AGENDA)


def un_recurso(
    *, activo: bool = True, servicios: frozenset[UUID] | None = None
) -> RecursoReservable:
    return RecursoReservable(
        id=uuid4(),
        empresa_id=EMPRESA,
        nombre="Consultorio 1",
        tipo=TipoRecurso.ESPACIO,
        activo=activo,
        patrones=(
            PatronDeDisponibilidad(
                dia_semana=1, hora_inicio=time(9), hora_fin=time(18), duracion_slot_min=30
            ),
        ),
        servicios=servicios if servicios is not None else frozenset({CORTE.id}),
        created_at=AHORA,
    )


def un_turno(recurso: RecursoReservable, **cambios: object) -> Turno:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EMPRESA,
        "cliente_id": uuid4(),
        "servicio_id": CORTE.id,
        "recurso_id": recurso.id,
        "franja": Franja(inicio=local(15), duracion_min=30),
        "created_at": AHORA,
        "updated_at": AHORA,
    }
    base.update(cambios)
    return Turno(**base)  # type: ignore[arg-type]


def _estado(uno: Turno) -> EstadoTurno:
    return uno.estado


class Escena:
    """Todo lo que un caso de uso de turnos necesita, cableado de una vez."""

    def __init__(
        self, recurso: RecursoReservable, *turnos: Turno, con_telefono: bool = True
    ) -> None:
        self.recurso = recurso
        self.recursos = RepositorioRecursoEnMemoria(recurso)
        self.turnos = RepositorioTurnoEnMemoria(*turnos)
        self.catalogo = CatalogoEnMemoria(CORTE, COLOR)
        contactos = (
            {uno.cliente_id: ("Ana Diaz", "5491112345678") for uno in turnos}
            if con_telefono
            else {}
        )
        self.directorio = DirectorioEnMemoria(contactos)
        self.notificador = NotificadorEnMemoria()
        self.publicador = PublicadorEnMemoria()
        self.avisador = Avisador(
            clientes=self.directorio,
            servicios=self.catalogo,
            notificador=self.notificador,
        )

    def reservar(self) -> ReservarTurno:
        return ReservarTurno(
            turnos=self.turnos,
            recursos=self.recursos,
            servicios=self.catalogo,
            avisador=self.avisador,
            publicador=self.publicador,
        )

    def cancelar(self) -> CancelarTurno:
        return CancelarTurno(
            turnos=self.turnos,
            recursos=self.recursos,
            avisador=self.avisador,
            publicador=self.publicador,
        )

    def reprogramar(self) -> ReprogramarTurno:
        return ReprogramarTurno(
            turnos=self.turnos,
            recursos=self.recursos,
            avisador=self.avisador,
            publicador=self.publicador,
        )

    def con_contacto(self, cliente_id: UUID) -> Escena:
        self.directorio.contactos[cliente_id] = ("Ana Diaz", "5491112345678")
        return self


class TestReservar:
    async def test_crea_el_turno_con_canal_panel_y_avisa(self) -> None:
        """HU-E7-06, primer criterio, con RN-04 encima."""
        escena = Escena(un_recurso())
        cliente = uuid4()
        escena.con_contacto(cliente)

        turno = await escena.reservar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=cliente,
            servicio_id=CORTE.id,
            recurso_id=escena.recurso.id,
            inicio=local(15),
            ahora=AHORA,
        )

        assert turno.canal_reserva == CanalDeReserva.PANEL
        assert _estado(turno) is EstadoTurno.RESERVADO
        # La duración sale del servicio, no del formulario.
        assert turno.franja.duracion_min == CORTE.duracion_estandar_min
        assert [clase for clase, _ in escena.notificador.avisos] == ["reserva"]
        assert "reservar_turno" in escena.publicador.acciones

    async def test_el_evento_del_turno_dice_de_que_cliente_es_sin_su_nombre(self) -> None:
        """#176 (HU-E12-01 RN-03): para que buscar un cliente encuentre sus turnos.

        La bitácora guarda el id del cliente y nunca su nombre: es una tabla inmutable que lee
        cualquiera con acceso a la auditoría (D72).
        """
        escena = Escena(un_recurso())
        cliente = uuid4()
        escena.con_contacto(cliente)

        await escena.reservar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=cliente,
            servicio_id=CORTE.id,
            recurso_id=escena.recurso.id,
            inicio=local(15),
            ahora=AHORA,
        )

        evento = next(
            uno
            for uno in escena.publicador.eventos
            if getattr(uno, "accion", "") == "reservar_turno"
        )
        assert getattr(evento, "detalle", None) == {"cliente_id": str(cliente)}

    async def test_rechaza_un_servicio_que_no_se_presta_en_ese_recurso(self) -> None:
        """HU-E7-04 RN-02, y el tercer criterio de HU-E7-06."""
        escena = Escena(un_recurso())

        with pytest.raises(ServicioNoAdmitido):
            await escena.reservar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                cliente_id=uuid4(),
                servicio_id=COLOR.id,
                recurso_id=escena.recurso.id,
                inicio=local(15),
                ahora=AHORA,
            )

        assert escena.turnos.turnos == {}

    async def test_rechaza_un_recurso_desactivado(self) -> None:
        """HU-E7-04 RN-03: no acepta reservas nuevas."""
        escena = Escena(un_recurso(activo=False))

        with pytest.raises(RecursoInactivo):
            await escena.reservar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                cliente_id=uuid4(),
                servicio_id=CORTE.id,
                recurso_id=escena.recurso.id,
                inicio=local(15),
                ahora=AHORA,
            )

    async def test_rechaza_un_horario_en_el_que_el_recurso_no_atiende(self) -> None:
        escena = Escena(un_recurso())

        with pytest.raises(FueraDeHorario):
            await escena.reservar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                cliente_id=uuid4(),
                servicio_id=CORTE.id,
                recurso_id=escena.recurso.id,
                inicio=local(22),
                ahora=AHORA,
            )

    async def test_deja_pasar_el_rechazo_del_motor_con_la_frase_de_la_historia(self) -> None:
        """**Decisión D28.** El caso de uso no decide; traduce lo que el motor decidió."""
        escena = Escena(un_recurso())
        escena.turnos.ocupado = True

        with pytest.raises(FranjaOcupada) as fallo:
            await escena.reservar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                cliente_id=uuid4(),
                servicio_id=CORTE.id,
                recurso_id=escena.recurso.id,
                inicio=local(15),
                ahora=AHORA,
            )

        assert str(fallo.value) == MENSAJE_HORARIO_OCUPADO

    async def test_solo_lectura_no_reserva(self) -> None:
        """HU-E7-01 RN-03. El guarda vive en el caso de uso, no sólo en el router (PRU-09)."""
        escena = Escena(un_recurso())

        with pytest.raises(OperacionNoPermitida) as fallo:
            await escena.reservar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.SOLO_LECTURA,
                cliente_id=uuid4(),
                servicio_id=CORTE.id,
                recurso_id=escena.recurso.id,
                inicio=local(15),
                ahora=AHORA,
            )

        assert str(fallo.value) == MOTIVO_SIN_PERMISO

    async def test_un_recurso_de_otra_empresa_no_existe(self) -> None:
        escena = Escena(un_recurso())

        with pytest.raises(RecursoInexistente):
            await escena.reservar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.ADMINISTRADOR,
                cliente_id=uuid4(),
                servicio_id=CORTE.id,
                recurso_id=uuid4(),
                inicio=local(15),
                ahora=AHORA,
            )


class TestCancelar:
    async def test_cancela_y_avisa_al_cliente_con_telefono(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno)

        cancelado = await escena.cancelar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            turno_id=turno.id,
            ahora=AHORA,
        )

        assert _estado(cancelado) is EstadoTurno.CANCELADO
        assert [clase for clase, _ in escena.notificador.avisos] == ["cancelacion"]
        assert "cancelar_turno" in escena.publicador.acciones

    async def test_el_aviso_lleva_el_cliente_del_turno(self) -> None:
        """U7, D-U7-4: el aviso se guarda en la conversación de **ese** cliente."""
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno)

        await escena.cancelar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            turno_id=turno.id,
            ahora=AHORA,
        )

        ((_, datos),) = escena.notificador.avisos
        assert datos.cliente_id == turno.cliente_id

    async def test_cancela_igual_a_un_cliente_sin_telefono(self) -> None:
        """RN-03 dice «si tiene número registrado»: sin número es un camino previsto."""
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno, con_telefono=False)

        cancelado = await escena.cancelar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            turno_id=turno.id,
            ahora=AHORA,
        )

        assert _estado(cancelado) is EstadoTurno.CANCELADO
        assert escena.notificador.avisos == []

    async def test_un_turno_ya_cancelado_no_se_cancela_de_nuevo(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso, estado=EstadoTurno.CANCELADO)
        escena = Escena(recurso, turno)

        with pytest.raises(TurnoNoModificable):
            await escena.cancelar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                turno_id=turno.id,
                ahora=AHORA,
            )

    async def test_un_turno_de_otra_empresa_no_existe(self) -> None:
        escena = Escena(un_recurso())

        with pytest.raises(TurnoInexistente):
            await escena.cancelar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                turno_id=uuid4(),
                ahora=AHORA,
            )


class TestReprogramar:
    async def test_mueve_la_franja_conservando_el_estado_y_avisa_con_el_horario_viejo(
        self,
    ) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso, estado=EstadoTurno.CONFIRMADO)
        escena = Escena(recurso, turno)

        movido = await escena.reprogramar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            turno_id=turno.id,
            inicio=local(16),
            ahora=AHORA,
        )

        assert _estado(movido) is EstadoTurno.CONFIRMADO
        assert movido.franja.inicio == local(16)
        clase, datos = escena.notificador.avisos[0]
        assert clase == "reprogramacion"
        # El horario viejo viaja: sólo el nuevo dejaría a alguien sin saber si es el mismo
        # turno o uno más.
        assert datos.inicio_anterior == local(15)

    async def test_el_turno_queda_donde_estaba_cuando_el_horario_no_sirve(self) -> None:
        """Cuarto criterio de HU-E7-02, textual: «mantiene el turno en su franja original»."""
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno)

        with pytest.raises(FueraDeHorario) as fallo:
            await escena.reprogramar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                turno_id=turno.id,
                inicio=local(23),
                ahora=AHORA,
            )

        assert str(fallo.value) == MENSAJE_HORARIO_OCUPADO
        assert escena.turnos.turnos[turno.id].franja.inicio == local(15)
        assert escena.notificador.avisos == []

    async def test_un_turno_cancelado_no_se_reprograma(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso, estado=EstadoTurno.CANCELADO)
        escena = Escena(recurso, turno)

        with pytest.raises(TurnoNoModificable):
            await escena.reprogramar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                turno_id=turno.id,
                inicio=local(16),
                ahora=AHORA,
            )


class TestAsistencia:
    async def test_marca_completado_un_turno_pasado(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno)

        marcado = await RegistrarAsistencia(escena.turnos, escena.publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            turno_id=turno.id,
            asistio=True,
            ahora=local(16),
        )

        assert _estado(marcado) is EstadoTurno.COMPLETADO
        assert marcado.habilita_facturacion
        assert "marcar_turno_completado" in escena.publicador.acciones

    async def test_no_deja_marcar_un_turno_futuro(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno)

        with pytest.raises(TurnoNoModificable):
            await RegistrarAsistencia(escena.turnos, escena.publicador).ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                turno_id=turno.id,
                asistio=False,
                ahora=AHORA,
            )

    async def test_registra_el_no_show_en_la_bitacora(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno)

        await RegistrarAsistencia(escena.turnos, escena.publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            turno_id=turno.id,
            asistio=False,
            ahora=local(16),
        )

        assert "marcar_turno_no_show" in escena.publicador.acciones


class TestConsultas:
    async def test_la_agenda_filtra_por_recurso_y_rango(self) -> None:
        recurso = un_recurso()
        otro = un_recurso()
        de_hoy = un_turno(recurso)
        de_manana = un_turno(
            recurso, franja=Franja(inicio=local(15, dia=date(2026, 9, 15)), duracion_min=30)
        )
        ajeno = un_turno(otro, recurso_id=otro.id)
        escena = Escena(recurso, de_hoy, de_manana, ajeno)

        encontrados = await VerAgenda(escena.turnos).ejecutar(
            FiltrosDeAgenda(
                recurso_id=recurso.id, desde=local(0), hasta=local(0, dia=date(2026, 9, 9))
            )
        )

        assert [uno.id for uno in encontrados] == [de_hoy.id]

    async def test_ver_un_turno_inexistente_levanta(self) -> None:
        escena = Escena(un_recurso())

        with pytest.raises(TurnoInexistente):
            await VerTurno(escena.turnos).ejecutar(uuid4())


class TestSena:
    async def test_asocia_el_cobro_al_turno_y_lo_registra(self) -> None:
        """HU-E6-07. El id cruza el límite de contexto y nada más."""
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno)
        cobro = uuid4()

        con_sena = await AsignarSenaAlTurno(escena.turnos, escena.publicador).ejecutar(
            empresa_id=EMPRESA, usuario_id=USUARIO, turno_id=turno.id, cobro_id=cobro, ahora=AHORA
        )

        assert con_sena.cobro_id == cobro
        assert "asociar_sena" in escena.publicador.acciones


class TestRecursos:
    async def test_registra_un_recurso_y_lo_lista(self) -> None:
        repositorio = RepositorioRecursoEnMemoria()
        publicador = PublicadorEnMemoria()

        creado = await RegistrarRecurso(repositorio, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            nombre="  Sala 2  ",
            tipo=TipoRecurso.ESPACIO,
            ahora=AHORA,
        )

        assert creado.nombre == "Sala 2"
        assert creado.activo
        # Nace sin servicios, así que no admite ninguno: un recurso a medio configurar no
        # acepta cualquier reserva.
        assert not creado.admite_servicio(CORTE.id)
        assert [uno.id for uno in await ListarRecursos(repositorio).ejecutar()] == [creado.id]

    async def test_solo_el_administrador_configura(self) -> None:
        repositorio = RepositorioRecursoEnMemoria()

        with pytest.raises(OperacionNoPermitida) as fallo:
            await RegistrarRecurso(repositorio, PublicadorEnMemoria()).ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                nombre="Sala 2",
                tipo=TipoRecurso.ESPACIO,
                ahora=AHORA,
            )

        assert str(fallo.value) == MOTIVO_SOLO_ADMIN

    async def test_configurar_la_disponibilidad_reemplaza_el_horario_entero(self) -> None:
        recurso = un_recurso()
        repositorio = RepositorioRecursoEnMemoria(recurso)
        nuevo = (
            PatronDeDisponibilidad(
                dia_semana=3, hora_inicio=time(10), hora_fin=time(14), duracion_slot_min=60
            ),
        )

        actualizado = await ConfigurarDisponibilidad(repositorio, PublicadorEnMemoria()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            recurso_id=recurso.id,
            patrones=nuevo,
            ahora=AHORA,
        )

        # Reemplaza: el martes ya no atiende.
        assert actualizado.patrones == nuevo
        assert not actualizado.esta_disponible_en(local(15), 30)

    async def test_desactivar_no_toca_los_turnos_ya_reservados(self) -> None:
        """HU-E7-04, quinto criterio: «los turnos reservados se mantienen»."""
        recurso = un_recurso()
        turno = un_turno(recurso)
        escena = Escena(recurso, turno)

        await CambiarEstadoDeRecurso(escena.recursos, escena.publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            recurso_id=recurso.id,
            activo=False,
            ahora=AHORA,
        )

        assert _estado(escena.turnos.turnos[turno.id]) is EstadoTurno.RESERVADO
        assert not (await VerRecurso(escena.recursos).ejecutar(recurso.id)).activo

    async def test_asociar_servicios_reemplaza_la_lista(self) -> None:
        recurso = un_recurso()
        repositorio = RepositorioRecursoEnMemoria(recurso)

        actualizado = await AsociarServicios(repositorio, PublicadorEnMemoria()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            recurso_id=recurso.id,
            servicios=frozenset({COLOR.id}),
            ahora=AHORA,
        )

        assert actualizado.admite_servicio(COLOR.id)
        assert not actualizado.admite_servicio(CORTE.id)


class TestExcepciones:
    async def test_registra_una_excepcion_y_la_quita(self) -> None:
        recurso = un_recurso()
        repositorio = RepositorioRecursoEnMemoria(recurso)
        publicador = PublicadorEnMemoria()
        bloqueo = ExcepcionDeDisponibilidad(fecha=MARTES, tipo=TipoExcepcion.BLOQUEO)

        con_feriado = await RegistrarExcepcion(repositorio, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            recurso_id=recurso.id,
            excepcion=bloqueo,
            ahora=AHORA,
        )
        assert not con_feriado.esta_disponible_en(local(15), 30)

        sin_feriado = await QuitarExcepcion(repositorio, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            recurso_id=recurso.id,
            fecha=MARTES,
            ahora=AHORA,
        )
        assert sin_feriado.esta_disponible_en(local(15), 30)

    async def test_la_segunda_excepcion_para_la_misma_fecha_es_un_422_y_no_un_409(self) -> None:
        """La traducción existe para que la frase de la historia llegue a la pantalla.

        `InvarianteViolada` se mapea a 409 y el BFF descarta su detalle; `ExcepcionDuplicada`
        deriva de `EntradaInvalida`, que se mapea a 422 reenviando el texto.
        """
        from cheatsheet.contexts.scheduling.application.errors import ExcepcionDuplicada

        recurso = un_recurso()
        repositorio = RepositorioRecursoEnMemoria(recurso)
        publicador = PublicadorEnMemoria()
        caso = RegistrarExcepcion(repositorio, publicador)
        argumentos = {
            "empresa_id": EMPRESA,
            "usuario_id": USUARIO,
            "rol": RolUsuario.ADMINISTRADOR,
            "recurso_id": recurso.id,
            "ahora": AHORA,
        }
        await caso.ejecutar(
            excepcion=ExcepcionDeDisponibilidad(fecha=MARTES, tipo=TipoExcepcion.BLOQUEO),
            **argumentos,  # type: ignore[arg-type]
        )

        with pytest.raises(ExcepcionDuplicada):
            await caso.ejecutar(
                excepcion=ExcepcionDeDisponibilidad(
                    fecha=MARTES,
                    tipo=TipoExcepcion.APERTURA_ESPECIAL,
                    franja_inicio=local(20),
                    franja_duracion_min=60,
                ),
                **argumentos,  # type: ignore[arg-type]
            )


#: Martes 8 de septiembre de 2026, 12:00 hora de la agenda: «hoy», a mitad del día.
AHORA_MARTES = local(12)


async def _reservar_el_martes(
    escena: Escena,
    *,
    inicio: datetime,
    rol: RolUsuario = RolUsuario.OPERADOR,
    a_posteriori: bool = False,
) -> Turno:
    return await escena.reservar().ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        cliente_id=uuid4(),
        servicio_id=CORTE.id,
        recurso_id=escena.recurso.id,
        inicio=inicio,
        ahora=AHORA_MARTES,
        a_posteriori=a_posteriori,
    )


async def _reprogramar_el_martes(
    escena: Escena,
    turno: Turno,
    *,
    inicio: datetime,
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
    a_posteriori: bool = False,
) -> Turno:
    return await escena.reprogramar().ejecutar(
        empresa_id=EMPRESA,
        usuario_id=USUARIO,
        rol=rol,
        turno_id=turno.id,
        inicio=inicio,
        ahora=AHORA_MARTES,
        a_posteriori=a_posteriori,
    )


class TestNoEnElPasado:
    """D95: crear o reprogramar a un instante ya transcurrido se rechaza, para cualquier rol."""

    async def test_reservar_hoy_a_una_hora_anterior_a_la_actual_se_rechaza(self) -> None:
        """HU-E7-06 RN-06, con el mensaje palabra por palabra."""
        escena = Escena(un_recurso())

        with pytest.raises(TurnoEnElPasado) as fallo:
            await _reservar_el_martes(escena, inicio=local(10))

        assert str(fallo.value) == MENSAJE_TURNO_EN_EL_PASADO
        assert escena.turnos.turnos == {}
        assert escena.notificador.avisos == []

    async def test_reservar_hoy_a_una_hora_posterior_a_la_actual_se_crea(self) -> None:
        escena = Escena(un_recurso())

        turno = await _reservar_el_martes(escena, inicio=local(15))

        assert turno.franja.inicio == local(15)

    async def test_reservar_fija_cuando_se_asigno_la_franja(self) -> None:
        escena = Escena(un_recurso())

        turno = await _reservar_el_martes(escena, inicio=local(15))

        assert turno.franja_asignada_en == AHORA_MARTES

    async def test_reprogramar_vuelve_a_fijar_cuando_se_asigno_la_franja(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso, franja_asignada_en=AHORA - timedelta(days=2))
        escena = Escena(recurso, turno)

        movido = await escena.reprogramar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            turno_id=turno.id,
            inicio=local(16),
            ahora=AHORA,
        )

        assert movido.franja_asignada_en == AHORA

    @pytest.mark.parametrize("rol", [RolUsuario.OPERADOR, RolUsuario.ADMINISTRADOR])
    async def test_reprogramar_a_una_hora_ya_transcurrida_se_rechaza_y_conserva_la_franja(
        self, rol: RolUsuario
    ) -> None:
        """HU-E7-02 RN-06: vale para el Operador y para el Administrador sin la excepción."""
        recurso = un_recurso()
        turno = un_turno(recurso, franja=Franja(inicio=local(16), duracion_min=30))
        escena = Escena(recurso, turno)

        with pytest.raises(TurnoEnElPasado) as fallo:
            await escena.reprogramar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=rol,
                turno_id=turno.id,
                inicio=local(10),
                ahora=AHORA_MARTES,
            )

        assert str(fallo.value) == MENSAJE_REPROGRAMAR_AL_PASADO
        assert escena.turnos.turnos[turno.id].franja.inicio == local(16)
        assert escena.notificador.avisos == []

    async def test_reservar_un_turno_en_curso_se_rechaza(self) -> None:
        """Empezó y no terminó (`inicio < ahora < fin`): ni es futuro ni terminó."""
        escena = Escena(un_recurso())

        with pytest.raises(TurnoEnElPasado) as fallo:
            await _reservar_el_martes(escena, inicio=local(11, 45))

        assert str(fallo.value) == MENSAJE_TURNO_EN_EL_PASADO

    async def test_reservar_un_turno_en_curso_se_rechaza_tambien_a_posteriori(self) -> None:
        """La excepción pide que la franja **haya terminado**: en curso no alcanza."""
        escena = Escena(un_recurso())

        with pytest.raises(TurnoEnElPasado) as fallo:
            await _reservar_el_martes(
                escena,
                inicio=local(11, 45),
                rol=RolUsuario.ADMINISTRADOR,
                a_posteriori=True,
            )

        assert str(fallo.value) == MENSAJE_TURNO_NO_TRANSCURRIO
        assert escena.turnos.turnos == {}

    async def test_un_inicio_exactamente_igual_a_ahora_se_acepta(self) -> None:
        escena = Escena(un_recurso())

        turno = await _reservar_el_martes(escena, inicio=AHORA_MARTES)

        assert turno.franja.inicio == AHORA_MARTES

    async def test_reprogramar_a_un_inicio_igual_a_ahora_se_acepta(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso, franja=Franja(inicio=local(16), duracion_min=30))
        escena = Escena(recurso, turno)

        movido = await _reprogramar_el_martes(escena, turno, inicio=AHORA_MARTES)

        assert movido.franja.inicio == AHORA_MARTES


class TestCargaAPosteriori:
    """HU-E7-06 RN-07: la excepción exclusiva del Administrador, y sus límites."""

    async def test_nace_completado_por_panel_sin_aviso_y_deja_la_marca_en_la_bitacora(
        self,
    ) -> None:
        escena = Escena(un_recurso())
        cliente = uuid4()
        escena.con_contacto(cliente)

        turno = await escena.reservar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            cliente_id=cliente,
            servicio_id=CORTE.id,
            recurso_id=escena.recurso.id,
            inicio=local(10),
            ahora=AHORA_MARTES,
            a_posteriori=True,
        )

        assert _estado(turno) is EstadoTurno.COMPLETADO
        assert turno.canal_reserva == CanalDeReserva.PANEL
        assert turno.habilita_facturacion
        assert escena.notificador.avisos == []
        assert escena.publicador.acciones == ["cargar_turno_a_posteriori"]
        assert escena.turnos.turnos[turno.id] is turno

    async def test_el_operador_no_puede_pedirla(self) -> None:
        escena = Escena(un_recurso())

        with pytest.raises(OperacionNoPermitida) as fallo:
            await _reservar_el_martes(
                escena, inicio=local(10), rol=RolUsuario.OPERADOR, a_posteriori=True
            )

        assert str(fallo.value) == MOTIVO_SOLO_ADMIN_A_POSTERIORI
        assert escena.turnos.turnos == {}

    async def test_omite_solo_la_disponibilidad_base(self) -> None:
        """A las 6 el recurso no atiende (9 a 18), y aun así se registra lo que ocurrió."""
        escena = Escena(un_recurso())

        turno = await _reservar_el_martes(
            escena, inicio=local(6), rol=RolUsuario.ADMINISTRADOR, a_posteriori=True
        )

        assert _estado(turno) is EstadoTurno.COMPLETADO

    async def test_sigue_exigiendo_un_recurso_activo_y_un_servicio_admitido(self) -> None:
        inactivo = Escena(un_recurso(activo=False))
        sin_servicio = Escena(un_recurso(servicios=frozenset()))

        with pytest.raises(RecursoInactivo):
            await _reservar_el_martes(
                inactivo, inicio=local(10), rol=RolUsuario.ADMINISTRADOR, a_posteriori=True
            )
        with pytest.raises(ServicioNoAdmitido):
            await _reservar_el_martes(
                sin_servicio, inicio=local(10), rol=RolUsuario.ADMINISTRADOR, a_posteriori=True
            )

    async def test_deja_pasar_el_rechazo_del_motor_por_solapamiento(self) -> None:
        escena = Escena(un_recurso())
        escena.turnos.ocupado = True

        with pytest.raises(FranjaOcupada):
            await _reservar_el_martes(
                escena, inicio=local(10), rol=RolUsuario.ADMINISTRADOR, a_posteriori=True
            )


class TestCorreccionAPosteriori:
    """HU-E7-02 RN-07: mover un turno a una franja ya terminada, sin avisar."""

    async def test_mueve_el_turno_conserva_el_estado_no_avisa_y_deja_la_marca(self) -> None:
        recurso = un_recurso()
        turno = un_turno(
            recurso,
            estado=EstadoTurno.CONFIRMADO,
            franja=Franja(inicio=local(16), duracion_min=30),
        )
        escena = Escena(recurso, turno)

        movido = await _reprogramar_el_martes(escena, turno, inicio=local(10), a_posteriori=True)

        assert movido.franja.inicio == local(10)
        # No pasa a COMPLETADO solo: la asistencia se marca por el camino normal (HU-E7-03).
        assert _estado(movido) is EstadoTurno.CONFIRMADO
        assert escena.notificador.avisos == []
        assert escena.publicador.acciones == ["corregir_turno_a_posteriori"]

    async def test_el_operador_no_puede_pedirla_y_el_turno_queda_donde_estaba(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso, franja=Franja(inicio=local(16), duracion_min=30))
        escena = Escena(recurso, turno)

        with pytest.raises(OperacionNoPermitida) as fallo:
            await _reprogramar_el_martes(
                escena, turno, inicio=local(10), rol=RolUsuario.OPERADOR, a_posteriori=True
            )

        assert str(fallo.value) == MOTIVO_SOLO_ADMIN_A_POSTERIORI
        assert escena.turnos.turnos[turno.id].franja.inicio == local(16)

    async def test_una_franja_que_no_termino_se_rechaza(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso, franja=Franja(inicio=local(16), duracion_min=30))
        escena = Escena(recurso, turno)

        with pytest.raises(TurnoEnElPasado):
            await _reprogramar_el_martes(escena, turno, inicio=local(11, 45), a_posteriori=True)


#: Un servicio de 45 minutos: más largo que el slot de 30 del recurso de estos tests.
DE_45 = ServicioAgendable(id=uuid4(), nombre="Limpieza", duracion_estandar_min=45)


def _con_servicio_de_45(escena: Escena) -> Escena:
    escena.catalogo.servicios[DE_45.id] = DE_45
    escena.recurso.asociar_servicios(frozenset({DE_45.id}))
    return escena


class TestDuracionEIntervaloAlReservar:
    """HU-E7-06 RN-08 y HU-E7-04 RN-06/RN-08 (decisión D96)."""

    async def test_el_turno_dura_lo_que_dura_el_servicio_y_guarda_el_intervalo_actual(
        self,
    ) -> None:
        recurso = un_recurso()
        recurso.definir_intervalo(10)
        escena = _con_servicio_de_45(Escena(recurso))

        turno = await escena.reservar().ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.OPERADOR,
            cliente_id=uuid4(),
            servicio_id=DE_45.id,
            recurso_id=recurso.id,
            inicio=local(15),
            ahora=AHORA,
        )

        assert turno.franja.duracion_min == 45
        assert turno.intervalo_posterior_min == 10

    async def test_no_acepta_una_duracion_externa(self) -> None:
        """La duración nunca se ingresa a mano: el parámetro ya no existe."""
        escena = _con_servicio_de_45(Escena(un_recurso()))

        with pytest.raises(TypeError):
            await escena.reservar().ejecutar(  # type: ignore[call-arg]
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                cliente_id=uuid4(),
                servicio_id=DE_45.id,
                recurso_id=escena.recurso.id,
                inicio=local(15),
                ahora=AHORA,
                duracion_min=20,
            )

    async def test_rechaza_un_servicio_cuya_duracion_esta_fuera_de_5_a_480(self) -> None:
        recurso = un_recurso()
        escena = Escena(recurso)
        largo = ServicioAgendable(id=uuid4(), nombre="Largo", duracion_estandar_min=600)
        escena.catalogo.servicios[largo.id] = largo
        recurso.asociar_servicios(frozenset({largo.id}))

        with pytest.raises(EntradaInvalida) as fallo:
            await escena.reservar().ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.OPERADOR,
                cliente_id=uuid4(),
                servicio_id=largo.id,
                recurso_id=recurso.id,
                inicio=local(10),
                ahora=AHORA,
            )

        assert str(fallo.value) == MENSAJE_DURACION_DE_TURNO
        assert escena.turnos.turnos == {}

    async def test_la_carga_a_posteriori_no_lleva_intervalo(self) -> None:
        recurso = un_recurso()
        recurso.definir_intervalo(10)
        escena = Escena(recurso)

        turno = await _reservar_el_martes(
            escena, inicio=local(10), rol=RolUsuario.ADMINISTRADOR, a_posteriori=True
        )

        assert turno.intervalo_posterior_min is None

    async def test_la_correccion_a_posteriori_deja_el_intervalo_en_none(self) -> None:
        recurso = un_recurso()
        recurso.definir_intervalo(10)
        turno = un_turno(recurso, franja=Franja(inicio=local(16), duracion_min=30))
        escena = Escena(recurso, turno)

        movido = await _reprogramar_el_martes(escena, turno, inicio=local(10), a_posteriori=True)

        assert movido.intervalo_posterior_min is None


class TestReprogramarConDuracionEIntervalo:
    async def test_reprogramar_copia_el_intervalo_actual_del_recurso(self) -> None:
        recurso = un_recurso()
        turno = un_turno(recurso, intervalo_posterior_min=0)
        escena = Escena(recurso, turno)
        recurso.definir_intervalo(15)

        movido = await _reprogramar_el_martes(
            escena, turno, inicio=local(16), rol=RolUsuario.OPERADOR
        )

        assert movido.intervalo_posterior_min == 15
        assert movido.franja.duracion_min == 30

    async def test_rechaza_reprogramar_un_turno_viejo_de_mas_de_480_minutos(self) -> None:
        recurso = un_recurso()
        viejo = un_turno(recurso, franja=Franja(inicio=local(15), duracion_min=600))
        escena = Escena(recurso, viejo)

        for a_posteriori in (False, True):
            with pytest.raises(EntradaInvalida) as fallo:
                await _reprogramar_el_martes(
                    escena, viejo, inicio=local(16), a_posteriori=a_posteriori
                )

            assert str(fallo.value) == MENSAJE_DURACION_DE_TURNO
        assert escena.turnos.turnos[viejo.id].franja.inicio == local(15)


class TestVerHorariosDisponibles:
    def ver(self, escena: Escena) -> VerHorariosDisponibles:
        return VerHorariosDisponibles(
            turnos=escena.turnos, recursos=escena.recursos, servicios=escena.catalogo
        )

    async def test_ofrece_por_la_duracion_del_servicio_y_marca_el_intervalo(self) -> None:
        recurso = un_recurso()
        recurso.definir_intervalo(10)
        existente = un_turno(
            recurso, franja=Franja(inicio=local(9), duracion_min=30), intervalo_posterior_min=10
        )
        escena = _con_servicio_de_45(Escena(recurso, existente))

        grilla = await self.ver(escena).ejecutar(
            recurso_id=recurso.id, servicio_id=DE_45.id, fecha=MARTES, ahora=AHORA
        )

        por_inicio = {uno.inicio: uno.ocupado for uno in grilla}
        # Slot de 30: 09:00 y 09:30 pisan al turno o a su margen; 10:00 queda libre; el último
        # inicio es el que deja entrar un turno de 45 antes de las 18.
        assert por_inicio[local(9)]
        assert por_inicio[local(9, 30)]
        assert not por_inicio[local(10)]
        assert max(por_inicio) == local(17)

    async def test_un_servicio_que_no_se_presta_en_el_recurso_se_rechaza(self) -> None:
        escena = Escena(un_recurso())

        with pytest.raises(ServicioNoAdmitido):
            await self.ver(escena).ejecutar(
                recurso_id=escena.recurso.id, servicio_id=COLOR.id, fecha=MARTES, ahora=AHORA
            )

    async def test_un_recurso_inexistente_se_rechaza(self) -> None:
        escena = Escena(un_recurso())

        with pytest.raises(RecursoInexistente):
            await self.ver(escena).ejecutar(
                recurso_id=uuid4(), servicio_id=CORTE.id, fecha=MARTES, ahora=AHORA
            )


class TestIntervaloDelRecurso:
    async def test_configurar_el_intervalo_lo_guarda_y_registra_la_misma_accion(self) -> None:
        recurso = un_recurso()
        repositorio = RepositorioRecursoEnMemoria(recurso)
        publicador = PublicadorEnMemoria()

        actualizado = await ConfigurarDisponibilidad(repositorio, publicador).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            recurso_id=recurso.id,
            patrones=recurso.patrones,
            intervalo_entre_turnos_min=10,
            ahora=AHORA,
        )

        assert actualizado.intervalo_entre_turnos_min == 10
        assert publicador.acciones == ["configurar_disponibilidad"]

    async def test_sin_intervalo_en_el_pedido_conserva_el_actual(self) -> None:
        recurso = un_recurso()
        recurso.definir_intervalo(20)
        repositorio = RepositorioRecursoEnMemoria(recurso)

        actualizado = await ConfigurarDisponibilidad(repositorio, PublicadorEnMemoria()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            recurso_id=recurso.id,
            patrones=recurso.patrones,
            ahora=AHORA,
        )

        assert actualizado.intervalo_entre_turnos_min == 20

    async def test_un_intervalo_negativo_se_rechaza_y_no_se_guarda(self) -> None:
        recurso = un_recurso()
        repositorio = RepositorioRecursoEnMemoria(recurso)

        with pytest.raises(EntradaInvalida):
            await ConfigurarDisponibilidad(repositorio, PublicadorEnMemoria()).ejecutar(
                empresa_id=EMPRESA,
                usuario_id=USUARIO,
                rol=RolUsuario.ADMINISTRADOR,
                recurso_id=recurso.id,
                patrones=recurso.patrones,
                intervalo_entre_turnos_min=-1,
                ahora=AHORA,
            )

        assert recurso.intervalo_entre_turnos_min == 0

    async def test_registrar_un_recurso_acepta_el_intervalo_y_por_defecto_es_cero(self) -> None:
        repositorio = RepositorioRecursoEnMemoria()

        con = await RegistrarRecurso(repositorio, PublicadorEnMemoria()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            nombre="Sala 3",
            tipo=TipoRecurso.ESPACIO,
            intervalo_entre_turnos_min=15,
            ahora=AHORA,
        )
        sin = await RegistrarRecurso(repositorio, PublicadorEnMemoria()).ejecutar(
            empresa_id=EMPRESA,
            usuario_id=USUARIO,
            rol=RolUsuario.ADMINISTRADOR,
            nombre="Sala 4",
            tipo=TipoRecurso.ESPACIO,
            ahora=AHORA,
        )

        assert (con.intervalo_entre_turnos_min, sin.intervalo_entre_turnos_min) == (15, 0)
