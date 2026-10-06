"""`Turno` — una franja reservada, y la máquina de estados que la gobierna.

El riesgo de este contexto es uno solo y tiene nombre: **doble booking**. Dos personas con el
mismo horario con el mismo profesional es el error que el cliente descubre en la puerta del
local, y ninguna cantidad de validación en Python lo evita — entre el `SELECT` que dice
«libre» y el `INSERT` que reserva hay una ventana, y dos requests concurrentes caben en ella.

Por eso la decisión **D28**: la unicidad de la franja la garantiza una **restricción de
exclusión** de PostgreSQL sobre `(recurso_id, tstzrange(franja))`, y este archivo no intenta
duplicarla. Lo que sí vive acá es todo lo demás: qué transiciones existen, qué significa
reprogramar y cuándo se puede marcar asistencia.

**Reprogramar no es un estado** (HU-E7-01 RN-02 y HU-E7-02 RN-02, las dos explícitas). Un
turno reprogramado sigue Reservado o Confirmado; lo que cambia es la franja. La historia se
tomó el trabajo de decirlo, así que el enum no gana un valor y `reprogramar` conserva el
estado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: HU-E7-01, HU-E7-02, HU-E7-03 y HU-E7-06, palabra por palabra.
MENSAJE_SIN_TURNOS = "No hay turnos para el período seleccionado."
MENSAJE_HORARIO_OCUPADO = "El horario seleccionado no está disponible."
MENSAJE_TURNO_NO_TRANSCURRIO = "El turno aún no transcurrió."
#: HU-E7-06 RN-06 y HU-E7-02 RN-06 (decisión D95). Dos frases porque las historias dicen dos.
MENSAJE_TURNO_EN_EL_PASADO = "No se puede agendar un turno en un horario que ya pasó."
MENSAJE_REPROGRAMAR_AL_PASADO = "No se puede reprogramar un turno a un horario que ya pasó."

#: Un turno de más de un día no es un turno. El techo estructural evita que un
#: `franja_duracion_min` escrito con un cero de más bloquee la agenda de un recurso durante una
#: semana. Es el de `Franja` y el de `ck_turno_duracion`; el rango del negocio es el de abajo.
DURACION_MAXIMA_MIN = 24 * 60

#: HU-E7-06 RN-08 y HU-E7-02 RN-08 (decisión D96): un turno dura de 5 a 480 minutos. Se valida
#: acá, al crear y al reprogramar, y **no** en `Franja` ni en la base: un turno viejo de 600
#: minutos (la duración manual existía) tiene que poder leerse aunque ya no se pueda reprogramar.
DURACION_TURNO_MINIMA_MIN = 5
DURACION_TURNO_MAXIMA_MIN = 480
MENSAJE_DURACION_DE_TURNO = "La duración del turno debe estar entre 5 y 480 minutos."


def validar_duracion_de_turno(duracion_min: int) -> None:
    if not DURACION_TURNO_MINIMA_MIN <= duracion_min <= DURACION_TURNO_MAXIMA_MIN:
        raise EntradaInvalida(MENSAJE_DURACION_DE_TURNO)


class EstadoTurno(StrEnum):
    """El enum `estado_turno` del DER.

    Los cinco que HU-E7-01 RN-02 enumera, y **ningún «REPROGRAMADO»**: la misma regla dice que
    la reprogramación conserva el estado.
    """

    RESERVADO = "RESERVADO"
    CONFIRMADO = "CONFIRMADO"
    CANCELADO = "CANCELADO"
    COMPLETADO = "COMPLETADO"
    NO_SHOW = "NO_SHOW"


class CanalDeReserva(StrEnum):
    """De dónde vino la reserva (HU-E7-06 RN-02).

    El DER guarda esto como `varchar` y no como enum, así que la columna acepta lo que se le
    mande; el tipo existe igual para que el código no escriba la cadena a mano en cuatro
    lugares. `AGENTE` lo va a usar el épico 8 y está desde ahora por lo mismo que `EQUIPO`.
    """

    PANEL = "PANEL"
    AGENTE = "AGENTE"


#: Qué transiciones existen, como tabla y no como diez `if`.
#:
#: **`RESERVADO → CONFIRMADO` y no al revés.** Confirmar es el cliente diciendo que viene; que
#: se «desconfirme» solo no lo pide ninguna historia, y una transición que nadie pide es una
#: por la que después hay que preguntarse cómo llegó un turno ahí.
#:
#: **Los tres estados finales no salen.** Un turno cancelado no se reprograma: se crea otro.
#: Un completado no se vuelve no-show. Cambiar el pasado registrado es justo lo que la
#: bitácora de HU-E7-03 RN-03 existe para impedir.
TRANSICIONES_LEGALES: dict[EstadoTurno, frozenset[EstadoTurno]] = {
    EstadoTurno.RESERVADO: frozenset(
        {
            EstadoTurno.CONFIRMADO,
            EstadoTurno.CANCELADO,
            EstadoTurno.COMPLETADO,
            EstadoTurno.NO_SHOW,
        }
    ),
    EstadoTurno.CONFIRMADO: frozenset(
        {EstadoTurno.CANCELADO, EstadoTurno.COMPLETADO, EstadoTurno.NO_SHOW}
    ),
    EstadoTurno.CANCELADO: frozenset(),
    EstadoTurno.COMPLETADO: frozenset(),
    EstadoTurno.NO_SHOW: frozenset(),
}

#: Los estados sobre los que HU-E7-02 permite actuar: «el turno existe y está en estado
#: Reservado o Confirmado».
ESTADOS_ABIERTOS = frozenset({EstadoTurno.RESERVADO, EstadoTurno.CONFIRMADO})

#: Los estados cuya franja está ocupada (D95). Los abiertos, y **también el completado**: la
#: carga a posteriori nace completada y tiene que quedar protegida del solapamiento, y ya hoy un
#: turno no debería poder crearse encima de una atención realizada. `NO_SHOW` queda afuera a
#: propósito: si el cliente no vino, el recurso quedó libre de hecho. Es la misma condición que
#: la restricción de exclusión de la base (migración 0024).
ESTADOS_QUE_OCUPAN_LA_FRANJA = ESTADOS_ABIERTOS | {EstadoTurno.COMPLETADO}


@dataclass(frozen=True, slots=True)
class Franja:
    """Inicio más duración, que es como el DER la modela — no un rango.

    La restricción de exclusión de la migración construye el rango a partir de estas dos
    columnas. Guardar el rango además sería guardar el mismo hecho dos veces, con la
    posibilidad de que discrepen.
    """

    inicio: datetime
    duracion_min: int

    def __post_init__(self) -> None:
        if self.inicio.tzinfo is None:
            # Sin zona, dos turnos «a las 15» pueden ser el mismo o distintos según quién los
            # lea. La restricción de exclusión los compararía como iguales y rechazaría uno de
            # los dos sin que nadie entienda por qué.
            raise EntradaInvalida("La franja de un turno necesita zona horaria")
        if not 0 < self.duracion_min <= DURACION_MAXIMA_MIN:
            raise EntradaInvalida(
                f"La duración de un turno debe estar entre 1 y {DURACION_MAXIMA_MIN} minutos"
            )

    @property
    def fin(self) -> datetime:
        return self.inicio + timedelta(minutes=self.duracion_min)

    def empieza_antes_de(self, ahora: datetime) -> bool:
        """El inicio ya pasó. Un inicio exactamente igual a `ahora` **no** cuenta como pasado.

        Se compara el instante y nunca `.date()`: un turno de hoy a una hora que ya transcurrió
        es un turno en el pasado aunque el día sea el mismo (D95). `ahora` siempre llega de
        afuera: el dominio no lee el reloj.
        """
        return self.inicio < ahora

    def ya_termino(self, ahora: datetime) -> bool:
        """La franja completa transcurrió. Es el «ya transcurrió» de D35: contra el **fin**."""
        return ahora >= self.fin

    def se_solapa_con(self, otra: Franja) -> bool:
        """Dos franjas se solapan si una empieza antes de que la otra termine.

        Los extremos **no** se solapan: un turno de 15:00 a 16:00 y otro de 16:00 a 17:00
        conviven. Es la misma semántica del rango `[)` que usa la restricción de exclusión, y
        tiene que serlo — si acá dijera otra cosa, la pantalla y la base darían respuestas
        distintas sobre el mismo par de turnos.
        """
        return self.inicio < otra.fin and otra.inicio < self.fin


@dataclass(slots=True)
class Turno:
    """Un cliente, un servicio, un recurso y una franja."""

    id: UUID
    empresa_id: EmpresaId
    cliente_id: UUID
    servicio_id: UUID
    recurso_id: UUID
    franja: Franja
    estado: EstadoTurno = EstadoTurno.RESERVADO
    canal_reserva: str = CanalDeReserva.PANEL
    #: La seña (HU-E6-07). Se escribe desde `payments` a través del servicio de aplicación de
    #: este contexto, nunca con un join: `turno.cobro_id` cruza un límite de contexto y el DER
    #: lo declara sin FK a propósito (hallazgo H4).
    cobro_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    #: El intervalo entre turnos que se aplicó al reservar o reprogramar (decisión D96). `None`
    #: significa «sin intervalo»: la carga y la corrección a posteriori no lo respetan ni lo
    #: imponen (HU-E7-06 RN-07), y la base deja esos turnos fuera de `excl_turno_recurso_intervalo`.
    intervalo_posterior_min: int | None = 0

    @classmethod
    def registrar_a_posteriori(
        cls,
        *,
        id: UUID,
        empresa_id: EmpresaId,
        cliente_id: UUID,
        servicio_id: UUID,
        recurso_id: UUID,
        franja: Franja,
        ahora: datetime,
    ) -> Turno:
        """HU-E7-06 RN-07: una atención que ya ocurrió **nace** `COMPLETADO`, canal `PANEL`.

        No se crea `RESERVADO` para transicionar después: ese primer estado sería un turno
        abierto en una franja pasada, que es justo lo que D95 prohíbe, y obligaría a dos
        escrituras. La franja tiene que haber terminado, no sólo empezado.
        """
        if not franja.ya_termino(ahora):
            raise EntradaInvalida(MENSAJE_TURNO_NO_TRANSCURRIO)
        return cls(
            id=id,
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            servicio_id=servicio_id,
            recurso_id=recurso_id,
            franja=franja,
            estado=EstadoTurno.COMPLETADO,
            canal_reserva=CanalDeReserva.PANEL,
            created_at=ahora,
            updated_at=ahora,
            intervalo_posterior_min=None,
        )

    # -- transiciones -----------------------------------------------------------------

    def confirmar(self) -> None:
        self._transicionar_a(EstadoTurno.CONFIRMADO)

    def cancelar(self) -> None:
        """HU-E7-02. Cancelar no pide que el turno haya transcurrido ni que falte para él.

        Un turno pasado que nadie marcó se puede cancelar, y eso es deliberado: la alternativa
        deja turnos viejos en `RESERVADO` para siempre, que es ruido en toda consulta de
        ocupación.
        """
        self._transicionar_a(EstadoTurno.CANCELADO)

    def reprogramar(self, franja: Franja, intervalo_posterior_min: int | None) -> None:
        """Mueve el turno a otra franja **conservando el estado** (RN-02).

        No hay `estado` de por medio y no lo va a haber: la historia dice que la reprogramación
        no es un estado, y este método es donde esa frase se vuelve código. El intervalo es el
        **actual** del recurso, o `None` en la corrección a posteriori.
        """
        if self.estado not in ESTADOS_ABIERTOS:
            raise InvarianteViolada(
                f"Un turno {self.estado.value.lower()} no se reprograma: se crea uno nuevo"
            )
        self.franja = franja
        self.intervalo_posterior_min = intervalo_posterior_min

    def marcar_completado(self, ahora: datetime) -> None:
        """HU-E7-03. Sólo cuando el turno ya transcurrió (RN-01)."""
        self._exigir_transcurrido(ahora)
        self._transicionar_a(EstadoTurno.COMPLETADO)

    def marcar_no_show(self, ahora: datetime) -> None:
        self._exigir_transcurrido(ahora)
        self._transicionar_a(EstadoTurno.NO_SHOW)

    # -- consultas --------------------------------------------------------------------

    @property
    def esta_abierto(self) -> bool:
        return self.estado in ESTADOS_ABIERTOS

    @property
    def habilita_facturacion(self) -> bool:
        """HU-E7-03 RN-02: un turno completado habilita emitir el comprobante del servicio.

        Es una propiedad y no un flag guardado por lo mismo que en el épico 6: un dato que se
        deriva de otro y se guarda igual es un dato que algún día va a discrepar.
        """
        return self.estado is EstadoTurno.COMPLETADO

    def bloquea(self, inicio: datetime, duracion_min: int, intervalo_min: int | None) -> bool:
        """¿Este turno impide ofrecer un turno nuevo con esa franja y ese intervalo?

        Es el mismo criterio que las dos restricciones de la base (D96). Pisar la franja real
        siempre choca. Si **los dos** llevan intervalo, también choca que se pisen las franjas
        extendidas con su margen, con la semántica `[)` de siempre. Un turno a posteriori
        (`None`) sólo bloquea su franja real.
        """
        nueva = Franja(inicio=inicio, duracion_min=duracion_min)
        if self.franja.se_solapa_con(nueva):
            return True
        if self.intervalo_posterior_min is None or intervalo_min is None:
            return False
        propio_fin = self.franja.fin + timedelta(minutes=self.intervalo_posterior_min)
        nuevo_fin = nueva.fin + timedelta(minutes=intervalo_min)
        return self.franja.inicio < nuevo_fin and nueva.inicio < propio_fin

    def ya_transcurrio(self, ahora: datetime) -> bool:
        """El turno terminó. Se mide contra el **fin** de la franja, no contra el inicio.

        Marcar «no se presentó» a los cinco minutos de empezado un turno de una hora sería
        marcarlo mientras el cliente todavía puede llegar.
        """
        return self.franja.ya_termino(ahora)

    def asignar_cobro(self, cobro_id: UUID) -> None:
        """Asocia la seña (HU-E6-07).

        Un turno tiene a lo sumo una: pedir dos señas por el mismo turno es un error de quien
        las pide, y sobrescribir la primera dejaría un cobro cobrado sin turno que lo explique.
        """
        if self.cobro_id is not None and self.cobro_id != cobro_id:
            raise InvarianteViolada("El turno ya tiene una seña asociada")
        self.cobro_id = cobro_id

    # -- interno ----------------------------------------------------------------------

    def _exigir_transcurrido(self, ahora: datetime) -> None:
        if not self.ya_transcurrio(ahora):
            raise InvarianteViolada(MENSAJE_TURNO_NO_TRANSCURRIO)

    def _transicionar_a(self, destino: EstadoTurno) -> None:
        if destino not in TRANSICIONES_LEGALES[self.estado]:
            raise InvarianteViolada(
                f"Un turno {self.estado.value.lower()} no puede pasar a {destino.value.lower()}"
            )
        self.estado = destino
