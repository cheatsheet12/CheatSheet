"""El mapeo entre `Cobro` y su fila (`CobroORM`), a mano en los dos sentidos.

Salió de `repositories.py` para que ese archivo quede bajo el tope de 400 líneas (`CLAUDE.md` §5).
El dominio no carga una dependencia de framework (R1): la traducción vive acá.
"""

from __future__ import annotations

from cheatsheet.contexts.payments.domain.cobro import (
    Cobro,
    EstadoCobro,
    LinkDePago,
    MedioDePago,
)
from cheatsheet.contexts.payments.infrastructure.models import CobroORM
from cheatsheet.shared.empresa import EmpresaId


def a_dominio(fila: CobroORM) -> Cobro:
    link = (
        LinkDePago(preference_id=fila.mp_preference_id, url=fila.mp_url_pago)
        if fila.mp_preference_id is not None and fila.mp_url_pago is not None
        else None
    )
    return Cobro(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        cliente_id=fila.cliente_id,
        monto=fila.monto,
        descripcion=fila.descripcion,
        vence_el=fila.vence_el,
        created_at=fila.created_at,
        estado=EstadoCobro(fila.estado),
        link=link,
        mp_payment_id=fila.mp_payment_id,
        comprobante_id=fila.comprobante_id,
        turno_id=fila.turno_id,
        fecha_pago=fila.fecha_pago,
        fecha_pago_aproximada=fila.fecha_pago_aproximada,
        medio_de_pago=MedioDePago(fila.medio_de_pago),
        numero_de_operacion=fila.numero_de_operacion,
        monto_reembolsado=fila.monto_reembolsado,
        reembolso_solicitado_en=fila.reembolso_solicitado_en,
        reembolso_solicitado_monto=fila.reembolso_solicitado_monto,
        reembolso_clave_idempotencia=fila.reembolso_clave_idempotencia,
        reembolso_mp_refund_id=fila.reembolso_mp_refund_id,
        motivo_de_cancelacion=fila.motivo_de_cancelacion,
        updated_at=fila.updated_at,
        clave_idempotencia=fila.clave_idempotencia,
    )


def a_fila(cobro: Cobro, fila: CobroORM) -> CobroORM:
    fila.id = cobro.id
    fila.empresa_id = cobro.empresa_id
    fila.cliente_id = cobro.cliente_id
    fila.comprobante_id = cobro.comprobante_id
    fila.turno_id = cobro.turno_id
    fila.monto = cobro.monto
    fila.monto_reembolsado = cobro.monto_reembolsado
    fila.descripcion = cobro.descripcion
    fila.estado = cobro.estado.value
    fila.mp_preference_id = cobro.link.preference_id if cobro.link else None
    fila.mp_url_pago = cobro.link.url if cobro.link else None
    fila.mp_payment_id = cobro.mp_payment_id
    fila.vence_el = cobro.vence_el
    fila.fecha_pago = cobro.fecha_pago
    fila.fecha_pago_aproximada = cobro.fecha_pago_aproximada
    fila.medio_de_pago = cobro.medio_de_pago.value
    fila.numero_de_operacion = cobro.numero_de_operacion
    fila.reembolso_solicitado_en = cobro.reembolso_solicitado_en
    fila.reembolso_solicitado_monto = cobro.reembolso_solicitado_monto
    fila.reembolso_clave_idempotencia = cobro.reembolso_clave_idempotencia
    fila.reembolso_mp_refund_id = cobro.reembolso_mp_refund_id
    fila.motivo_de_cancelacion = cobro.motivo_de_cancelacion
    fila.created_at = cobro.created_at
    fila.clave_idempotencia = cobro.clave_idempotencia
    fila.updated_at = cobro.updated_at or cobro.created_at
    return fila


__all__ = ["a_dominio", "a_fila"]
