"""El detalle de cobranza contra el motor: lo que ningun doble puede probar (ADR-0010, punto 6).

`cobrado_por_dia` y `por_estado` suman **en la base**, cortan el dia en una zona horaria y
tienen que dar las mismas cifras que `metricas`. Tres cosas viven solo aca:

- **El borde de dia**: un pago del 31/3 a las 23:30 hora argentina (02:30 UTC del 1/4) es del
  31/3, igual que en `_limites`.
- **Las identidades con `metricas`**: la suma de los dias es el `cobrado` del encabezado, y las
  filas de `por_estado` son `pendiente`, `en_mora` y `cobrado_de_lo_creado`. Dos consultas
  definen «cobrado»; este test es lo que las obliga a cambiar juntas.
- **RLS**: las dos agregaciones quedan acotadas a la empresa.

Necesitan PostgreSQL: se saltean sin base y corren en CI.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from cheatsheet.contexts.payments.application.cobranza_del_periodo import (
    CobrosDeUnEstado,
    DetalleDeCobranzaDelPeriodo,
)
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro
from cheatsheet.contexts.payments.domain.cobro import EstadoCobro
from cheatsheet.contexts.payments.infrastructure.consultas_de_cobranza import (
    ConsultasDeCobranzaPostgres,
)
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base
from tests.integracion.test_cobros_postgres import (
    FEBRERO,
    MARZO,
    _cliente,
    _cobro,
    _empresa,
    _guardar,
    _reembolsar_por_api,
)

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
#: Marzo entero, cortado en hora argentina como lo hace `_limites` en el ACL de reporting.
MARZO_ARGENTINO = FiltrosDeCobro(
    desde=datetime(2026, 3, 1, 0, 0, tzinfo=ZONA),
    hasta=datetime(2026, 3, 31, 23, 59, 59, 999999, tzinfo=ZONA),
)
#: 31/3 a las 23:30 en Buenos Aires: ya es 1/4 en UTC.
PAGO_DEL_31_A_LA_NOCHE = datetime(2026, 4, 1, 2, 30, tzinfo=UTC)


async def _por_dia(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, filtros: FiltrosDeCobro
) -> dict[date, Decimal]:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        return await ConsultasDeCobranzaPostgres(sesion).cobrado_por_dia(filtros, ZONA)


async def _por_estado(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, filtros: FiltrosDeCobro
) -> dict[EstadoCobro, CobrosDeUnEstado]:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        return await ConsultasDeCobranzaPostgres(sesion).por_estado(filtros)


# ------------------------------------------------------------------ caso 8: cobrado por dia


async def test_un_pago_del_31_a_la_noche_hora_argentina_cae_el_31(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id, monto="1000.00", creado_el=FEBRERO)
    cobro.aprobar(
        payment_id="pago-1", ahora=PAGO_DEL_31_A_LA_NOCHE, fecha_pago=PAGO_DEL_31_A_LA_NOCHE
    )
    await _guardar(sesiones, empresa_id, cobro)

    por_dia = await _por_dia(sesiones, empresa_id, MARZO_ARGENTINO)

    assert por_dia == {date(2026, 3, 31): Decimal("1000.00")}


async def test_un_reembolso_resta_el_dia_de_la_devolucion_y_el_dia_puede_quedar_negativo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    cobro = _cobro(empresa_id, cliente_id, monto="1000.00", creado_el=FEBRERO)
    cobro.aprobar(payment_id="pago-1", ahora=FEBRERO + timedelta(days=1))
    await _guardar(sesiones, empresa_id, cobro)
    await _reembolsar_por_api(sesiones, cobro, "300.00", MARZO)

    en_febrero = await _por_dia(
        sesiones,
        empresa_id,
        FiltrosDeCobro(
            desde=datetime(2026, 2, 1, tzinfo=ZONA),
            hasta=datetime(2026, 2, 28, 23, 59, tzinfo=ZONA),
        ),
    )
    en_marzo = await _por_dia(sesiones, empresa_id, MARZO_ARGENTINO)

    assert en_febrero == {date(2026, 2, 11): Decimal("1000.00")}
    assert en_marzo == {date(2026, 3, 5): Decimal("-300.00")}


async def test_los_pagos_y_las_devoluciones_del_mismo_dia_se_netean(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`0.10 + 0.20 = 0.30` en NUMERIC, y una devolucion del mismo dia resta del dia."""
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    uno = _cobro(empresa_id, cliente_id, monto="0.10", creado_el=FEBRERO, preferencia="a")
    otro = _cobro(empresa_id, cliente_id, monto="0.20", creado_el=FEBRERO, preferencia="b")
    grande = _cobro(empresa_id, cliente_id, monto="5.00", creado_el=FEBRERO, preferencia="c")
    for numero, cobro in enumerate((uno, otro, grande), start=1):
        cobro.aprobar(payment_id=f"pago-{numero}", ahora=MARZO, fecha_pago=MARZO)
    await _guardar(sesiones, empresa_id, uno, otro, grande)

    solo_pagos = await _por_dia(sesiones, empresa_id, MARZO_ARGENTINO)
    await _reembolsar_por_api(sesiones, grande, "5.00", MARZO + timedelta(hours=1))
    netos = await _por_dia(sesiones, empresa_id, MARZO_ARGENTINO)

    assert solo_pagos == {date(2026, 3, 5): Decimal("5.30")}
    assert netos == {date(2026, 3, 5): Decimal("0.30")}
    assert all(isinstance(monto, Decimal) for monto in netos.values())


# ------------------------------------------------------------------ caso 9: identidades


async def test_el_detalle_cuadra_con_las_metricas_del_encabezado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    pendiente = _cobro(empresa_id, cliente_id, monto="500.00", creado_el=MARZO, preferencia="a")
    moroso = _cobro(empresa_id, cliente_id, monto="250.00", creado_el=MARZO, preferencia="b")
    moroso.vencer(MARZO + timedelta(days=1))
    pagado = _cobro(empresa_id, cliente_id, monto="1000.00", creado_el=MARZO, preferencia="c")
    pagado.aprobar(payment_id="pago-1", ahora=MARZO + timedelta(hours=1))
    parcial = _cobro(empresa_id, cliente_id, monto="400.00", creado_el=MARZO, preferencia="d")
    parcial.aprobar(payment_id="pago-2", ahora=MARZO + timedelta(hours=2))
    viejo = _cobro(empresa_id, cliente_id, monto="9000.00", creado_el=FEBRERO, preferencia="e")
    viejo.aprobar(payment_id="pago-3", ahora=MARZO, fecha_pago=MARZO)
    await _guardar(sesiones, empresa_id, pendiente, moroso, pagado, parcial, viejo)
    await _reembolsar_por_api(sesiones, parcial, "150.00", MARZO + timedelta(days=3))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        metricas = await RepositorioCobroPostgres(sesion).metricas(MARZO_ARGENTINO)
        detalle = await DetalleDeCobranzaDelPeriodo(ConsultasDeCobranzaPostgres(sesion)).ejecutar(
            filtros=MARZO_ARGENTINO, zona=ZONA
        )

    assert sum(detalle.cobrado_por_dia.values(), Decimal("0.00")) == metricas.cobrado
    assert detalle.por_estado[EstadoCobro.PENDIENTE].monto == metricas.pendiente
    assert detalle.por_estado[EstadoCobro.VENCIDO].monto == metricas.en_mora
    pagados = (
        EstadoCobro.APROBADO,
        EstadoCobro.REEMBOLSADO_PARCIAL,
        EstadoCobro.REEMBOLSADO,
    )
    assert (
        sum((detalle.por_estado[e].monto for e in pagados if e in detalle.por_estado), Decimal(0))
        == metricas.cobrado_de_lo_creado
    )


# ------------------------------------------------------------------ caso 10: por estado


async def test_por_estado_agrupa_lo_creado_en_el_periodo_por_su_estado_actual(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    # Creado en febrero y pagado en marzo: es «Pagado» de febrero y no aparece en marzo.
    de_febrero = _cobro(empresa_id, cliente_id, monto="1000.00", creado_el=FEBRERO, preferencia="a")
    de_febrero.aprobar(payment_id="pago-1", ahora=MARZO, fecha_pago=MARZO)
    abierto = _cobro(empresa_id, cliente_id, monto="500.00", creado_el=MARZO, preferencia="b")
    otro_abierto = _cobro(empresa_id, cliente_id, monto="0.50", creado_el=MARZO, preferencia="c")
    cancelado = _cobro(empresa_id, cliente_id, monto="70.00", creado_el=MARZO, preferencia="d")
    cancelado.cancelar(motivo="Se cargo por error", ahora=MARZO + timedelta(hours=1))
    await _guardar(sesiones, empresa_id, de_febrero, abierto, otro_abierto, cancelado)

    en_febrero = await _por_estado(
        sesiones,
        empresa_id,
        FiltrosDeCobro(
            desde=datetime(2026, 2, 1, tzinfo=ZONA),
            hasta=datetime(2026, 2, 28, 23, 59, tzinfo=ZONA),
        ),
    )
    en_marzo = await _por_estado(sesiones, empresa_id, MARZO_ARGENTINO)

    assert en_febrero == {EstadoCobro.APROBADO: CobrosDeUnEstado(1, Decimal("1000.00"))}
    assert en_marzo == {
        EstadoCobro.PENDIENTE: CobrosDeUnEstado(2, Decimal("500.50")),
        EstadoCobro.CANCELADO: CobrosDeUnEstado(1, Decimal("70.00")),
    }


# ------------------------------------------------------------------ caso 11: RLS


async def test_el_detalle_de_una_empresa_no_incluye_los_cobros_ni_las_devoluciones_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    con_datos = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, con_datos)
    cobro = _cobro(con_datos, cliente_id, monto="1000.00", creado_el=MARZO)
    cobro.aprobar(payment_id=f"pago-{uuid.uuid4()}", ahora=MARZO + timedelta(hours=1))
    await _guardar(sesiones, con_datos, cobro)
    await _reembolsar_por_api(sesiones, cobro, "100.00", MARZO + timedelta(days=2))
    vacia = await _empresa(engine_dueno)

    assert await _por_dia(sesiones, vacia, MARZO_ARGENTINO) == {}
    assert await _por_estado(sesiones, vacia, MARZO_ARGENTINO) == {}
    assert await _por_dia(sesiones, con_datos, MARZO_ARGENTINO) != {}
    assert await _por_estado(sesiones, con_datos, MARZO_ARGENTINO) != {}
