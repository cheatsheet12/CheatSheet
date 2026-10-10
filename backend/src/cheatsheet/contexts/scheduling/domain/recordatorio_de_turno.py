"""`RecordatorioDeTurno` — un aviso de un turno y la regla de cuándo corresponde mandarlo.

Una fila por `(turno, anticipación, franja)`. **La idempotencia vive en el índice único de la
migración 0040**, no en una ventana de tiempo: el mismo criterio que D25 en cobros. El estado de
entrega (enviado, entregado, leído) no se duplica acá: vive en el mensaje `SISTEMA` del hilo.

Estados de una fila, por sus columnas (`resultado` / `intentos` / `proximo_intento_en` /
`ultimo_error`): envío en curso (nulo/n/ventana/nulo), esperando reintento (nulo/n/espera/código),
y los cuatro finales `ENVIADO`, `FALLIDO`, `OMITIDO` y `DESCARTADO` (con `procesado_en`).

El dominio no lee el reloj: `ahora` siempre llega de afuera. Todas las comparaciones son entre
instantes; la zona horaria solo interviene al mostrar la fecha, y eso no es de este módulo.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.scheduling.domain.turno import Turno
from cheatsheet.shared.errors import EntradaInvalida

#: Los límites de la columna `anticipacion_min` (1 a 168 horas, como la regla de agenda).
ANTICIPACION_MINIMA_MIN = 60
ANTICIPACION_MAXIMA_MIN = 168 * 60
#: El largo de la columna `ultimo_error`.
LARGO_MAXIMO_ULTIMO_ERROR = 60

#: Intentos en total, esperas de 15 y 30 minutos (D-U8-8). Más que eso convertiría un aviso
#: «para mañana» en uno que llega cuando el cliente ya está en camino.
REINTENTOS_MAXIMOS = 3
#: La espera tras el intento `n` es `ESPERA_BASE * 2 ** (n - 1)`.
ESPERA_BASE = timedelta(minutes=15)
#: Cuánto puede tardar un envío en curso antes de darlo por perdido, medido desde la reserva. Pasada
#: la ventana se sabe que el proceso murió **después de empezar** y no se sabe si Meta lo aceptó.
VENTANA_DE_ENVIO = timedelta(minutes=30)

#: Motivos de `ultimo_error` que no son un código del canal.
ANTICIPACION_SUPERADA = "ANTICIPACION_SUPERADA"
SIN_TELEFONO = "SIN_TELEFONO"
TURNO_CERRADO = "TURNO_CERRADO"
FRANJA_CAMBIADA = "FRANJA_CAMBIADA"
TURNO_EMPEZADO = "TURNO_EMPEZADO"
INCIERTO = "INCIERTO"


class ResultadoDeRecordatorio(StrEnum):
    """El `resultado` de la fila. Nulo significa «todavía no terminó» (en curso o esperando)."""

    ENVIADO = "ENVIADO"
    FALLIDO = "FALLIDO"
    OMITIDO = "OMITIDO"
    DESCARTADO = "DESCARTADO"


@dataclass(slots=True)
class RecordatorioDeTurno:
    id: UUID
    empresa_id: UUID
    turno_id: UUID
    anticipacion_min: int
    #: La franja del turno **cuando se creó la fila**: junto con el turno y la anticipación, la
    #: clave de idempotencia. Reprogramar cambia la franja y por eso genera claves nuevas.
    franja_inicio: datetime
    created_at: datetime
    resultado: ResultadoDeRecordatorio | None = None
    intentos: int = 0
    proximo_intento_en: datetime | None = None
    ultimo_error: str | None = None
    procesado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not ANTICIPACION_MINIMA_MIN <= self.anticipacion_min <= ANTICIPACION_MAXIMA_MIN:
            raise EntradaInvalida(
                "La anticipación de un recordatorio debe estar entre 1 y 168 horas."
            )
        if self.intentos < 0:
            raise EntradaInvalida("Los intentos de un recordatorio no pueden ser negativos.")

    @classmethod
    def para(
        cls, *, id: UUID, turno: Turno, anticipacion_min: int, ahora: datetime
    ) -> RecordatorioDeTurno:
        """La fila de un turno para una anticipación, atada a su franja de hoy."""
        return cls(
            id=id,
            empresa_id=turno.empresa_id,
            turno_id=turno.id,
            anticipacion_min=anticipacion_min,
            franja_inicio=turno.franja.inicio,
            created_at=ahora,
        )

    @property
    def momento(self) -> datetime:
        """Desde cuándo corresponde mandarlo: el inicio del turno menos la anticipación."""
        return self.franja_inicio - timedelta(minutes=self.anticipacion_min)

    # ------------------------------------------------------------------ ciclo del envío

    def iniciar_intento(self, ahora: datetime) -> None:
        """Empieza un envío: cuenta el intento y abre la ventana. Se confirma **antes** del canal."""
        self.intentos += 1
        self.proximo_intento_en = ahora + VENTANA_DE_ENVIO
        self.ultimo_error = None

    def marcar_enviado(self, ahora: datetime) -> None:
        self._cerrar(ResultadoDeRecordatorio.ENVIADO, ahora, None)

    def fallar(self, ahora: datetime, codigo: str) -> None:
        self._cerrar(ResultadoDeRecordatorio.FALLIDO, ahora, codigo)

    def omitir(self, ahora: datetime, motivo: str) -> None:
        """No corresponde mandarlo (otra anticipación más cercana, sin teléfono)."""
        self._cerrar(ResultadoDeRecordatorio.OMITIDO, ahora, motivo)

    def descartar(self, ahora: datetime, motivo: str) -> None:
        """El turno cambió mientras la fila esperaba: no se manda y no es una falla."""
        self._cerrar(ResultadoDeRecordatorio.DESCARTADO, ahora, motivo)

    def registrar_falla(self, ahora: datetime, *, codigo: str, transitoria: bool) -> bool:
        """Cierra un intento fallido. Devuelve `True` si queda programado otro.

        Solo una falla **transitoria** con intentos disponibles espera, y solo si la espera cae
        **antes** del turno: nunca se recuerda un turno que ya empezó (D-U8-8). Una permanente
        (incluido el 131047) o una incierta (timeout de lectura: Meta pudo haberlo aceptado) deja
        la fila `FALLIDO` sin reenvío.
        """
        if not transitoria or self.intentos >= REINTENTOS_MAXIMOS:
            self.fallar(ahora, codigo)
            return False
        proximo = ahora + ESPERA_BASE * 2 ** (self.intentos - 1)
        if proximo >= self.franja_inicio:
            self.descartar(ahora, TURNO_EMPEZADO)
            return False
        self.proximo_intento_en = proximo
        self.ultimo_error = codigo[:LARGO_MAXIMO_ULTIMO_ERROR]
        return True

    def _cerrar(
        self, resultado: ResultadoDeRecordatorio, ahora: datetime, motivo: str | None
    ) -> None:
        self.resultado = resultado
        self.procesado_en = ahora
        self.proximo_intento_en = None
        self.ultimo_error = motivo[:LARGO_MAXIMO_ULTIMO_ERROR] if motivo else None

    # ------------------------------------------------------------------ consultas

    @property
    def terminado(self) -> bool:
        return self.resultado is not None

    @property
    def envio_en_curso(self) -> bool:
        """Se reservó y el canal todavía no contestó (o el proceso murió en el medio)."""
        return (
            not self.terminado
            and self.intentos > 0
            and self.proximo_intento_en is not None
            and self.ultimo_error is None
        )

    @property
    def esperando_reintento(self) -> bool:
        return (
            not self.terminado
            and self.proximo_intento_en is not None
            and self.ultimo_error is not None
        )

    def envio_perdido(self, ahora: datetime) -> bool:
        """La ventana de un envío en curso venció sin resultado: **incierto**, nunca se reenvía."""
        return (
            self.envio_en_curso
            and self.proximo_intento_en is not None
            and self.proximo_intento_en <= ahora
        )

    def reintento_vencido(self, ahora: datetime) -> bool:
        """Le toca el reintento: esperaba y su fecha se cumplió."""
        return (
            self.esperando_reintento
            and self.proximo_intento_en is not None
            and self.proximo_intento_en <= ahora
        )


@dataclass(frozen=True, slots=True)
class PlanDeRecordatorio:
    """Qué hacer con un turno en este barrido: a lo sumo una anticipación para mandar."""

    #: La anticipación (en minutos) a mandar, o `None`.
    enviar: int | None = None
    #: Las que corresponden pero ya no tienen sentido: quedan como filas `OMITIDO`.
    omitir: tuple[int, ...] = field(default_factory=tuple)


def que_corresponde(
    turno: Turno,
    anticipaciones_min: Collection[int],
    existentes: Collection[RecordatorioDeTurno],
    ahora: datetime,
) -> PlanDeRecordatorio:
    """Qué recordatorio le toca a un turno ahora (D-U8-3). Función pura.

    Para una anticipación `h` y el inicio `I`, el momento es `M = I - h`. Corresponde si
    `M <= ahora < I`, si `M >= F` (la franja ya estaba fijada cuando el momento llegó) y si no hay
    fila para `(turno, h, I)`. Si corresponden varias a la vez (worker caído) sale **solo la más
    cercana al turno**, y las demás —y cualquiera que ya tenga una más cercana resuelta— quedan
    `OMITIDO`. Un turno cerrado, o que ya empezó, no recibe nada.
    """
    inicio = turno.franja.inicio
    if not turno.esta_abierto or ahora >= inicio:
        return PlanDeRecordatorio()
    fijada = turno.franja_asignada_en or turno.created_at
    hechas = {fila.anticipacion_min for fila in existentes if fila.franja_inicio == inicio}

    candidatas = sorted(
        h
        for h in set(anticipaciones_min)
        if h not in hechas
        and inicio - timedelta(minutes=h) <= ahora
        and (fijada is None or inicio - timedelta(minutes=h) >= fijada)
    )
    if not candidatas:
        return PlanDeRecordatorio()
    mas_cercana_hecha = min(hechas, default=None)
    if mas_cercana_hecha is not None and candidatas[0] > mas_cercana_hecha:
        return PlanDeRecordatorio(omitir=tuple(candidatas))
    return PlanDeRecordatorio(enviar=candidatas[0], omitir=tuple(candidatas[1:]))


__all__ = [
    "ANTICIPACION_MAXIMA_MIN",
    "ANTICIPACION_MINIMA_MIN",
    "ANTICIPACION_SUPERADA",
    "ESPERA_BASE",
    "FRANJA_CAMBIADA",
    "INCIERTO",
    "LARGO_MAXIMO_ULTIMO_ERROR",
    "REINTENTOS_MAXIMOS",
    "SIN_TELEFONO",
    "TURNO_CERRADO",
    "TURNO_EMPEZADO",
    "VENTANA_DE_ENVIO",
    "PlanDeRecordatorio",
    "RecordatorioDeTurno",
    "ResultadoDeRecordatorio",
    "que_corresponde",
]
