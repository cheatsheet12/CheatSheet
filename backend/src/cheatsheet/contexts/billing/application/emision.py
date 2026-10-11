"""HU-E5-03 — issuing a document and getting its CAE.

The flow is split in three use cases on purpose, and the split *is* the safety property:

- `EmitirComprobante` runs in the request. It validates, draws the number under the lock
  of D14, **persists the document in `ENVIADO_A_ARCA`**, and hands it to a worker. It never
  talks to WSFEv1.
- `AutorizarComprobante` runs in the worker. It is the only thing that sends the envelope.
- `ReconciliarComprobante` runs when the second one did not come back — from its own retry
  or from the Beat sweep — and is decision **D17**.

**Why the document is persisted before the envelope leaves.** If we sent first and recorded
afterwards, a crash in between would leave a CAE at the AFIP that this system has no row
for: a legal document nobody can find, against a number we would happily hand out again.
Recording first gives the opposite failure, which is the recoverable one — a row that says
«we do not know», and `FECompConsultar` to find out.

**Why a retry is never a plain retry.** `FECAESolicitar` is not idempotent. Sending the
same document twice after a timeout is the exact way to issue two legal documents for one
sale, and the second one also carries a CAE. So an unknown outcome goes through
`ReconciliarComprobante`, which asks before it acts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from cheatsheet.contexts.billing.application.errors import (
    ArcaNoDisponible,
    ComprobanteInexistente,
    PuntoDeVentaInexistente,
    TipoDeComprobanteInvalido,
)
from cheatsheet.contexts.billing.application.ports import (
    PortAutorizacionDeArca,
    PortColaDeEmision,
    PortRepositorioComprobante,
    PortRepositorioPuntoDeVenta,
    PortValidacionDeReceptor,
    RespuestaDeArca,
)
from cheatsheet.contexts.billing.domain.comprobante import (
    MENSAJE_CUIT_INVALIDO,
    MENSAJE_CUIT_NO_ENCONTRADO,
    MENSAJE_TIPO_INVALIDO,
    AlicuotaIVA,
    Comprobante,
    ItemDeComprobante,
    Receptor,
    tipos_permitidos,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.fiscal import CUIT, CondicionIVA
from cheatsheet.shared.roles import RolUsuario

#: How long a document may sit in `ENVIADO_A_ARCA` before the sweep considers it stuck.
#: Long enough that a slow but healthy call is not reconciled out from under the task that
#: is still awaiting it; short enough that nobody waits an afternoon to learn they have a
#: CAE. WSFEv1's own timeout is a fraction of this.
VENTANA_DE_VUELO = timedelta(minutes=5)

MOTIVO_SIN_PERMISO = "Solo un Administrador u Operador puede emitir comprobantes"
MENSAJE_RECEPTOR_INACTIVO = "El CUIT figura en el padrón de ARCA pero no está activo."
MENSAJE_SIN_CONDICION = (
    "ARCA no informa la condición de IVA de ese CUIT, así que no podemos determinar el tipo "
    "de comprobante."
)


def _exigir_emisor(rol: RolUsuario) -> None:
    """HU-E5-03's actors: Administrador and Operador. Solo Lectura reads (RN-04)."""
    if rol not in (RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR):
        raise EntradaInvalida(MOTIVO_SIN_PERMISO)


class ValidarReceptor:
    """HU-E5-03 RN-02 — the CUIT, checked before anything else is offered.

    Two checks in a deliberate order: **the check digit first, locally**, then the padrón.
    The story is explicit that an invalid CUIT «no consulta a ARCA», and that is not only
    politeness towards ARCA's rate limits — it is the difference between an answer in a
    millisecond and an answer in a second, on a field somebody is still typing.
    """

    def __init__(self, receptores: PortValidacionDeReceptor) -> None:
        self._receptores = receptores

    async def ejecutar(self, *, empresa_id: EmpresaId, cuit: str) -> Receptor:
        try:
            validado = CUIT(cuit)
        except EntradaInvalida as exc:
            raise EntradaInvalida(MENSAJE_CUIT_INVALIDO) from exc

        datos = await self._receptores.validar(empresa_id=empresa_id, cuit=str(validado))
        if datos is None:
            raise EntradaInvalida(MENSAJE_CUIT_NO_ENCONTRADO)
        if not datos.activo:
            # Not the same as "not found", and the two lead to opposite conversations with
            # the customer. `DatosDePadron` keeps them apart; so does this.
            raise EntradaInvalida(MENSAJE_RECEPTOR_INACTIVO)
        if datos.condicion_iva is None:
            # Inventing one would decide which type of document may be issued, which is
            # exactly the decision that must not be guessed.
            raise EntradaInvalida(MENSAJE_SIN_CONDICION)

        return Receptor(
            nombre=datos.razon_social or str(validado),
            cuit=str(validado),
            condicion_iva=datos.condicion_iva,
        )


class TiposDisponibles:
    """RN-01 — which types the screen may offer for this pair of conditions (D16).

    Answering this *before* the user picks is what turns the story's error message into a
    message they should never see: PAN-FAC-03 offers only what is legal, and the check on
    the way in exists for the request that did not come from that screen.
    """

    @staticmethod
    def ejecutar(*, emisor: CondicionIVA, receptor: CondicionIVA) -> tuple[TipoComprobante, ...]:
        permitidos = tipos_permitidos(emisor=emisor, receptor=receptor)
        # Sorted so the screen's order is stable across requests; a set is not.
        return tuple(sorted(permitidos, key=lambda tipo: tipo.codigo_arca))


class EmitirComprobante:
    """Validate, draw the number, persist, enqueue. **Never talks to ARCA.**

    The transaction boundary is the caller's unit of work, and everything here belongs
    inside it: the number is drawn with the point of sale's row locked (D14), and the
    document that carries it is written before the lock is released. A number drawn in one
    transaction and a document written in another is a hole in the numbering waiting for a
    crash.
    """

    def __init__(
        self,
        *,
        comprobantes: PortRepositorioComprobante,
        puntos: PortRepositorioPuntoDeVenta,
        arca: PortAutorizacionDeArca,
        cola: PortColaDeEmision,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._comprobantes = comprobantes
        self._puntos = puntos
        self._arca = arca
        self._cola = cola
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        comprobante: Comprobante,
        ahora: datetime,
    ) -> Comprobante:
        _exigir_emisor(rol)

        try:
            comprobante.validar()
        except EntradaInvalida as exc:
            if str(exc) == MENSAJE_TIPO_INVALIDO:
                # Narrower than `EntradaInvalida` so the router can answer RN-01 specifically
                # while still forwarding the story's sentence.
                raise TipoDeComprobanteInvalido(MENSAJE_TIPO_INVALIDO) from exc
            raise

        punto = await self._puntos.tomar_para_emitir(comprobante.punto_de_venta_id)
        if punto is None:
            raise PuntoDeVentaInexistente("El punto de venta no existe")

        # **Decision D18, inside the lock.** WSFEv1 demands strictly correlative numbering
        # and keeps rejecting until our counter and its own agree, so ARCA is asked what it
        # last authorised before the number is drawn. It is a read, not an issue -- this
        # use case still never sends `FECAESolicitar` -- and if ARCA cannot be reached the
        # emission fails here, which is right: without ARCA there is no CAE either.
        ultimo = await self._arca.ultimo_autorizado(
            empresa_id=empresa_id, punto=punto, tipo=comprobante.tipo
        )
        punto.sincronizar_con_arca(comprobante.tipo, ultimo)

        numero = punto.siguiente_numero(comprobante.tipo)
        comprobante.enviar_a_arca(numero, ahora)

        await self._puntos.guardar(punto)
        await self._comprobantes.agregar(comprobante)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.BILLING,
                accion="emitir_comprobante",
                entidad_afectada=f"Comprobante:{comprobante.id}",
                # The *request* completed: the document exists and is on its way. Whether
                # ARCA authorises it is a second event, written by the worker. HS-T5's
                # `Resultado` has two values on purpose -- it records whether the action
                # this row names succeeded, not the fate of everything it set in motion.
                resultado=Resultado.COMPLETADO,
            )
        )
        # Enqueued last, after everything that could still fail. A task that starts before
        # its row is committed reads a document that is not there yet.
        await self._cola.encolar(empresa_id=empresa_id, comprobante_id=comprobante.id)
        return comprobante


class AutorizarComprobante:
    """The worker side: send the envelope and resolve the state (RN-04).

    Three outcomes, and keeping them apart is the point:

    - **ARCA authorises** → CAE recorded, done.
    - **ARCA rejects** → an *answer*. The state goes to `RECHAZADO` with ARCA's own words,
      and the number goes back to the point of sale: ARCA has nothing recorded under it.
    - **No answer** → `ArcaNoDisponible` propagates and the document stays in
      `ENVIADO_A_ARCA`. The number is **not** returned. Reconciliation decides later.

    That third branch is the one worth reading twice: doing nothing is the correct action.
    """

    def __init__(
        self,
        *,
        comprobantes: PortRepositorioComprobante,
        puntos: PortRepositorioPuntoDeVenta,
        arca: PortAutorizacionDeArca,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._comprobantes = comprobantes
        self._puntos = puntos
        self._arca = arca
        self._publicador = publicador

    async def ejecutar(
        self, *, empresa_id: EmpresaId, comprobante_id: UUID, ahora: datetime
    ) -> Comprobante:
        comprobante = await self._comprobantes.buscar_por_id(comprobante_id)
        if comprobante is None:
            raise ComprobanteInexistente("El comprobante no existe")
        if not comprobante.esta_en_vuelo:
            # Already resolved -- by an earlier attempt or by the sweep. Celery redelivers,
            # and a task that re-sent an authorised document would issue a second one.
            return comprobante

        respuesta = await self._arca.solicitar(empresa_id=empresa_id, comprobante=comprobante)
        return await _aplicar_respuesta(
            comprobantes=self._comprobantes,
            puntos=self._puntos,
            publicador=self._publicador,
            empresa_id=empresa_id,
            comprobante=comprobante,
            respuesta=respuesta,
            ahora=ahora,
        )


class ReconciliarComprobante:
    """**Decision D17.** Ask ARCA what happened; never assume, never resend blindly.

    A document in `ENVIADO_A_ARCA` past the flight window is one whose outcome we do not
    know. There are exactly two truths and one question that separates them:

    - ARCA has a record under `(tipo, punto, numero)` → **it was authorised**. Record the
      CAE it returns. One sale, one document.
    - ARCA has no record → it never got through. The document goes back to `RECHAZADO`
      with a reason saying so, which is the state the user can retry from.

    **The number is never reused for a different document and never quietly dropped.** A
    gap in the numbering is a question from an inspector; two documents sharing a number is
    a different order of problem.
    """

    def __init__(
        self,
        *,
        comprobantes: PortRepositorioComprobante,
        puntos: PortRepositorioPuntoDeVenta,
        arca: PortAutorizacionDeArca,
        publicador: PublicadorDeEventos,
        ventana: timedelta = VENTANA_DE_VUELO,
    ) -> None:
        self._comprobantes = comprobantes
        self._puntos = puntos
        self._arca = arca
        self._publicador = publicador
        self._ventana = ventana

    async def ejecutar(self, *, empresa_id: EmpresaId, ahora: datetime) -> list[Comprobante]:
        """Reconcile every document stuck in flight. Returns the ones it resolved."""
        pendientes = await self._comprobantes.en_vuelo(anteriores_a=ahora - self._ventana)
        resueltos: list[Comprobante] = []
        for comprobante in pendientes:
            resuelto = await self._uno(empresa_id=empresa_id, comprobante=comprobante, ahora=ahora)
            if resuelto is not None:
                resueltos.append(resuelto)
        return resueltos

    async def _uno(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante, ahora: datetime
    ) -> Comprobante | None:
        try:
            registrado = await self._arca.consultar(empresa_id=empresa_id, comprobante=comprobante)
        except ArcaNoDisponible:
            # Still cannot ask. The document stays exactly where it is, which is the whole
            # point: an unknown outcome that we leave alone stays recoverable.
            return None

        if registrado is None:
            # ARCA has no record: it never got through. Safe to release the number and let
            # the user try again -- and this is the *only* branch where that is safe.
            return await _aplicar_respuesta(
                comprobantes=self._comprobantes,
                puntos=self._puntos,
                publicador=self._publicador,
                empresa_id=empresa_id,
                comprobante=comprobante,
                respuesta=_RECHAZO_POR_RECONCILIACION,
                ahora=ahora,
            )

        return await _aplicar_respuesta(
            comprobantes=self._comprobantes,
            puntos=self._puntos,
            publicador=self._publicador,
            empresa_id=empresa_id,
            comprobante=comprobante,
            respuesta=registrado,
            ahora=ahora,
        )


#: The one rejection this system writes rather than quotes. It is a `RespuestaDeArca` like
#: any other, because from the document's point of view nothing distinguishes it: ARCA has
#: no record, so the document was never authorised. `_aplicar_respuesta` must not learn to
#: tell the two apart.
_RECHAZO_POR_RECONCILIACION = RespuestaDeArca(
    autorizado=False,
    codigo="SIN_REGISTRO",
    descripcion=(
        "ARCA no tiene registro de este comprobante, así que no llegó a autorizarse. "
        "Podés emitirlo de nuevo."
    ),
)


async def _aplicar_respuesta(
    *,
    comprobantes: PortRepositorioComprobante,
    puntos: PortRepositorioPuntoDeVenta,
    publicador: PublicadorDeEventos,
    empresa_id: EmpresaId,
    comprobante: Comprobante,
    respuesta: RespuestaDeArca,
    ahora: datetime,
) -> Comprobante:
    """Turn ARCA's answer into a state change, once, for both callers.

    Shared by `AutorizarComprobante` and `ReconciliarComprobante` on purpose: the two reach
    the answer differently and must act on it identically. Two copies of this would drift,
    and the direction they would drift in is the dangerous one.
    """
    if respuesta.autorizado:
        if respuesta.cae is None:  # pragma: no cover - the adapter never reports this shape
            raise ArcaNoDisponible("ARCA autorizo el comprobante pero no devolvio el CAE")
        comprobante.autorizar(respuesta.cae)
    else:
        codigo = respuesta.codigo or "SIN_CODIGO"
        descripcion = respuesta.descripcion or "ARCA rechazo el comprobante"
        numero = comprobante.rechazar(f"Error {codigo}: {descripcion}")
        # A rejection is an answer, so ARCA recorded nothing under that number and it can
        # go back. When it cannot -- a later document already drew one -- the gap stays and
        # `sincronizar_con_arca` closes it on the next issue (D18). Failing here instead
        # would leave the document unresolved over a bookkeeping detail.
        punto = await puntos.tomar_para_emitir(comprobante.punto_de_venta_id)
        if punto is not None and numero is not None:
            punto.devolver_numero(comprobante.tipo, numero)
            await puntos.guardar(punto)

    await comprobantes.guardar(comprobante)
    if comprobante.comprobante_origen_id is not None:
        # HU-E5-04 RN-05. Imported here rather than at module scope: `notas_de_credito`
        # imports `EmitirComprobante` from this module, and naming it at the top would
        # close the cycle. The direction of the dependency is right -- credit notes are
        # built on issuance, not the other way round -- and this is the one call back.
        from cheatsheet.contexts.billing.application.notas_de_credito import (
            reflejar_anulacion,
        )

        await reflejar_anulacion(comprobantes, comprobante)
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            ocurrido_en=ahora,
            # No user: this runs in a worker, on nobody's behalf. HS-T5 allows a null
            # actor precisely for the system's own actions.
            usuario_id=None,
            modulo=Modulo.BILLING,
            accion="autorizar_comprobante",
            entidad_afectada=f"Comprobante:{comprobante.id}",
            resultado=Resultado.COMPLETADO if respuesta.autorizado else Resultado.ERROR,
            # HU-E12-02 RN-02: «para operaciones fiscales, el detalle incluye los datos del
            # comprobante y el resultado de ARCA». Es la única operación del sistema que lo
            # llena, y es la que la historia nombra. Sin datos personales del receptor: lo que
            # se guarda es lo fiscal, que es lo que alguien va a ir a buscar cuando pregunte
            # por qué un comprobante quedó como quedó.
            detalle=_detalle_de_arca(comprobante, respuesta),
        )
    )
    return comprobante


def _detalle_de_arca(comprobante: Comprobante, respuesta: RespuestaDeArca) -> dict[str, str]:
    """Lo que la autorización deja escrito en la bitácora (HU-E12-02 RN-02).

    Todo como texto, incluido el total: es la misma regla que en el resto del sistema, y acá
    además el valor se guarda en un `jsonb` que nadie va a poder corregir después.
    """
    detalle = {
        "tipo": comprobante.tipo.value,
        "numero": str(comprobante.numero or ""),
        "total": str(comprobante.total),
        "estado": comprobante.estado.value,
    }
    if respuesta.cae is not None:
        detalle["cae"] = respuesta.cae.codigo
        detalle["cae_vence"] = f"{respuesta.cae.vence_el:%Y-%m-%d}"
    if respuesta.codigo is not None:
        # El código y la descripción tal como los contestó ARCA. Parafrasearlos los volvería
        # imposibles de buscar, que es justo lo que alguien hace con un rechazo en la mano.
        detalle["codigo_arca"] = respuesta.codigo
        detalle["descripcion_arca"] = respuesta.descripcion or ""
    return detalle


def item(
    *,
    descripcion: str,
    cantidad: str,
    precio_unitario: str,
    alicuota_iva: AlicuotaIVA,
) -> ItemDeComprobante:
    """Build one line from text.

    **The amounts arrive as strings and stay strings until `Decimal`.** A `float` anywhere
    on this path is the bug `CLAUDE.md` §3.5 forbids, and it is invisible: `0.1 + 0.2` is
    wrong in the fourth decimal, which is exactly where a centavo lives.
    """
    try:
        return ItemDeComprobante(
            id=uuid4(),
            descripcion=descripcion,
            cantidad=Decimal(cantidad),
            precio_unitario=Decimal(precio_unitario),
            alicuota_iva=alicuota_iva,
        )
    except InvalidOperation as exc:
        raise EntradaInvalida("La cantidad y el precio tienen que ser numeros") from exc


__all__ = [
    "MENSAJE_RECEPTOR_INACTIVO",
    "MENSAJE_SIN_CONDICION",
    "MOTIVO_SIN_PERMISO",
    "VENTANA_DE_VUELO",
    "AutorizarComprobante",
    "EmitirComprobante",
    "ReconciliarComprobante",
    "TiposDisponibles",
    "ValidarReceptor",
    "item",
]
