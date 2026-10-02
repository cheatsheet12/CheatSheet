"""`RecursoReservable` — qué se puede reservar, y cuándo.

Este archivo contesta una sola pregunta, y la contesta sin base de datos: **¿este recurso
atiende en esta franja?** De esa respuesta dependen las tres cosas que el épico promete —que
el panel no ofrezca un horario que no existe, que el agente de WhatsApp del épico 8 tampoco lo
ofrezca, y que un turno creado a mano caiga dentro del horario de atención.

Dos decisiones viven acá, y las dos son de forma:

1. **La disponibilidad se calcula, no se materializa.** No hay una tabla de slots libres. Un
   patrón semanal más sus excepciones alcanza para responder por cualquier fecha, incluida una
   de dentro de un año, y una tabla de slots habría que barrerla, extenderla y mantenerla
   consistente con cada cambio de horario. Lo que se guarda es la regla; el slot se deriva.

2. **La excepción le gana al patrón** (HU-E7-05 RN-03), y hay **una sola excepción por día y
   recurso** (RN-02). No se comparan excepciones entre sí buscando contradicciones: si sólo
   puede haber una, no hay con qué contradecirse. La regla se vuelve un índice único en la
   migración, que es donde una regla de unicidad se sostiene de verdad.

**El día de la semana es el de Python** —lunes 0, domingo 6— y el horario es **hora local de
la agenda**. Guardar `time` sin zona y compararlo contra un `datetime` con zona es un error
silencioso clásico, así que la conversión pasa por un solo lugar: `_local`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: La zona en la que se leen los horarios de atención.
#:
#: Es una constante y no un dato de la empresa porque el DER no le da zona horaria a `empresa`
#: —sólo `usuario.pref_zona_horaria`, que es una preferencia de visualización y no el horario
#: en el que el local abre—. Una empresa que atienda en otro huso necesita esa columna primero;
#: está anotado en los pendientes del épico.
#:
#: Declarada acá y no importada de `identity`: la regla R3 prohíbe cruzar dominios, y una
#: constante compartida entre contextos sería justamente eso. Que digan lo mismo hoy es una
#: coincidencia del país, no un acoplamiento.
ZONA_DE_LA_AGENDA = ZoneInfo("America/Argentina/Buenos_Aires")

#: HU-E7-04 y HU-E7-05, palabra por palabra.
MENSAJE_HORARIO_INVERTIDO = "La hora de inicio debe ser anterior a la hora de fin."
MENSAJE_EXCEPCION_DUPLICADA = "Ya existe una excepción para esa fecha en este recurso."
MENSAJE_SIN_NOMBRE = "El recurso debe tener un nombre."

#: Cuánto puede durar un slot (HU-E7-04 RN-05, decisión D96). El piso evita un patrón con
#: `duracion_slot_min=0`, que haría infinita cualquier enumeración de horarios. El slot es sólo
#: el **paso** de la grilla de inicios: la duración del turno es la del servicio.
DURACION_SLOT_MINIMA_MIN = 5
DURACION_SLOT_MAXIMA_MIN = 480
MENSAJE_DURACION_SLOT = "La duración del slot debe estar entre 5 y 480 minutos."
MENSAJE_SLOT_MAYOR_QUE_FRANJA = "La duración del slot no puede superar la extensión de la franja."

#: El intervalo entre turnos de un recurso (HU-E7-04 RN-06): cero por defecto, máximo 480.
INTERVALO_MINIMO_MIN = 0
INTERVALO_MAXIMO_MIN = 480
MENSAJE_INTERVALO = "El intervalo entre turnos debe estar entre 0 y 480 minutos."


class TipoRecurso(StrEnum):
    """El enum `tipo_recurso` del DER.

    `EQUIPO` no aparece en HU-E7-04 —la historia dice «persona o espacio»— y está igual porque
    el DER lo tiene. Un enum de almacenamiento incompleto se paga en una migración; uno con un
    valor que todavía nadie eligió no cuesta nada.
    """

    PERSONA = "PERSONA"
    ESPACIO = "ESPACIO"
    EQUIPO = "EQUIPO"


class TipoExcepcion(StrEnum):
    """El enum `tipo_excepcion` del DER.

    `BLOQUEO` es un día sin atención; `APERTURA_ESPECIAL` es un día con horario distinto del
    habitual. Los dos casos de HU-E7-05 RN-01, y no hay un tercero.
    """

    BLOQUEO = "BLOQUEO"
    APERTURA_ESPECIAL = "APERTURA_ESPECIAL"


def _local(instante: datetime) -> datetime:
    """El mismo instante, leído en la zona de la agenda.

    Todo lo que compara un `datetime` contra un `time` del patrón pasa por acá. Es una función
    de tres líneas y existe para que sea imposible olvidarse de la conversión en el cuarto
    lugar que la necesite.
    """
    if instante.tzinfo is None:
        raise EntradaInvalida("La franja de un turno necesita zona horaria")
    return instante.astimezone(ZONA_DE_LA_AGENDA)


@dataclass(frozen=True, slots=True)
class PatronDeDisponibilidad:
    """Un día de la semana y la franja en la que el recurso atiende ese día.

    Frozen: cambiar el horario de atención es reemplazar el patrón, no mutarlo. Un patrón
    mutable dejaría turnos ya reservados apoyados en una regla que cambió debajo.
    """

    dia_semana: int
    hora_inicio: time
    hora_fin: time
    duracion_slot_min: int

    def __post_init__(self) -> None:
        if not 0 <= self.dia_semana <= 6:
            raise EntradaInvalida("El día de la semana va de 0 (lunes) a 6 (domingo)")
        if self.hora_inicio >= self.hora_fin:
            # HU-E7-04, criterio 3. La frase es la de la historia y el test la afirma letra
            # por letra.
            raise EntradaInvalida(MENSAJE_HORARIO_INVERTIDO)
        if not DURACION_SLOT_MINIMA_MIN <= self.duracion_slot_min <= DURACION_SLOT_MAXIMA_MIN:
            # HU-E7-04 RN-05, letra por letra.
            raise EntradaInvalida(MENSAJE_DURACION_SLOT)
        if self.duracion_slot_min > self._extension_min():
            raise EntradaInvalida(MENSAJE_SLOT_MAYOR_QUE_FRANJA)

    def _extension_min(self) -> int:
        """Cuántos minutos dura la franja del patrón (`hora_inicio < hora_fin` ya se validó)."""
        desde = self.hora_inicio.hour * 60 + self.hora_inicio.minute
        hasta = self.hora_fin.hour * 60 + self.hora_fin.minute
        return hasta - desde

    def cubre(self, inicio: datetime, duracion_min: int) -> bool:
        """¿Esta franja entra entera dentro del patrón, en el día que le toca?

        **Entera**: un turno que empieza a las 17:45 y dura media hora no entra en un horario
        que cierra a las 18. Aceptarlo sería ofrecer un turno que termina con el local cerrado.
        """
        local = _local(inicio)
        if local.weekday() != self.dia_semana:
            return False
        fin = local + timedelta(minutes=duracion_min)
        # Un turno que cruza la medianoche no puede entrar en un patrón de un solo día, y esta
        # comparación lo rechaza sin caso especial: su fecha de fin es otra.
        if fin.date() != local.date():
            return False
        return self.hora_inicio <= local.time() and fin.time() <= self.hora_fin


@dataclass(frozen=True, slots=True)
class ExcepcionDeDisponibilidad:
    """Un día que no se comporta como los demás (HU-E7-05).

    Un `BLOQUEO` no lleva franja: es el día entero cerrado. Una `APERTURA_ESPECIAL` sí, y **es
    el horario completo de ese día** — no se suma al patrón, lo reemplaza (RN-03). Sumarlos
    haría que abrir un domingo a la mañana abriera también el horario del lunes.
    """

    fecha: date
    tipo: TipoExcepcion
    franja_inicio: datetime | None = None
    franja_duracion_min: int | None = None

    def __post_init__(self) -> None:
        if self.tipo is TipoExcepcion.APERTURA_ESPECIAL:
            if self.franja_inicio is None or self.franja_duracion_min is None:
                raise EntradaInvalida("Una apertura especial necesita horario")
            if self.franja_duracion_min <= 0:
                raise EntradaInvalida("Una apertura especial necesita duración positiva")
            if _local(self.franja_inicio).date() != self.fecha:
                raise EntradaInvalida("El horario de la apertura no cae en la fecha indicada")
        elif self.franja_inicio is not None or self.franja_duracion_min is not None:
            # Un bloqueo con horario sería ambiguo: ¿cierra el día o cierra ese rato? El DER
            # deja las dos columnas nulas para el bloqueo, y aceptar una a medias produciría
            # filas que dos lectores distintos interpretan de dos maneras.
            raise EntradaInvalida("Un bloqueo cierra el día entero y no lleva horario")

    def cubre(self, inicio: datetime, duracion_min: int) -> bool:
        """¿La excepción deja pasar esta franja?

        Un bloqueo nunca. Una apertura especial, sólo si la franja entra entera en la suya.
        """
        # `__post_init__` garantiza que una apertura tenga las dos columnas; el `or` explícito
        # es para mypy y no para el caso, que no puede darse.
        if self.tipo is TipoExcepcion.BLOQUEO or self.franja_inicio is None:
            return False
        apertura_inicio = _local(self.franja_inicio)
        apertura_fin = apertura_inicio + timedelta(minutes=self.franja_duracion_min or 0)
        local = _local(inicio)
        return apertura_inicio <= local and local + timedelta(minutes=duracion_min) <= apertura_fin


@dataclass(slots=True)
class RecursoReservable:
    """Una persona, un espacio o un equipo que se puede reservar.

    Los servicios asociados son parte del agregado y no una tabla suelta: HU-E7-04 RN-02 dice
    que **sólo** esos servicios pueden reservarse en el recurso, y esa es una regla que el
    recurso tiene que poder contestar sin ir a buscar nada.
    """

    id: UUID
    empresa_id: EmpresaId
    nombre: str
    tipo: TipoRecurso
    activo: bool = True
    patrones: tuple[PatronDeDisponibilidad, ...] = ()
    excepciones: tuple[ExcepcionDeDisponibilidad, ...] = ()
    servicios: frozenset[UUID] = field(default_factory=frozenset)
    created_at: datetime | None = None
    #: Minutos que se agregan después de cada turno (HU-E7-04 RN-06). Cambiarlo aplica a las
    #: reservas nuevas y **no mueve** los turnos existentes (RN-08): cada turno guarda el que
    #: se aplicó al reservarlo.
    intervalo_entre_turnos_min: int = 0

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise EntradaInvalida(MENSAJE_SIN_NOMBRE)
        _validar_intervalo(self.intervalo_entre_turnos_min)

    # -- configuración ----------------------------------------------------------------

    def definir_disponibilidad(self, patrones: tuple[PatronDeDisponibilidad, ...]) -> None:
        """Reemplaza la disponibilidad semanal entera.

        Reemplaza y no acumula, por lo mismo que la cadena de recordatorios del épico 6: un
        recurso tiene **un** horario de atención. Guardar versiones obligaría a desempatar
        entre dos patrones del mismo día, y el desempate no lo pide ninguna historia.
        """
        self.patrones = tuple(patrones)

    def definir_intervalo(self, minutos: int) -> None:
        """Cambia el intervalo entre turnos. Sólo aplica a reservas y reprogramaciones nuevas."""
        _validar_intervalo(minutos)
        self.intervalo_entre_turnos_min = minutos

    def agregar_excepcion(self, excepcion: ExcepcionDeDisponibilidad) -> None:
        """Registra una excepción, o se niega si ya hay una para esa fecha (RN-02).

        «Contradice» y «ya existe» son la misma cosa acá: con una sola excepción por fecha, la
        segunda siempre contradice a la primera, sea del tipo que sea. La frase es la de la
        historia.
        """
        if any(una.fecha == excepcion.fecha for una in self.excepciones):
            raise InvarianteViolada(MENSAJE_EXCEPCION_DUPLICADA)
        self.excepciones = (*self.excepciones, excepcion)

    def quitar_excepcion(self, fecha: date) -> None:
        """Saca la excepción de esa fecha, si la hay.

        Es la única forma de cambiar una excepción: se quita y se agrega. Un «editar» tendría
        que decidir qué pasa cuando cambia el tipo, y quitar más agregar ya lo decide.
        """
        self.excepciones = tuple(una for una in self.excepciones if una.fecha != fecha)

    def asociar_servicios(self, servicios: frozenset[UUID]) -> None:
        self.servicios = servicios

    def desactivar(self) -> None:
        """Deja de aceptar reservas nuevas (HU-E7-04 RN-03).

        **No toca los turnos ya reservados**, y por eso no los recibe ni los mira: un método
        que pudiera cancelarlos sería un método que alguien va a llamar por error el día que
        una persona se toma vacaciones.
        """
        self.activo = False

    def activar(self) -> None:
        self.activo = True

    # -- consultas --------------------------------------------------------------------

    def admite_servicio(self, servicio_id: UUID) -> bool:
        """HU-E7-04 RN-02 y HU-E7-06 RN-03.

        Un recurso **sin** servicios asociados no admite ninguno. La alternativa —«sin lista,
        todos»— convertiría un recurso a medio configurar en uno que acepta cualquier reserva,
        que es el error que se descubre cuando alguien ya reservó.
        """
        return servicio_id in self.servicios

    def esta_disponible_en(self, inicio: datetime, duracion_min: int) -> bool:
        """¿El recurso atiende en esta franja?

        No dice nada sobre si la franja está **ocupada**: eso lo contesta la restricción de
        exclusión de PostgreSQL (decisión D28), porque es lo único que lo puede contestar sin
        una carrera. Acá se responde sólo por el horario de atención.
        """
        if not self.activo:
            return False
        if duracion_min <= 0:
            raise EntradaInvalida("La duración de un turno debe ser positiva")
        fecha = _local(inicio).date()
        excepcion = self.excepcion_de(fecha)
        if excepcion is not None:
            # La excepción **reemplaza** al patrón, no se suma (RN-03).
            return excepcion.cubre(inicio, duracion_min)
        return any(patron.cubre(inicio, duracion_min) for patron in self.patrones)

    def excepcion_de(self, fecha: date) -> ExcepcionDeDisponibilidad | None:
        return next((una for una in self.excepciones if una.fecha == fecha), None)

    def horarios_del_dia(self, fecha: date, duracion_min: int) -> tuple[datetime, ...]:
        """Los comienzos de turno que el recurso ofrece ese día para un turno de `duracion_min`.

        Los inicios siguen el **paso del slot**, y el último es el último cuyo **turno** (no el
        slot) termina dentro de la franja. El intervalo posterior al último turno puede pasarse
        de `hora_fin` (HU-E7-04 RN-07), así que no se descuenta acá. **No dice cuáles están
        libres** —eso sale de cruzar con los turnos ya reservados—, dice cuáles existen.
        """
        excepcion = self.excepcion_de(fecha)
        if excepcion is not None:
            return self._horarios_de_la_excepcion(excepcion, duracion_min)
        return tuple(
            momento
            for patron in sorted(self.patrones, key=lambda uno: uno.hora_inicio)
            if patron.dia_semana == fecha.weekday()
            for momento in _slots(
                fecha, patron.hora_inicio, patron.hora_fin, patron.duracion_slot_min, duracion_min
            )
        )

    def _horarios_de_la_excepcion(
        self, excepcion: ExcepcionDeDisponibilidad, duracion_min: int
    ) -> tuple[datetime, ...]:
        if excepcion.tipo is TipoExcepcion.BLOQUEO or excepcion.franja_inicio is None:
            return ()
        inicio = _local(excepcion.franja_inicio)
        fin = inicio + timedelta(minutes=excepcion.franja_duracion_min or 0)
        # La apertura especial no trae duración de slot propia —el DER no le da la columna—,
        # así que hereda la del patrón de ese día, y si no hay patrón, la del recurso. Sin
        # ninguno de los dos no hay con qué cortar la franja y se ofrece su inicio, si el turno
        # entra.
        paso = self._duracion_de_slot(excepcion.fecha)
        if paso is None:
            entra = inicio + timedelta(minutes=duracion_min) <= fin
            return (inicio,) if entra else ()
        return _slots(excepcion.fecha, inicio.time(), fin.time(), paso, duracion_min)

    def _duracion_de_slot(self, fecha: date) -> int | None:
        del_dia = [uno for uno in self.patrones if uno.dia_semana == fecha.weekday()]
        candidatos = del_dia or list(self.patrones)
        return min((uno.duracion_slot_min for uno in candidatos), default=None)


def _validar_intervalo(minutos: int) -> None:
    if not INTERVALO_MINIMO_MIN <= minutos <= INTERVALO_MAXIMO_MIN:
        raise EntradaInvalida(MENSAJE_INTERVALO)


def _slots(
    fecha: date, desde: time, hasta: time, paso_min: int, duracion_min: int
) -> tuple[datetime, ...]:
    """Los comienzos de turno entre dos horas, cada `paso_min` minutos.

    El último inicio es el último cuyo **turno** termina antes del cierre: ofrecer uno que se
    pasa sería ofrecer un turno que no cabe.
    """
    inicio = datetime.combine(fecha, desde, tzinfo=ZONA_DE_LA_AGENDA)
    cierre = datetime.combine(fecha, hasta, tzinfo=ZONA_DE_LA_AGENDA)
    paso = timedelta(minutes=paso_min)
    duracion = timedelta(minutes=duracion_min)
    momentos: list[datetime] = []
    actual = inicio
    while actual + duracion <= cierre:
        momentos.append(actual)
        actual += paso
    return tuple(momentos)
