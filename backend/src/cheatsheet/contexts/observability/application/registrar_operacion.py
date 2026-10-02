"""`RegistrarOperacion` — the single use case of HS-T5.

Two properties are worth stating because everything else in the file exists to hold
them up:

**It records failures.** RN-04 says the log is independent of the outcome, so
`resultado` is an input, never a condition. A caller reporting an error takes exactly
the same path as one reporting success.

**It is idempotent on `evento_id`.** The same occurrence delivered twice leaves one
row. The check happens twice on purpose: a read first, because that is the common case
and it costs nothing, and then the unique index in the database, because between the
read and the insert two workers can interleave and only the index is atomic. The second
one is the guarantee; the first only keeps the logs quiet.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from cheatsheet.contexts.observability.application.errors import RegistroDuplicado
from cheatsheet.contexts.observability.application.ports import PortRegistroDeAuditoria
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.shared.auditoria import EventoAuditable


@dataclass(frozen=True, slots=True)
class ResultadoDeRegistro:
    """What happened, from the caller's point of view."""

    registro_id: UUID
    #: True when this call created the row; False when the occurrence was already
    #: registered. Callers ignore it; tests and metrics do not.
    fue_creado: bool


class RegistrarOperacion:
    """Turns an auditable occurrence into a permanent line of the log."""

    def __init__(self, registros: PortRegistroDeAuditoria) -> None:
        self._registros = registros

    async def ejecutar(self, evento: EventoAuditable) -> ResultadoDeRegistro:
        existente = await self._registros.buscar_por_evento(evento.evento_id)
        if existente is not None:
            return ResultadoDeRegistro(registro_id=existente.id, fue_creado=False)

        registro = RegistroDeAuditoria(
            id=uuid4(),
            evento_id=evento.evento_id,
            empresa_id=evento.empresa_id,
            usuario_id=evento.usuario_id,
            modulo=evento.modulo,
            accion=evento.accion,
            entidad_afectada=evento.entidad_afectada,
            resultado=evento.resultado,
            direccion_ip=evento.direccion_ip,
            iniciador=evento.quien_inicio,
            # The event's own instant, read from the emitter's injected clock. The row
            # records when the operation happened, not when it got persisted.
            timestamp=evento.ocurrido_en,
            detalle=evento.detalle,
        )
        try:
            await self._registros.agregar(registro)
        except RegistroDuplicado:
            # Lost the race against a concurrent delivery. The row exists, which is all
            # the caller wanted; re-read it so the returned id is the real one.
            ganador = await self._registros.buscar_por_evento(evento.evento_id)
            if ganador is None:  # pragma: no cover — only if the index lied
                raise
            return ResultadoDeRegistro(registro_id=ganador.id, fue_creado=False)
        return ResultadoDeRegistro(registro_id=registro.id, fue_creado=True)
