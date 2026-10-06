"""El mapeo `Cobro` <-> `CobroORM` sin base de datos: es una función pura entre dos objetos.

Lo que importa acá es el reembolso en vuelo: si la clave de idempotencia no viaja en el mapeo,
el reintento generaría una clave nueva y MercadoPago reembolsaría dos veces. Que la fila sobreviva
a una transacción real (RLS, columnas, constraints) lo prueba `tests/integracion/`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from cheatsheet.contexts.payments.domain.cobro import Cobro, LinkDePago
from cheatsheet.contexts.payments.infrastructure.mapeo_de_cobro import a_dominio, a_fila
from cheatsheet.contexts.payments.infrastructure.models import CobroORM
from cheatsheet.shared.empresa import EmpresaId

AHORA = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _cobro_con_reembolso_en_vuelo() -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        cliente_id=uuid4(),
        monto=Decimal("1000.00"),
        descripcion="Consulta",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA - timedelta(days=3),
    )
    cobro.asignar_link(LinkDePago(preference_id="pref-1", url="https://mp/pay"), AHORA)
    cobro.aprobar(payment_id="pago-1", ahora=AHORA)
    cobro.reembolso_solicitado_en = AHORA
    cobro.reembolso_solicitado_monto = Decimal("250.00")
    cobro.reembolso_clave_idempotencia = uuid4()
    cobro.reembolso_mp_refund_id = "refund-9"
    cobro.monto_reembolsado = Decimal("100.00")
    return cobro


def test_la_clave_y_el_reembolso_en_vuelo_hacen_el_viaje_de_ida_y_vuelta() -> None:
    cobro = _cobro_con_reembolso_en_vuelo()

    fila = a_fila(cobro, CobroORM())

    assert fila.reembolso_clave_idempotencia == cobro.reembolso_clave_idempotencia
    assert fila.reembolso_solicitado_monto == Decimal("250.00")
    assert fila.reembolso_solicitado_en == AHORA
    assert fila.reembolso_mp_refund_id == "refund-9"
    leido = a_dominio(fila)
    assert leido.reembolso_clave_idempotencia == cobro.reembolso_clave_idempotencia
    assert leido.reembolso_solicitado_monto == cobro.reembolso_solicitado_monto
    assert leido.reembolso_solicitado_en == cobro.reembolso_solicitado_en
    assert leido.reembolso_mp_refund_id == cobro.reembolso_mp_refund_id
    assert leido.monto_reembolsado == cobro.monto_reembolsado


def test_sin_reembolso_en_vuelo_las_cuatro_columnas_quedan_vacias() -> None:
    cobro = _cobro_con_reembolso_en_vuelo()
    cobro.reembolso_solicitado_en = None
    cobro.reembolso_solicitado_monto = None
    cobro.reembolso_clave_idempotencia = None
    cobro.reembolso_mp_refund_id = None

    leido = a_dominio(a_fila(cobro, CobroORM()))

    assert leido.reembolso_clave_idempotencia is None
    assert leido.reembolso_solicitado_en is None


def test_la_clave_del_pedido_hace_el_viaje_de_ida_y_vuelta_y_puede_faltar() -> None:
    """ADR-0013: la clave que mandó el cliente vive en la fila; los cobros viejos no la tienen."""
    cobro = _cobro_con_reembolso_en_vuelo()
    cobro.clave_idempotencia = uuid4()

    fila = a_fila(cobro, CobroORM())

    assert fila.clave_idempotencia == cobro.clave_idempotencia
    assert a_dominio(fila).clave_idempotencia == cobro.clave_idempotencia
    cobro.clave_idempotencia = None
    assert a_dominio(a_fila(cobro, CobroORM())).clave_idempotencia is None
