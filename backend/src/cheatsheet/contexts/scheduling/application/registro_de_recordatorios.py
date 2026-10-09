"""Lo que el envío de recordatorios deja dicho: la bitácora, los logs de descarte y la vigencia.

Piezas sin estado que `EnvioDeRecordatorios` usa para contar qué pasó con una fila. Aparte para que el
orquestador del envío en tres tiempos quede legible.

Ningún log ni evento lleva el nombre, el teléfono ni el texto: solo ids, la anticipación y el motivo.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    ANTICIPACION_QUITADA,
    ANTICIPACION_SUPERADA,
    FRANJA_CAMBIADA,
    TURNO_CERRADO,
    TURNO_EMPEZADO,
    RecordatorioDeTurno,
)
from cheatsheet.contexts.scheduling.domain.turno import Turno
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)

#: Lo que escribe la bitácora: `usuario_id=None` dice que actuó el sistema (el barrido).
ACCION_DE_BITACORA = "enviar_recordatorio_de_turno"

#: `detalle["desenlace"]` de la bitácora: separa lo que salió de lo que se descartó (que además lleva
#: `detalle["motivo"]`) sin tener que mirar el resultado.
ENVIADO = "ENVIADO"
FALLIDO = "FALLIDO"
DESCARTADO = "DESCARTADO"


class Desenlace(StrEnum):
    """Cómo terminó el trato con una fila o un turno, para los contadores del barrido."""

    SALIO = "SALIO"
    FALLO = "FALLO"
    EN_REINTENTO = "EN_REINTENTO"
    OMITIDO = "OMITIDO"
    DESCARTADO = "DESCARTADO"
    #: No se mandó nada ni se cambió el resultado (otro barrido la tenía, o nada la hacía caber).
    NADA = "NADA"
    #: No se pudo registrar lo que pasó: la fila queda «en curso» y se resolverá `INCIERTO` al vencer
    #: su ventana. Nunca se reenvía.
    SIN_REGISTRAR = "SIN_REGISTRAR"


async def publicar_resultado(
    publicador: PublicadorDeEventos,
    recordatorio: RecordatorioDeTurno,
    ahora: datetime,
    resultado: Resultado,
    *,
    detalle: Mapping[str, str] | None = None,
) -> None:
    """`enviar_recordatorio_de_turno`: **una vez por recordatorio**, al terminar.

    Un intento intermedio que espera su reintento no es una falla de la bitácora. Sin datos
    personales: el sistema actuó (`usuario_id=None`) y la entidad es el turno.
    """
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=EmpresaId(recordatorio.empresa_id),
            ocurrido_en=ahora,
            usuario_id=None,
            modulo=Modulo.SCHEDULING,
            accion=ACCION_DE_BITACORA,
            entidad_afectada=f"Turno:{recordatorio.turno_id}",
            resultado=resultado,
            detalle=detalle,
        )
    )


async def publicar_descarte(
    publicador: PublicadorDeEventos, recordatorio: RecordatorioDeTurno, ahora: datetime
) -> None:
    """Un descarte no es una falla: queda en el log y en la bitácora como resultado completado."""
    motivo = recordatorio.ultimo_error or ""
    logger.info(
        "recordatorio_de_turno_descartado",
        turno_id=str(recordatorio.turno_id),
        anticipacion_min=recordatorio.anticipacion_min,
        motivo=motivo,
    )
    await publicar_resultado(
        publicador,
        recordatorio,
        ahora,
        Resultado.COMPLETADO,
        detalle={"desenlace": DESCARTADO, "motivo": motivo},
    )


def motivo_de_descarte(
    turno: Turno | None, recordatorio: RecordatorioDeTurno, ahora: datetime
) -> str | None:
    """Por qué una fila que esperaba ya no corresponde, o `None` si sigue vigente (D-U8-4)."""
    if turno is None or not turno.esta_abierto:
        return TURNO_CERRADO
    if turno.franja.inicio != recordatorio.franja_inicio:
        return FRANJA_CAMBIADA
    if ahora >= recordatorio.franja_inicio:
        return TURNO_EMPEZADO
    return None


def motivo_de_agenda(
    recordatorio: RecordatorioDeTurno,
    del_turno: Collection[RecordatorioDeTurno],
    vigentes: Collection[int] | None,
) -> str | None:
    """Por qué una fila que esperaba su reintento ya no corresponde según la agenda y sus hermanas.

    - `ANTICIPACION_QUITADA`: la empresa sacó esa anticipación de la agenda (`vigentes` es `None`
      cuando no se sabe, y entonces no se juzga).
    - `ANTICIPACION_SUPERADA`: el mismo turno, con la misma franja, ya tiene una fila de una
      anticipación **más cercana**: un aviso de 24 h no puede salir después de uno de 2 h.
    """
    if vigentes is not None and recordatorio.anticipacion_min not in vigentes:
        return ANTICIPACION_QUITADA
    if any(
        otra.id != recordatorio.id
        and otra.franja_inicio == recordatorio.franja_inicio
        and otra.anticipacion_min < recordatorio.anticipacion_min
        for otra in del_turno
    ):
        return ANTICIPACION_SUPERADA
    return None


__all__ = [
    "ACCION_DE_BITACORA",
    "DESCARTADO",
    "ENVIADO",
    "FALLIDO",
    "Desenlace",
    "motivo_de_agenda",
    "motivo_de_descarte",
    "publicar_descarte",
    "publicar_resultado",
]
