"""Dos webhooks del mismo pago a la vez contra el motor (#240, HS-T1, HU-E6-06 RN-03).

`ConfirmarPago` cargaba el cobro sin bloqueo. Dos notificaciones del mismo `payment_id`,
cada una en su transacción, pasaban `buscar_por_payment_id` (ninguna había commiteado), veían
el cobro abierto y lo aprobaban: la segunda esperaba el bloqueo de la fila en el `UPDATE`,
reescribía la misma fila --el índice único no salta, es la misma fila-- y después le restaba
otra vez el monto al saldo del comprobante, con un segundo `confirmar_pago` en la bitácora.

El solapamiento es **determinista**, nunca con un `sleep` (mismo patrón que
`test_entregas_concurrentes_postgres.py`):

* **A** es un webhook que procesa y se queda abierto dentro de su transacción.
* **B** es el segundo webhook del mismo pago, lanzado como tarea mientras A sigue abierto.
* El test consulta `pg_locks` hasta ver a alguien esperando un bloqueo; recién ahí A confirma
  y B termina.

El saldo es el real (`SaldoViaBilling` sobre el repositorio de `billing` en PostgreSQL) y los
eventos se cuentan en `registro_de_auditoria`, que es lo que la bitácora mostraría de verdad.
Sin PostgreSQL se saltean; los confirma la CI del PR.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from cheatsheet.contexts.billing.domain.comprobante import EstadoComprobante
from cheatsheet.contexts.billing.infrastructure.repositorio_comprobante import (
    RepositorioComprobantePostgres,
)
from cheatsheet.contexts.observability.application.registrar_operacion import RegistrarOperacion
from cheatsheet.contexts.observability.infrastructure.repository import (
    RepositorioDeAuditoriaPostgres,
)
from cheatsheet.contexts.observability.infrastructure.subscriber import SuscriptorDeAuditoria
from cheatsheet.contexts.payments.application.confirmacion import (
    ConfirmarPago,
    ResultadoDeConfirmacion,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro
from cheatsheet.contexts.payments.infrastructure.repositories import RepositorioCobroPostgres
from cheatsheet.contexts.payments.infrastructure.saldo import SaldoViaBilling
from cheatsheet.platform.events import PublicadorEnProceso
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.payments.application.test_confirmacion import PasarelaFalsa
from tests.integracion.conftest import requiere_base
from tests.integracion.test_cobros_postgres import AHORA, _cobro, _guardar
from tests.integracion.test_comprobantes_postgres import (
    _cliente,
    _comprobante,
    _empresa,
    _punto,
)
from tests.integracion.test_comprobantes_postgres import _guardar as _guardar_comprobante
from tests.integracion.test_entregas_concurrentes_postgres import _a_abierto_y_b_en_espera

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

MONTO_DEL_COBRO = Decimal("400.00")
PAYMENT_ID = "pago-concurrente-1"

Webhook = Callable[[AsyncSession], Awaitable[None]]


class Escenario:
    """Una empresa con un comprobante autorizado y un cobro (parcial) que lo salda."""

    def __init__(
        self, empresa_id: EmpresaId, cobro: Cobro, comprobante_id: uuid.UUID, total: Decimal
    ) -> None:
        self.empresa_id = empresa_id
        self.cobro = cobro
        self.comprobante_id = comprobante_id
        self.total = total


async def _escenario(
    sesiones: async_sessionmaker[AsyncSession],
    engine_dueno: AsyncEngine,
    *,
    cancelado: bool = False,
) -> Escenario:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id)
    punto = await _punto(sesiones, empresa_id)
    comprobante = _comprobante(
        empresa_id, cliente_id, punto, numero=1, estado=EstadoComprobante.AUTORIZADO
    )
    await _guardar_comprobante(sesiones, empresa_id, comprobante)

    cobro = _cobro(empresa_id, cliente_id, monto=str(MONTO_DEL_COBRO), preferencia="pref-conc-1")
    cobro.comprobante_id = comprobante.id
    if cancelado:
        cobro.cancelar(motivo="Se cargó por error, lo da de baja el administrador", ahora=AHORA)
    await _guardar(sesiones, empresa_id, cobro)
    return Escenario(empresa_id, cobro, comprobante.id, comprobante.total)


def _webhook(
    escenario: Escenario, pasarela: PasarelaFalsa, resultados: list[ResultadoDeConfirmacion]
) -> Webhook:
    """Un webhook completo: su propia transacción, su propio publicador, el saldo real."""

    async def aplicar(sesion: AsyncSession) -> None:
        publicador = PublicadorEnProceso()
        publicador.suscribir(
            SuscriptorDeAuditoria(RegistrarOperacion(RepositorioDeAuditoriaPostgres(sesion)))
        )
        resultado = await ConfirmarPago(
            cobros=RepositorioCobroPostgres(sesion),
            pasarela=pasarela,
            saldos=SaldoViaBilling(RepositorioComprobantePostgres(sesion)),
            publicador=publicador,
        ).ejecutar(empresa_id=escenario.empresa_id, payment_id=PAYMENT_ID, ahora=AHORA)
        resultados.append(resultado)

    return aplicar


async def _saldo_del_comprobante(engine: AsyncEngine, comprobante_id: uuid.UUID) -> Decimal:
    async with engine.connect() as conexion:
        saldo = (
            await conexion.execute(
                text("SELECT saldo_pendiente FROM comprobante WHERE id = :id"),
                {"id": comprobante_id},
            )
        ).scalar_one()
    return Decimal(saldo)


async def _acciones_de_la_bitacora(engine: AsyncEngine, cobro_id: uuid.UUID) -> list[str]:
    async with engine.connect() as conexion:
        filas = (
            await conexion.execute(
                text(
                    "SELECT accion FROM registro_de_auditoria "
                    "WHERE entidad_afectada = :entidad ORDER BY accion"
                ),
                {"entidad": f"Cobro:{cobro_id}"},
            )
        ).all()
    return [fila.accion for fila in filas]


async def _estado_y_pago_del_cobro(
    engine: AsyncEngine, cobro_id: uuid.UUID
) -> tuple[str, str | None]:
    async with engine.connect() as conexion:
        fila = (
            await conexion.execute(
                text("SELECT estado, mp_payment_id FROM cobro WHERE id = :id"), {"id": cobro_id}
            )
        ).one()
    return fila.estado, fila.mp_payment_id


# Cómo encuentra el webhook el cobro: por el `external_reference` (el camino habitual de
# Checkout Pro) o, si no viene, por la preferencia.
def _pasarela(escenario: Escenario, *, por: str) -> PasarelaFalsa:
    if por == "external_reference":
        return PasarelaFalsa(cobro_id=escenario.cobro.id, preferencia=None)
    return PasarelaFalsa(cobro_id=None, preferencia="pref-conc-1")


POR = [
    pytest.param("external_reference", id="por-external-reference"),
    pytest.param("preference_id", id="por-preferencia"),
]


@pytest.mark.parametrize("por", POR)
async def test_dos_webhooks_concurrentes_del_mismo_pago_bajan_el_saldo_una_sola_vez(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine, por: str
) -> None:
    escenario = await _escenario(sesiones, engine_dueno)
    resultados: list[ResultadoDeConfirmacion] = []

    await _a_abierto_y_b_en_espera(
        engine_dueno,
        sesiones,
        escenario.empresa_id,
        a=_webhook(escenario, _pasarela(escenario, por=por), resultados),
        b=_webhook(escenario, _pasarela(escenario, por=por), resultados),
    )

    # El primero aprueba y baja el saldo una vez; el segundo no toca nada.
    assert await _saldo_del_comprobante(engine_dueno, escenario.comprobante_id) == (
        escenario.total - MONTO_DEL_COBRO
    )
    assert await _acciones_de_la_bitacora(engine_dueno, escenario.cobro.id) == ["confirmar_pago"]
    assert [(r.aprobado, r.ya_procesado) for r in resultados] == [(True, False), (True, True)]
    assert await _estado_y_pago_del_cobro(engine_dueno, escenario.cobro.id) == (
        EstadoCobro.APROBADO.value,
        PAYMENT_ID,
    )


async def test_dos_webhooks_concurrentes_sobre_un_cobro_cancelado_registran_un_solo_huerfano(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    escenario = await _escenario(sesiones, engine_dueno, cancelado=True)
    resultados: list[ResultadoDeConfirmacion] = []

    await _a_abierto_y_b_en_espera(
        engine_dueno,
        sesiones,
        escenario.empresa_id,
        a=_webhook(escenario, _pasarela(escenario, por="external_reference"), resultados),
        b=_webhook(escenario, _pasarela(escenario, por="external_reference"), resultados),
    )

    # Un solo huérfano, una sola alerta, y el saldo intacto (esa plata no está imputada).
    assert await _acciones_de_la_bitacora(engine_dueno, escenario.cobro.id) == [
        "pago_sobre_cobro_cancelado"
    ]
    assert [(r.huerfano, r.ya_procesado) for r in resultados] == [(True, False), (False, True)]
    assert await _saldo_del_comprobante(engine_dueno, escenario.comprobante_id) == escenario.total
    assert await _estado_y_pago_del_cobro(engine_dueno, escenario.cobro.id) == (
        EstadoCobro.CANCELADO.value,
        PAYMENT_ID,
    )
