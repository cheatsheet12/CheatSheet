"""`GenerarCobro` (HU-E6-03 y HU-E6-06), con la clave de idempotencia del pedido (ADR-0013).

Vive aparte de `cobros.py`, que ya pasaba de 400 líneas (`CLAUDE.md` §5).

**Orden**: rol → bloqueo y búsqueda por clave → (si existe: comparar y devolver) → cliente →
comprobante y saldo → link → persistir con la clave → bitácora. La búsqueda va antes de validar
el cliente a propósito: si el cliente se desactivó después del primer pedido, el reintento igual
tiene que devolver el cobro que ya existe, no un 422.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.application.cobros import exigir_gestor
from cheatsheet.contexts.payments.application.errors import (
    ClaveDeIdempotenciaReusada,
    ClienteInexistente,
    CobroInexistente,
    ComprobanteDeOtroCliente,
    MontoExcedeSaldo,
)
from cheatsheet.contexts.payments.application.ports import (
    PortClienteDeCobro,
    PortPasarelaDePago,
    PortRepositorioCobro,
    PortSaldoDeComprobante,
)
from cheatsheet.contexts.payments.domain.cobro import VIGENCIA_POR_DEFECTO, Cobro
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

#: HU-E6-06 RN-02, con el saldo disponible adentro: el criterio pide que el mensaje **indique
#: el saldo**, no sólo que hubo exceso.
MENSAJE_EXCEDE_SALDO = "El monto no puede superar el saldo pendiente del comprobante."
MENSAJE_CLIENTE_INEXISTENTE = "El cliente seleccionado no existe o esta inactivo."
MENSAJE_COMPROBANTE_DE_OTRO_CLIENTE = "El comprobante no corresponde al cliente elegido."
MENSAJE_CLAVE_REUSADA = (
    "Esta clave ya se uso para generar un cobro con otros datos. "
    "Revise el listado de cobros antes de reintentar."
)

logger = obtener_logger(__name__)


class GenerarCobro:
    """HU-E6-03 y HU-E6-06 — el link de pago, con o sin comprobante detrás.

    **El link se pide antes de guardar nada.** El criterio de aceptación lo exige: si
    MercadoPago no responde, «no crea el cobro». Un cobro sin link es una deuda que nadie
    puede pagar y que igual manda recordatorios, que es la peor de las dos formas de fallar.

    **El mismo pedido repetido devuelve el cobro original** y no vuelve a llamar a MercadoPago
    (ADR-0013): la clave la manda el cliente, que es el único que sabe si es «el mismo pedido»
    o «otro igual».
    """

    def __init__(
        self,
        *,
        cobros: PortRepositorioCobro,
        pasarela: PortPasarelaDePago,
        saldos: PortSaldoDeComprobante,
        clientes: PortClienteDeCobro,
        publicador: PublicadorDeEventos,
        url_de_retorno: str,
    ) -> None:
        self._cobros = cobros
        self._pasarela = pasarela
        self._saldos = saldos
        self._clientes = clientes
        self._publicador = publicador
        self._url_de_retorno = url_de_retorno

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        clave_idempotencia: UUID,
        cliente_id: UUID,
        monto: Decimal,
        descripcion: str,
        ahora: datetime,
        comprobante_id: UUID | None = None,
        turno_id: UUID | None = None,
        vigencia: timedelta = VIGENCIA_POR_DEFECTO,
    ) -> Cobro:
        exigir_gestor(rol)

        # Con el bloqueo tomado, un segundo pedido con la misma clave espera acá a que el
        # primero termine (commit o rollback) y recién entonces lee.
        existente = await self._cobros.buscar_por_clave_bloqueada(clave_idempotencia)
        if existente is not None:
            return self._repetido(existente, cliente_id, monto, descripcion, comprobante_id)

        # El cliente va antes que el comprobante y que la pasarela: un cliente invalido no
        # tiene que gastar una preferencia en MercadoPago, y el rol va antes que todo para que
        # la respuesta no deje ver si el id existe.
        if not await self._clientes.esta_activo(cliente_id):
            raise ClienteInexistente(MENSAJE_CLIENTE_INEXISTENTE)

        if comprobante_id is not None:
            await self._exigir_comprobante_del_cliente(comprobante_id, cliente_id)
            await self._exigir_saldo_suficiente(comprobante_id, monto)

        cobro = Cobro(
            id=uuid4(),
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            monto=monto,
            descripcion=descripcion,
            vence_el=ahora + vigencia,
            created_at=ahora,
            comprobante_id=comprobante_id,
            turno_id=turno_id,
            updated_at=ahora,
            clave_idempotencia=clave_idempotencia,
        )

        # Antes de persistir: si esto levanta, no queda nada escrito. Es el criterio de
        # aceptación de «MercadoPago no responde al generar el link».
        link = await self._pasarela.crear_link(
            empresa_id=empresa_id, cobro=cobro, url_de_retorno=self._url_de_retorno
        )
        cobro.asignar_link(link, ahora)
        await self._cobros.agregar(cobro)

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                usuario_id=usuario_id,
                modulo=Modulo.PAYMENTS,
                accion="generar_cobro",
                entidad_afectada=f"Cobro:{cobro.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return cobro

    @staticmethod
    def _repetido(
        existente: Cobro,
        cliente_id: UUID,
        monto: Decimal,
        descripcion: str,
        comprobante_id: UUID | None,
    ) -> Cobro:
        """La clave ya creó un cobro: el mismo pedido lo devuelve, otro pedido se rechaza.

        No se publica `generar_cobro` en la bitácora (no hubo efecto): queda un log estructurado
        sin datos personales.
        """
        if not existente.es_el_mismo_pedido(
            cliente_id=cliente_id,
            monto=monto,
            descripcion=descripcion,
            comprobante_id=comprobante_id,
        ):
            raise ClaveDeIdempotenciaReusada(MENSAJE_CLAVE_REUSADA)
        logger.info("cobro_pedido_repetido", cobro_id=str(existente.id))
        return existente

    async def _exigir_comprobante_del_cliente(self, comprobante_id: UUID, cliente_id: UUID) -> None:
        """Con el selector editable, cambiar de cliente con un comprobante elegido es un caso
        cotidiano, y cobrarle a Ana la factura de Bruno es cobrar una deuda ajena."""
        dueno = await self._saldos.cliente_de(comprobante_id)
        # `None` es «no existe»: eso lo dice la comprobacion del saldo, con su propio mensaje.
        if dueno is not None and dueno != cliente_id:
            raise ComprobanteDeOtroCliente(MENSAJE_COMPROBANTE_DE_OTRO_CLIENTE)

    async def _exigir_saldo_suficiente(self, comprobante_id: UUID, monto: Decimal) -> None:
        """HU-E6-06 RN-02, contra el saldo **actual** del comprobante.

        No se descuenta nada acá (decisión **D26**): un link generado no es plata cobrada, y
        un comprobante cuyo saldo bajó porque alguien generó un link que nadie pagó miente en
        el balance. El descuento lo hace la aprobación.
        """
        saldo = await self._saldos.saldo_pendiente(comprobante_id)
        if saldo is None:
            raise CobroInexistente("El comprobante no existe")
        if monto > saldo:
            raise MontoExcedeSaldo(f"{MENSAJE_EXCEDE_SALDO} Saldo disponible: $ {saldo}.")


__all__ = [
    "MENSAJE_CLAVE_REUSADA",
    "MENSAJE_CLIENTE_INEXISTENTE",
    "MENSAJE_COMPROBANTE_DE_OTRO_CLIENTE",
    "MENSAJE_EXCEDE_SALDO",
    "GenerarCobro",
]
