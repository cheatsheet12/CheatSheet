"""The use cases of HS-T4 — syncing ARCA's catalogue and reading it back by date.

Two operations with opposite risk profiles. The sync runs unattended once a day and its
worst failure is doing too much; the query runs on every issued document and its worst
failure is answering with today's rate for a document dated in March.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import uuid4

from cheatsheet.contexts.reference_data.application.ports import (
    EntradaDeCatalogo,
    PortCatalogosFiscales,
    PortRepositorioParametros,
)
from cheatsheet.contexts.reference_data.domain.parametro import (
    ParametroFiscal,
    TipoCatalogoFiscal,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import ErrorDeDominio, InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos


@dataclass(frozen=True, slots=True)
class ResultadoDeSincronizacion:
    """What one run changed. All three are zero on a run that found nothing new."""

    nuevos: int
    cerrados: int
    #: True when ARCA could not be reached. RN-04: the previous catalogue is kept.
    fallo: bool = False

    @property
    def hubo_cambios(self) -> bool:
        return bool(self.nuevos or self.cerrados)


class SincronizarParametrosFiscales:
    """HS-T4 — bring ARCA's catalogue in, preserving what it used to say.

    **A failure keeps the previous catalogue** (RN-04). Not «clear and retry»: emptying the
    table would leave the issuing code with nothing to validate against, during exactly the
    window in which somebody is going to try to invoice. Doing nothing is the correct
    behaviour and the error goes to the log.
    """

    def __init__(
        self,
        *,
        parametros: PortRepositorioParametros,
        catalogos: PortCatalogosFiscales,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._parametros = parametros
        self._catalogos = catalogos
        self._publicador = publicador

    async def ejecutar(
        self, *, empresa_id: EmpresaId, ahora: datetime
    ) -> ResultadoDeSincronizacion:
        hoy = ahora.date()

        try:
            entradas = await self._catalogos.obtener(empresa_id=empresa_id)
        except ErrorDeDominio as exc:
            await self._auditar(
                empresa_id, ahora=ahora, resultado=Resultado.ERROR, detalle=str(exc)
            )
            return ResultadoDeSincronizacion(nuevos=0, cerrados=0, fallo=True)

        if not entradas:
            # An empty answer is not a reason to close everything. ARCA returning nothing
            # is indistinguishable from ARCA having a bad day, and the difference matters
            # enough to do nothing in both cases.
            await self._auditar(
                empresa_id,
                ahora=ahora,
                resultado=Resultado.ERROR,
                detalle="ARCA no devolvio catalogos",
            )
            return ResultadoDeSincronizacion(nuevos=0, cerrados=0, fallo=True)

        vigentes = {p.clave: p for p in await self._parametros.vigentes()}
        nuevos = 0
        cerrados = 0

        for entrada in entradas:
            actual = vigentes.get((entrada.tipo, entrada.codigo))
            if actual is not None and actual.valor == entrada.valor:
                # Unchanged. Writing a new row anyway would make the history a log of
                # syncs instead of a history of the catalogue.
                continue

            if actual is not None:
                # The old version ends the day before the new one starts, so the two never
                # overlap by a day -- which is the aggregate's invariant, kept here rather
                # than discovered by a query that returns two rows.
                await self._parametros.cerrar(actual.cerrar(hasta=hoy - timedelta(days=1)))
                cerrados += 1

            await self._parametros.agregar(
                ParametroFiscal(
                    id=uuid4(),
                    tipo=entrada.tipo,
                    codigo=entrada.codigo,
                    valor=entrada.valor,
                    fecha_desde=hoy,
                )
            )
            nuevos += 1

        await self._auditar(
            empresa_id,
            ahora=ahora,
            resultado=Resultado.COMPLETADO,
            detalle=f"nuevos={nuevos} cerrados={cerrados}",
        )
        return ResultadoDeSincronizacion(nuevos=nuevos, cerrados=cerrados)

    async def _auditar(
        self, empresa_id: EmpresaId, *, ahora: datetime, resultado: Resultado, detalle: str
    ) -> None:
        del detalle  # Kept out of the audit row: `accion` and `resultado` are the record.
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                # The scheduler ran it. HS-T5 models that as a null initiator.
                usuario_id=None,
                modulo=Modulo.REFERENCE_DATA,
                accion="sincronizar_parametros_fiscales",
                entidad_afectada="ParametroFiscal",
                resultado=resultado,
            )
        )


class ParametroVigenteA:
    """RN-03 — the catalogue entry in force **on a given date**.

    The date is required and has no default, which is the whole design of this class. A
    default of `date.today()` reads well and is wrong for every reprint, every credit note
    issued after the fact, and the VAT book of epic 9 — and it is wrong silently, returning
    a plausible number from the wrong period.
    """

    def __init__(self, parametros: PortRepositorioParametros) -> None:
        self._parametros = parametros

    async def ejecutar(
        self, *, tipo: TipoCatalogoFiscal, codigo: str, fecha: date
    ) -> ParametroFiscal:
        parametro = await self._parametros.buscar_vigente_a(tipo=tipo, codigo=codigo, fecha=fecha)
        if parametro is None:
            # Raising rather than returning None: every caller of this is about to put the
            # value on a fiscal document, and a `None` that reaches that far becomes an
            # invoice with a missing field instead of an error somebody can act on.
            raise InvarianteViolada(
                f"No hay un parametro fiscal {tipo.value}/{codigo} vigente al {fecha.isoformat()}"
            )
        return parametro


__all__ = [
    "EntradaDeCatalogo",
    "ParametroVigenteA",
    "ResultadoDeSincronizacion",
    "SincronizarParametrosFiscales",
]
