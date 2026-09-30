"""Los reembolsos de un `Cobro` (HU-E6-05, ADR-0010 puntos 4 y 5).

Un mixin y no una clase aparte porque el reembolso **es** el cobro cambiando de estado: lee y
escribe su monto, su estado y su solicitud en vuelo. Vive en su archivo para que `cobro.py` quepa
en las 400 líneas de `CLAUDE.md` §5. Las anotaciones de abajo declaran los campos que `Cobro`
define (dataclass), para que el verificador de tipos los conozca acá.

**El estado después de un reembolso o una corrección es una función pura del acumulado**
(`_estado_por_acumulado`), así que una corrección puede bajarlo. Un reembolso **en vuelo** no es
un estado (decisión D27): son cuatro columnas que viven mientras dura.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from cheatsheet.contexts.payments.domain.dinero import redondear
from cheatsheet.contexts.payments.domain.estado_de_cobro import (
    MENSAJE_FECHA_ANTERIOR_AL_PAGO,
    MENSAJE_FECHA_FUTURA,
    MENSAJE_MONTO_NO_POSITIVO,
    MENSAJE_REEMBOLSO_EN_PROCESO,
    MENSAJE_REEMBOLSO_EXCEDIDO,
    MENSAJE_REEMBOLSO_MANUAL_SOLO_TRANSFERENCIA,
    MENSAJE_REEMBOLSO_NO_CORREGIBLE,
    MENSAJE_REEMBOLSO_POR_API_SOLO_LINK,
    MENSAJE_SIN_REEMBOLSO_EN_PROCESO,
    MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN,
    TOLERANCIA_DE_RELOJ,
    TRANSICIONES_LEGALES,
    EstadoCobro,
    MedioDePago,
)
from cheatsheet.contexts.payments.domain.reembolso import (
    OrigenDeReembolso,
    Reembolso,
    dia_de_argentina,
    mediodia_de_argentina,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


class ReembolsosDeCobro:
    """Lo que un cobro sabe hacer con la plata que devuelve."""

    id: UUID
    empresa_id: EmpresaId
    monto: Decimal
    estado: EstadoCobro
    medio_de_pago: MedioDePago
    fecha_pago: datetime | None
    updated_at: datetime | None
    monto_reembolsado: Decimal
    reembolso_solicitado_en: datetime | None
    reembolso_solicitado_monto: Decimal | None
    reembolso_clave_idempotencia: UUID | None
    reembolso_mp_refund_id: str | None

    def solicitar_reembolso(self, *, monto: Decimal, clave: UUID, ahora: datetime) -> Decimal:
        """HU-E6-05 — pide el reembolso a MercadoPago. **No cambia el estado** (D27).

        Solo por link, con el cobro pagado y **sin otro en vuelo**: la solicitud en vuelo es el
        mutex del reembolso por API. Guarda la `clave` de idempotencia, que es la que se reenvía en
        cada reintento: una clave nueva por intento duplicaría la devolución.
        """
        self._exigir_admite_reembolso()
        if self.medio_de_pago is not MedioDePago.LINK_MERCADOPAGO:
            raise InvarianteViolada(MENSAJE_REEMBOLSO_POR_API_SOLO_LINK)
        if self.reembolso_en_proceso:
            raise InvarianteViolada(MENSAJE_REEMBOLSO_EN_PROCESO)
        pedido = self._monto_a_reembolsar(monto)
        self.reembolso_solicitado_en = ahora
        self.reembolso_solicitado_monto = pedido
        self.reembolso_clave_idempotencia = clave
        self.reembolso_mp_refund_id = None
        self.updated_at = ahora
        return pedido

    def confirmar_reembolso(
        self,
        *,
        reembolso_id: UUID,
        monto: Decimal,
        mp_refund_id: str | None,
        fecha: datetime | None,
        ahora: datetime,
    ) -> Reembolso:
        """MercadoPago confirmó (RN-04). Recién ahora el acumulado y el estado cambian.

        Sin solicitud en vuelo no hay nada que confirmar: es lo que vuelve idempotente a la
        segunda confirmación de la misma respuesta. Un monto mayor al pendiente levanta sin
        tocar nada, y la solicitud sigue en vuelo.
        """
        if not self.reembolso_en_proceso:
            raise InvarianteViolada(MENSAJE_SIN_REEMBOLSO_EN_PROCESO)
        fila = self._nueva_fila(
            reembolso_id=reembolso_id,
            monto=self._monto_a_reembolsar(monto),
            fecha_devolucion=self._fecha_de_devolucion(fecha, ahora),
            origen=OrigenDeReembolso.API_MERCADOPAGO,
            ahora=ahora,
            mp_refund_id=mp_refund_id,
        )
        self._aplicar(fila.monto, ahora)
        self._limpiar_solicitud()
        return fila

    def rechazar_reembolso(self, ahora: datetime) -> None:
        """MercadoPago dijo que no (RN-03). El estado y el acumulado **no cambian**.

        No hay transición porque no hubo cambio de estado, y ahí está la elegancia de D27: la
        vuelta atrás no existe porque nunca se fue.
        """
        self._limpiar_solicitud()
        self.updated_at = ahora

    def registrar_id_de_reembolso(self, mp_refund_id: str, ahora: datetime) -> None:
        """MercadoPago contestó pero todavía no confirmó: el id permite consultarlo después."""
        if not self.reembolso_en_proceso:
            raise InvarianteViolada(MENSAJE_SIN_REEMBOLSO_EN_PROCESO)
        self.reembolso_mp_refund_id = mp_refund_id
        self.updated_at = ahora

    def registrar_reembolso_manual(
        self,
        *,
        reembolso_id: UUID,
        monto: Decimal,
        dia: date,
        referencia: str | None,
        motivo: str,
        usuario_id: UsuarioId,
        ahora: datetime,
    ) -> Reembolso:
        """HU-E6-05 RN-07 — la devolución de una transferencia, declarada a mano.

        `dia` es un día, no un instante: se guarda a las 12:00 de Argentina. No puede ser
        posterior a hoy ni anterior al día del pago.
        """
        self._exigir_admite_reembolso()
        if self.medio_de_pago is not MedioDePago.TRANSFERENCIA:
            raise InvarianteViolada(MENSAJE_REEMBOLSO_MANUAL_SOLO_TRANSFERENCIA)
        pedido = self._monto_a_reembolsar(monto)
        if dia > dia_de_argentina(ahora):
            raise EntradaInvalida(MENSAJE_FECHA_FUTURA)
        if self.fecha_pago is not None and dia < dia_de_argentina(self.fecha_pago):
            raise EntradaInvalida(MENSAJE_FECHA_ANTERIOR_AL_PAGO)
        fila = self._nueva_fila(
            reembolso_id=reembolso_id,
            monto=pedido,
            fecha_devolucion=mediodia_de_argentina(dia),
            origen=OrigenDeReembolso.MANUAL,
            ahora=ahora,
            referencia=referencia,
            motivo=motivo,
            registrado_por=usuario_id,
        )
        self._aplicar(fila.monto, ahora)
        return fila

    def corregir_reembolso(
        self,
        original: Reembolso,
        *,
        reembolso_id: UUID,
        ya_corregido: bool,
        motivo: str,
        usuario_id: UsuarioId,
        ahora: datetime,
    ) -> Reembolso:
        """RN-08 — un error se corrige con una fila **negativa** visible, nunca editando.

        Anula la fila entera (`-original.monto`); si el error era de monto, se registra después
        una fila nueva con el correcto. Solo filas manuales, que no sean correcciones ni estén
        ya corregidas: las de la API las manda MercadoPago, que es la fuente de verdad.
        """
        if (
            original.cobro_id != self.id
            or not original.es_manual
            or original.es_correccion
            or ya_corregido
        ):
            raise InvarianteViolada(MENSAJE_REEMBOLSO_NO_CORREGIBLE)
        fila = self._nueva_fila(
            reembolso_id=reembolso_id,
            monto=-original.monto,
            fecha_devolucion=ahora,
            origen=OrigenDeReembolso.MANUAL,
            ahora=ahora,
            motivo=motivo,
            corrige_a=original.id,
            registrado_por=usuario_id,
        )
        self._aplicar(fila.monto, ahora)
        return fila

    @property
    def reembolso_en_proceso(self) -> bool:
        return self.reembolso_solicitado_en is not None

    @property
    def reembolso_pedido(self) -> tuple[Decimal, UUID]:
        """El monto y la clave del reembolso en vuelo. Levanta si no hay ninguno."""
        if self.reembolso_solicitado_monto is None or self.reembolso_clave_idempotencia is None:
            raise InvarianteViolada(MENSAJE_SIN_REEMBOLSO_EN_PROCESO)
        return self.reembolso_solicitado_monto, self.reembolso_clave_idempotencia

    @property
    def pendiente_de_reembolso(self) -> Decimal:
        return self.monto - self.monto_reembolsado

    @property
    def admite_reembolso(self) -> bool:
        return self.estado in (EstadoCobro.APROBADO, EstadoCobro.REEMBOLSADO_PARCIAL)

    def _exigir_admite_reembolso(self) -> None:
        if not self.admite_reembolso:
            raise InvarianteViolada(MENSAJE_SOLO_PAGADOS_SE_REEMBOLSAN)

    def _monto_a_reembolsar(self, monto: Decimal) -> Decimal:
        """El monto redondeado **una sola vez**, positivo y dentro de lo que falta devolver."""
        pedido = redondear(monto)
        if pedido <= 0:
            raise EntradaInvalida(MENSAJE_MONTO_NO_POSITIVO)
        if pedido > self.pendiente_de_reembolso:
            raise EntradaInvalida(MENSAJE_REEMBOLSO_EXCEDIDO)
        return pedido

    def _fecha_de_devolucion(self, fecha: datetime | None, ahora: datetime) -> datetime:
        """La de MercadoPago si es plausible; si no, el momento de la confirmación."""
        if fecha is None or fecha.utcoffset() is None:
            return ahora
        if fecha > ahora + TOLERANCIA_DE_RELOJ:
            return ahora
        if self.fecha_pago is not None and fecha < self.fecha_pago:
            return ahora
        return fecha.astimezone(UTC)

    def _nueva_fila(
        self,
        *,
        reembolso_id: UUID,
        monto: Decimal,
        fecha_devolucion: datetime,
        origen: OrigenDeReembolso,
        ahora: datetime,
        referencia: str | None = None,
        motivo: str | None = None,
        corrige_a: UUID | None = None,
        mp_refund_id: str | None = None,
        registrado_por: UsuarioId | None = None,
    ) -> Reembolso:
        return Reembolso(
            id=reembolso_id,
            empresa_id=self.empresa_id,
            cobro_id=self.id,
            monto=monto,
            fecha_devolucion=fecha_devolucion,
            origen=origen,
            created_at=ahora,
            referencia=referencia,
            motivo=motivo,
            corrige_a=corrige_a,
            mp_refund_id=mp_refund_id,
            registrado_por=registrado_por,
        )

    def _aplicar(self, monto: Decimal, ahora: datetime) -> None:
        """Suma la fila al acumulado y **deriva** el estado de él (ADR-0010 punto 5)."""
        acumulado = self.monto_reembolsado + monto
        if not 0 <= acumulado <= self.monto:
            raise InvarianteViolada("El acumulado de reembolsos queda fuera de lo cobrado")
        self._transicionar(self._estado_por_acumulado(acumulado))
        self.monto_reembolsado = acumulado
        self.updated_at = ahora

    def _estado_por_acumulado(self, acumulado: Decimal) -> EstadoCobro:
        if acumulado == 0:
            return EstadoCobro.APROBADO
        if acumulado == self.monto:
            return EstadoCobro.REEMBOLSADO
        return EstadoCobro.REEMBOLSADO_PARCIAL

    def _limpiar_solicitud(self) -> None:
        self.reembolso_solicitado_en = None
        self.reembolso_solicitado_monto = None
        self.reembolso_clave_idempotencia = None
        self.reembolso_mp_refund_id = None

    def _transicionar(self, destino: EstadoCobro) -> None:
        if destino not in TRANSICIONES_LEGALES[self.estado]:
            raise InvarianteViolada(f"Un cobro no pasa de {self.estado.value} a {destino.value}")
        self.estado = destino


__all__ = ["ReembolsosDeCobro"]
