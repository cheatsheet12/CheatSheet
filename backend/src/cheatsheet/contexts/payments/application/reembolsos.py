"""Los reembolsos por la API de MercadoPago (HU-E6-05): dos transacciones y una clave.

**Sólo el Administrador** (RN-05). El guarda vive acá y no sólo en el router, por lo que enseñó
PRU-09.

**Un reembolso por API se pide en dos transacciones** (decisión de la unidad, P2):

1. `SolicitarReembolso` (T1) bloquea el cobro, valida, y guarda la marca de «en proceso», el
   monto y **una clave de idempotencia**. El borde la commitea antes de seguir.
2. `EnviarReembolso` (T2) llama a MercadoPago **con esa clave** y registra lo que contestó.

Si T1 y T2 fueran una sola transacción, una excepción del borde la descartaría entera: el
rechazo no quedaría escrito y, peor, si MercadoPago no contestara la marca se perdería aunque la
plata hubiera salido. Por eso ningún caso de uso de este módulo levanta por un rechazo de
MercadoPago: **lo devuelve** (`ResultadoDeReembolso.rechazo`) y el borde lo re-levanta después
del commit, con el patrón de `unidad_de_trabajo`.

El registro manual y la corrección, que no hablan con MercadoPago, viven en
`reembolsos_manuales.py`; lo que comparten, en `reembolsos_comunes.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.application.errors import (
    CobroNoReembolsable,
    PasarelaNoDisponible,
    ReembolsoEnProceso,
)
from cheatsheet.contexts.payments.application.ports import (
    EstadoDeReembolso,
    PortPasarelaDePago,
    PortRepositorioCobro,
    PortRepositorioReembolso,
    PortSaldoDeComprobante,
    RespuestaDeReembolso,
)
from cheatsheet.contexts.payments.application.reembolsos_comunes import (
    aplicar,
    cargar_cobro,
    detalle_de_fila,
    exigir_administrador,
    publicar,
)
from cheatsheet.contexts.payments.domain.cobro import MENSAJE_REEMBOLSO_EN_PROCESO, Cobro
from cheatsheet.shared.auditoria import Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

#: Lo que de un mensaje de MercadoPago cabe en la bitácora: el detalle se guarda para siempre.
LARGO_MAXIMO_DEL_MOTIVO_EN_BITACORA = 300
MOTIVO_NO_INFORMADO = "MercadoPago no informo el motivo"


@dataclass(frozen=True, slots=True)
class ResultadoDeReembolso:
    """Lo que dejó T2. `rechazo` trae el motivo de MercadoPago cuando dijo que no.

    **No es una excepción a propósito**: levantarla dentro de la unidad de trabajo descartaría el
    rechazo y su evento. El borde la levanta después del commit.
    """

    cobro: Cobro
    rechazo: str | None = None


class SolicitarReembolso:
    """T1 — deja escrito que se pidió, cuánto y con qué clave. **No habla con MercadoPago.**"""

    def __init__(self, *, cobros: PortRepositorioCobro, publicador: PublicadorDeEventos) -> None:
        self._cobros = cobros
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cobro_id: UUID,
        monto: Decimal,
        ahora: datetime,
    ) -> Cobro:
        del empresa_id
        exigir_administrador(rol)
        cobro = await cargar_cobro(self._cobros, cobro_id)
        if cobro.reembolso_en_proceso:
            raise ReembolsoEnProceso(MENSAJE_REEMBOLSO_EN_PROCESO)
        try:
            pedido = cobro.solicitar_reembolso(monto=monto, clave=uuid4(), ahora=ahora)
        except InvarianteViolada as exc:
            raise CobroNoReembolsable(str(exc)) from exc

        await self._cobros.guardar(cobro)
        await publicar(
            self._publicador,
            cobro=cobro,
            usuario_id=usuario_id,
            ahora=ahora,
            accion="solicitar_reembolso",
            resultado=Resultado.COMPLETADO,
            detalle={"monto": str(pedido), "origen": "API_MERCADOPAGO"},
        )
        return cobro


class EnviarReembolso:
    """T2 — pide el reembolso **con la clave guardada** y registra lo que MercadoPago contestó.

    Tres desenlaces, y ninguno levanta: aceptado (fila, acumulado, estado, saldo), rechazado (se
    limpia la marca y se devuelve el motivo) y en proceso o sin respuesta (la solicitud sigue en
    vuelo, con el id de MercadoPago si lo hubo). Si ya no hay nada en vuelo no hace nada: es lo que
    vuelve idempotente a una segunda llamada.
    """

    #: `ActualizarReembolso` lo enciende: con el id de MercadoPago se **consulta** en vez de
    #: reenviar el `POST`.
    _consulta_si_hay_id = False

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        reembolsos: PortRepositorioReembolso,
        pasarela: PortPasarelaDePago,
        saldos: PortSaldoDeComprobante,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._cobros = cobros
        self._reembolsos = reembolsos
        self._pasarela = pasarela
        self._saldos = saldos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        cobro_id: UUID,
        ahora: datetime,
    ) -> ResultadoDeReembolso:
        exigir_administrador(rol)
        cobro = await cargar_cobro(self._cobros, cobro_id)
        if not cobro.reembolso_en_proceso:
            return ResultadoDeReembolso(cobro)
        try:
            respuesta = await self._preguntar(empresa_id, cobro)
        except PasarelaNoDisponible as exc:
            return await self._dejar_en_vuelo(
                cobro, None, usuario_id, ahora, Resultado.ERROR, str(exc)
            )
        if respuesta.estado is EstadoDeReembolso.ACEPTADO:
            return await self._confirmar(cobro, respuesta, usuario_id, ahora)
        if respuesta.estado is EstadoDeReembolso.RECHAZADO:
            return await self._rechazar(cobro, respuesta, usuario_id, ahora)
        return await self._dejar_en_vuelo(cobro, respuesta, usuario_id, ahora, Resultado.COMPLETADO)

    async def _preguntar(self, empresa_id: EmpresaId, cobro: Cobro) -> RespuestaDeReembolso:
        monto, clave = cobro.reembolso_pedido
        if cobro.mp_payment_id is None:
            raise CobroNoReembolsable("El cobro no tiene un pago de MercadoPago asociado")
        if self._consulta_si_hay_id and cobro.reembolso_mp_refund_id is not None:
            return await self._pasarela.consultar_reembolso(
                empresa_id=empresa_id,
                payment_id=cobro.mp_payment_id,
                refund_id=cobro.reembolso_mp_refund_id,
            )
        return await self._pasarela.reembolsar(
            empresa_id=empresa_id, payment_id=cobro.mp_payment_id, monto=monto, clave=clave
        )

    async def _confirmar(
        self, cobro: Cobro, respuesta: RespuestaDeReembolso, usuario_id: UsuarioId, ahora: datetime
    ) -> ResultadoDeReembolso:
        monto, _ = cobro.reembolso_pedido
        try:
            fila = cobro.confirmar_reembolso(
                reembolso_id=uuid4(),
                monto=monto if respuesta.monto is None else respuesta.monto,
                mp_refund_id=respuesta.mp_refund_id,
                fecha=respuesta.fecha,
                ahora=ahora,
            )
        except EntradaInvalida as exc:
            # MercadoPago dice haber devuelto más de lo que el cobro admite: no se registra una
            # plata que no cuadra, queda en vuelo y alguien la mira.
            return await self._dejar_en_vuelo(
                cobro, respuesta, usuario_id, ahora, Resultado.ERROR, str(exc)
            )
        await aplicar(
            cobros=self._cobros,
            reembolsos=self._reembolsos,
            saldos=self._saldos,
            cobro=cobro,
            fila=fila,
        )
        await publicar(
            self._publicador,
            cobro=cobro,
            usuario_id=usuario_id,
            ahora=ahora,
            accion="confirmar_reembolso",
            resultado=Resultado.COMPLETADO,
            detalle=detalle_de_fila(fila),
        )
        return ResultadoDeReembolso(cobro)

    async def _rechazar(
        self, cobro: Cobro, respuesta: RespuestaDeReembolso, usuario_id: UsuarioId, ahora: datetime
    ) -> ResultadoDeReembolso:
        """RN-03: el estado y el acumulado no cambian, y el administrador se entera (`ERROR`)."""
        monto, _ = cobro.reembolso_pedido
        motivo = respuesta.motivo or MOTIVO_NO_INFORMADO
        cobro.rechazar_reembolso(ahora)
        await self._cobros.guardar(cobro)
        await publicar(
            self._publicador,
            cobro=cobro,
            usuario_id=usuario_id,
            ahora=ahora,
            accion="rechazar_reembolso",
            resultado=Resultado.ERROR,
            detalle={
                "monto": str(monto),
                "motivo_mercadopago": motivo[:LARGO_MAXIMO_DEL_MOTIVO_EN_BITACORA],
            },
        )
        return ResultadoDeReembolso(cobro, rechazo=motivo)

    async def _dejar_en_vuelo(
        self,
        cobro: Cobro,
        respuesta: RespuestaDeReembolso | None,
        usuario_id: UsuarioId,
        ahora: datetime,
        resultado: Resultado,
        causa: str | None = None,
    ) -> ResultadoDeReembolso:
        """Sigue en proceso, con el id de MercadoPago si lo hubo. `ERROR` solo cuando algo no
        cuadra o no hubo respuesta: es lo que hace que alguien se entere."""
        monto, _ = cobro.reembolso_pedido
        if respuesta is not None and respuesta.mp_refund_id is not None:
            cobro.registrar_id_de_reembolso(respuesta.mp_refund_id, ahora)
        await self._cobros.guardar(cobro)
        detalle = {"monto": str(monto)}
        if causa is not None:
            detalle["causa"] = causa[:LARGO_MAXIMO_DEL_MOTIVO_EN_BITACORA]
        await publicar(
            self._publicador,
            cobro=cobro,
            usuario_id=usuario_id,
            ahora=ahora,
            accion="reembolso_sin_confirmar",
            resultado=resultado,
            detalle=detalle,
        )
        return ResultadoDeReembolso(cobro)


class ActualizarReembolso(EnviarReembolso):
    """«Actualizar estado»: destraba un reembolso que quedó en proceso (solo Administrador).

    Con el id de MercadoPago **consulta**; sin id **reenvía el `POST` con la misma clave**, así
    que MercadoPago deduplica en vez de devolver dos veces. Es el mismo caso de uso que el barrido
    automático de la unidad `reembolsos-en-vuelo` va a llamar.
    """

    _consulta_si_hay_id = True


__all__ = [
    "ActualizarReembolso",
    "EnviarReembolso",
    "ResultadoDeReembolso",
    "SolicitarReembolso",
]
