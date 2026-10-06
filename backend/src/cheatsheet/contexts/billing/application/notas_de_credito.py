"""HU-E5-04 — reversing an authorised document with a credit note.

**A credit note is a `Comprobante`.** Everything the previous unit built applies unchanged:
it draws a number under the same lock, goes out through the same asynchronous issuance, and
comes back through the same reconciliation (D17). What is added here is the three rules that
only exist because there is an original: the link (RN-01), the type (RN-02) and the ceiling
(RN-03).

**Decision D19 — what is reversed is derived, not stored.** `EstadoDeAnulacion` sums the
authorised credit notes against an original. The `ANULADO` state on the original is a cache
of the "fully reversed" case, kept so `PAN-FAC-01` can filter without summing anything, and
it is allowed to be lost: recomputing it is one query. The opposite -- keeping only the
column -- cannot be recomputed at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.billing.application.emision import EmitirComprobante
from cheatsheet.contexts.billing.application.errors import (
    ComprobanteInexistente,
    ComprobanteNoAnulable,
    MontoDeNotaExcedido,
)
from cheatsheet.contexts.billing.application.ports import PortRepositorioComprobante
from cheatsheet.contexts.billing.domain.comprobante import (
    Comprobante,
    EstadoComprobante,
    ItemDeComprobante,
    monto_anulado,
    nota_de_credito_para,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import InvarianteViolada
from cheatsheet.shared.roles import RolUsuario

#: HU-E5-04, word for word.
MENSAJE_MONTO_EXCEDIDO = (
    "El monto de la nota de crédito no puede superar el del comprobante original."
)
MENSAJE_SIN_ORIGEN = "Debe seleccionar el comprobante que desea anular."


@dataclass(frozen=True, slots=True)
class Anulacion:
    """What has been reversed of one document, and what is left (RN-05).

    Derived on every read (D19). `total_anulado` counts only authorised notes: one ARCA
    rejected reversed nothing, and one still in flight has not reversed anything *yet* --
    counting it would let somebody reverse the same amount twice while the first attempt is
    unresolved.
    """

    total_original: Decimal
    total_anulado: Decimal

    @property
    def disponible(self) -> Decimal:
        """The ceiling RN-03 sets for the next credit note."""
        return self.total_original - self.total_anulado

    @property
    def es_total(self) -> bool:
        return self.total_anulado >= self.total_original

    @property
    def es_parcial(self) -> bool:
        """Not a state. The original stays `AUTORIZADO`: it is still a live document for
        what remains of it."""
        return Decimal("0.00") < self.total_anulado < self.total_original


class EstadoDeAnulacion:
    """How much of a document has been reversed (RN-05). **The source of truth.**"""

    def __init__(self, comprobantes: PortRepositorioComprobante) -> None:
        self._comprobantes = comprobantes

    async def ejecutar(self, comprobante_id: UUID) -> Anulacion:
        original = await self._comprobantes.buscar_por_id(comprobante_id)
        if original is None:
            raise ComprobanteInexistente("El comprobante no existe")
        notas = await self._comprobantes.notas_de(comprobante_id)
        return Anulacion(total_original=original.total, total_anulado=monto_anulado(notas))


class EmitirNotaDeCredito:
    """Reverse an authorised document, in full or in part.

    Delegates to `EmitirComprobante` for everything a document needs — validation, the
    number under the lock, persistence, the queue — and adds only what an *original* makes
    necessary. That delegation is the point: a second issuance path would be a second place
    for decisions D14, D17 and D18 to be got wrong, and a credit note also carries a CAE.
    """

    def __init__(
        self,
        *,
        comprobantes: PortRepositorioComprobante,
        emitir: EmitirComprobante,
    ) -> None:
        self._comprobantes = comprobantes
        self._emitir = emitir

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        origen_id: UUID,
        items: list[ItemDeComprobante],
        ahora: datetime,
    ) -> Comprobante:
        original = await self._comprobantes.buscar_por_id(origen_id)
        if original is None:
            # RN-01. Under RLS "not yours" and "does not exist" are the same answer, and
            # the story's sentence covers both without confirming either.
            raise ComprobanteInexistente(MENSAJE_SIN_ORIGEN)

        try:
            nota = nota_de_credito_para(original, nota_id=uuid4(), items=items, ahora=ahora)
        except InvarianteViolada as exc:
            # Narrowed so the router can answer 409 for "that document cannot be reversed"
            # while still carrying the reason.
            raise ComprobanteNoAnulable(str(exc)) from exc

        # RN-03, against what is **left**, not against the original's total: two credit
        # notes of half the amount each are legitimate, and a check against the total would
        # allow a third.
        notas = await self._comprobantes.notas_de(origen_id)
        disponible = original.total - monto_anulado(notas)
        if nota.total > disponible:
            raise MontoDeNotaExcedido(MENSAJE_MONTO_EXCEDIDO)

        return await self._emitir.ejecutar(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            rol=rol,
            comprobante=nota,
            ahora=ahora,
        )


async def reflejar_anulacion(comprobantes: PortRepositorioComprobante, nota: Comprobante) -> None:
    """RN-05 — the original records that it was fully reversed, once ARCA authorises.

    Called from `_aplicar_respuesta` when an authorised document turns out to be a credit
    note, so the cache is written on exactly the transition that can change the answer.

    **Only on a full reversal.** A partial one leaves the original `AUTORIZADO`, because
    that is what it is: a live document for what remains of it. And the write is a cache
    (D19) -- if it were lost, `EstadoDeAnulacion` would still give the right answer.
    """
    if nota.comprobante_origen_id is None or nota.estado is not EstadoComprobante.AUTORIZADO:
        return

    original = await comprobantes.buscar_por_id(nota.comprobante_origen_id)
    if original is None or original.estado is not EstadoComprobante.AUTORIZADO:
        # Already `ANULADO`, or gone. Either way there is nothing to record: the transition
        # table refuses `ANULADO → ANULADO`, which is what makes this idempotent.
        return

    notas = await comprobantes.notas_de(original.id)
    if monto_anulado(notas) >= original.total:
        original.anular()
        await comprobantes.guardar(original)


__all__ = [
    "MENSAJE_MONTO_EXCEDIDO",
    "MENSAJE_SIN_ORIGEN",
    "Anulacion",
    "EmitirNotaDeCredito",
    "EstadoDeAnulacion",
    "reflejar_anulacion",
]
