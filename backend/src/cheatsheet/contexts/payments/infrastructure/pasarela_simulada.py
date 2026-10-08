"""`PasarelaSimulada`: el doble de `PortPasarelaDePago`, sin socket.

Vive aparte de `pasarela.py` (que lo reexporta) para que cada archivo quepa en las 400 líneas de
`CLAUDE.md` §5. **Se niega a construirse en producción**, como los cinco anteriores, y acá con
más en juego que en ninguno: una empresa cobrando contra este doble estaría entregando links que
nadie puede pagar y dando por saldadas deudas que nadie pagó.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from cheatsheet.contexts.payments.application.errors import PasarelaNoDisponible
from cheatsheet.contexts.payments.application.ports import (
    EstadoDeReembolso,
    PagoRecibido,
    RespuestaDeReembolso,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.empresa import EmpresaId


class PasarelaSimulada:
    """El doble: links y pagos sin socket.

    **Rechazado en producción**, y acá con más en juego que en ningún otro simulado del
    sistema: una empresa cobrando contra esto estaría entregando links que nadie puede pagar y
    dando por saldadas deudas que nadie pagó.

    No es siempre-que-sí a propósito. Un cobro cuya descripción contenga «rechazar» hace que
    el reembolso vuelva rechazado **y que la invalidación del link falle**, y uno que contenga
    «demorar» deja el reembolso en proceso hasta la primera consulta («Actualizar estado»): las
    tres ramas se pueden caminar en una laptop sin editar código.
    """

    #: Las palabras que disparan cada rama. Documentadas acá porque un doble cuyo comportamiento
    #: hay que adivinar leyendo el código no sirve para lo que existe.
    PALABRA_DE_RECHAZO = "rechazar"
    PALABRA_DE_DEMORA = "demorar"

    def __init__(self, entorno: Entorno = Entorno.LOCAL) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "La pasarela simulada no puede usarse en produccion: entregaria links que "
                "nadie puede pagar y daria por saldadas deudas que nadie pago"
            )
        self.links: dict[str, str] = {}
        self.reembolsos: list[tuple[str, Decimal]] = []
        self.invalidados: list[str] = []
        #: El `external_reference` de cada preferencia (el id del cobro), como lo propaga
        #: MercadoPago al pago. Separado de `links`: invalidar una preferencia no lo borra.
        self._referencias: dict[str, str] = {}
        self._rechazan: set[str] = set()
        self._demoran: set[str] = set()
        #: Lo que ya contestó, por clave: la misma clave devuelve el mismo reembolso, como
        #: MercadoPago (documentado, no verificado: `TODO.md` §20.10).
        self._por_clave: dict[UUID, RespuestaDeReembolso] = {}
        self._por_reembolso: dict[str, RespuestaDeReembolso] = {}
        self._demorados: dict[str, tuple[str, Decimal]] = {}

    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        del empresa_id, url_de_retorno
        preferencia = f"pref-{cobro.id}"
        self.links[preferencia] = str(cobro.id)
        self._referencias[preferencia] = str(cobro.id)
        if self.PALABRA_DE_RECHAZO in cobro.descripcion.lower():
            self._rechazan.add(preferencia)
        if self.PALABRA_DE_DEMORA in cobro.descripcion.lower():
            self._demoran.add(preferencia)
        return LinkDePago(
            preference_id=preferencia,
            # Con la forma de una real: un código que sólo vio `http://x` es un código que se
            # rompe el día que ve una URL de verdad.
            url=f"https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id={preferencia}",
        )

    async def invalidar_link(
        self, *, empresa_id: EmpresaId, preference_id: str, ahora: datetime
    ) -> None:
        del empresa_id, ahora
        if preference_id in self._rechazan:
            raise PasarelaNoDisponible("MercadoPago no invalido el link de pago (simulado)")
        # Se saca de `links` porque eso es lo que la invalidación significa acá: el doble deja
        # de reconocer la preferencia, igual que MercadoPago deja de cobrarla.
        self.links.pop(preference_id, None)
        self.invalidados.append(preference_id)

    async def consultar_pago(self, *, empresa_id: EmpresaId, payment_id: str) -> PagoRecibido:
        del empresa_id
        preferencia = self._preferencia_de(payment_id)
        return PagoRecibido(
            payment_id=payment_id,
            preference_id=preferencia,
            referencia_externa=self._referencias.get(preferencia),
            estado="approved",
            # La hora actual en UTC, para que una demo local no muestre «aproximada».
            fecha_aprobacion=datetime.now(UTC),
        )

    async def reembolsar(
        self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal, clave: UUID
    ) -> RespuestaDeReembolso:
        del empresa_id
        if clave in self._por_clave:
            return self._por_clave[clave]
        preferencia = self._preferencia_de(payment_id)
        identificador = f"ref-{clave}"
        if preferencia in self._rechazan:
            respuesta = RespuestaDeReembolso(
                estado=EstadoDeReembolso.RECHAZADO, motivo="Reembolso rechazado (simulado)"
            )
        elif preferencia in self._demoran:
            self._demorados[identificador] = (payment_id, monto)
            respuesta = RespuestaDeReembolso(
                estado=EstadoDeReembolso.EN_PROCESO, mp_refund_id=identificador
            )
        else:
            respuesta = self._aceptar(identificador, payment_id, monto)
        self._por_clave[clave] = respuesta
        return respuesta

    async def consultar_reembolso(
        self, *, empresa_id: EmpresaId, payment_id: str, refund_id: str
    ) -> RespuestaDeReembolso:
        del empresa_id, payment_id
        if refund_id in self._demorados:
            pago, monto = self._demorados.pop(refund_id)
            self._aceptar(refund_id, pago, monto)
        if refund_id not in self._por_reembolso:
            raise PasarelaNoDisponible("MercadoPago no conoce ese reembolso (simulado)")
        return self._por_reembolso[refund_id]

    def _aceptar(self, identificador: str, payment_id: str, monto: Decimal) -> RespuestaDeReembolso:
        self.reembolsos.append((payment_id, monto))
        respuesta = RespuestaDeReembolso(
            estado=EstadoDeReembolso.ACEPTADO,
            mp_refund_id=identificador,
            monto=monto,
            fecha=datetime.now(UTC),
        )
        self._por_reembolso[identificador] = respuesta
        return respuesta

    def _preferencia_de(self, payment_id: str) -> str:
        """El doble ata el pago a la preferencia por convención: `pago-<preferencia>`."""
        return payment_id.removeprefix("pago-")


__all__ = ["PasarelaSimulada"]
