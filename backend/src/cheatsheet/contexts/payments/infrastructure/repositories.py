"""Adaptadores PostgreSQL de los dos repositorios de `payments`.

Las convenciones de siempre: mapeo a mano en los dos sentidos para que el dominio no cargue
una dependencia de framework (R1), y `empresa_id` nunca en un `WHERE` porque RLS ya acota.

**Ninguno tiene `eliminar`.** Un cobro aprobado es plata que entro y un recordatorio enviado es
un mensaje que un cliente recibio: los dos se cancelan o se reembolsan, no se borran.

`metricas` suma **en la base** y no en Python sobre `listar`. La diferencia no es de
rendimiento: las metricas son del periodo entero y el listado se pagina, asi que sumarlas
sobre la pagina mostraria un total que cambia al pasar de hoja. El listado sigue filtrando por
fecha de creacion; `cobrado` mide por fecha de pago (D91).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Select, String, cast, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from cheatsheet.contexts.payments.application.errors import PedidoEnCurso, RecordatorioDuplicado
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro, MetricasDeCobros
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.contexts.payments.infrastructure.mapeo_de_cobro import a_dominio, a_fila
from cheatsheet.contexts.payments.infrastructure.models import (
    CobroORM,
    RecordatorioORM,
    ReembolsoORM,
)
from cheatsheet.shared.empresa import EmpresaId

CERO = Decimal("0.00")

#: Primera clave de `pg_advisory_xact_lock(int4, int4)`: el espacio de las claves de pedido de un
#: cobro (ASCII "CC" en los bytes altos). La segunda es `hashtext(empresa_id || ':' || clave)`.
#: Un choque de hash solo hace esperar a dos claves distintas: no expone datos (ADR-0013).
ESPACIO_CLAVE_DE_COBRO = 0x4343_0001
#: El nombre del indice unico de la migracion 0034, para traducir solo ese `IntegrityError`.
INDICE_CLAVE_DE_COBRO = "uq_cobro_clave_idempotencia"
MENSAJE_PEDIDO_EN_CURSO = "Ese pedido ya se esta procesando. Intente nuevamente."

#: Los tres estados de un cobro que se pagó, por bruto: un reembolso no deshace que se cobró.
ESTADOS_PAGADOS = (
    EstadoCobro.APROBADO.value,
    EstadoCobro.REEMBOLSADO_PARCIAL.value,
    EstadoCobro.REEMBOLSADO.value,
)

#: El listado y las métricas comparten los mismos filtros y devuelven formas distintas —una
#: entidad y una agregación—, así que `_con_filtros` es genérico sobre el `Select`. Sin esto
#: habría dos copias de los mismos tres `where`, que es donde una empresa termina viendo un
#: total calculado sobre un filtro distinto del que muestra.
_Sentencia = TypeVar("_Sentencia", bound=Select[Any])


def en_periodo(
    sentencia: _Sentencia,
    columna: InstrumentedAttribute[datetime] | InstrumentedAttribute[datetime | None],
    filtros: FiltrosDeCobro,
) -> _Sentencia:
    """Acota una sentencia al período de los filtros, sobre la columna de fecha que se diga.

    Es de módulo y no del repositorio porque `ConsultasDeCobranzaPostgres` recorta igual que
    `metricas`: si cada uno tuviera su copia, el gráfico y el encabezado podrían dejar de cuadrar.
    """
    if filtros.desde is not None:
        sentencia = sentencia.where(columna >= filtros.desde)
    if filtros.hasta is not None:
        sentencia = sentencia.where(columna <= filtros.hasta)
    return sentencia


class RepositorioCobroPostgres:
    """Cobros, sobre PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, cobro: Cobro) -> None:
        self._sesion.add(a_fila(cobro, CobroORM()))
        try:
            await self._sesion.flush()
        except IntegrityError as exc:
            # Respaldo del bloqueo consultivo: con el bloqueo, dos altas con la misma clave no
            # compiten. Si el indice saltara igual, es un 409 con texto y no un 500. Solo ese
            # indice, por nombre: cualquier otra violacion sigue siendo un error de verdad.
            if INDICE_CLAVE_DE_COBRO not in str(exc.orig):
                raise
            raise PedidoEnCurso(MENSAJE_PEDIDO_EN_CURSO) from exc

    async def buscar_por_clave_bloqueada(self, clave: UUID) -> Cobro | None:
        """Toma el bloqueo consultivo de `(empresa, clave)` y recien despues lee (ADR-0013).

        El bloqueo es transaccional: lo suelta la unidad de trabajo al terminar (commit o
        rollback), igual que `tomar_con_familia_bloqueada`. Un segundo pedido con la misma clave
        espera aca. Como la lectura es la primera de la sesion sobre esta clave, ve lo que el
        primero dejo confirmado; `populate_existing` por si la sesion ya tuviera la fila.
        """
        empresa = func.current_setting("app.current_empresa", True)
        await self._sesion.execute(
            select(
                func.pg_advisory_xact_lock(
                    ESPACIO_CLAVE_DE_COBRO,
                    func.hashtext(func.concat(empresa, ":", cast(str(clave), String))),
                )
            )
        )
        sentencia = (
            select(CobroORM)
            .where(CobroORM.clave_idempotencia == clave)
            .execution_options(populate_existing=True)
        )
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return a_dominio(fila) if fila is not None else None

    async def guardar(self, cobro: Cobro) -> None:
        fila = await self._sesion.get(CobroORM, cobro.id)
        if fila is None:
            raise LookupError(f"El cobro {cobro.id} no existe para esta empresa")
        a_fila(cobro, fila)
        await self._sesion.flush()

    async def buscar_por_id(self, cobro_id: UUID) -> Cobro | None:
        fila = await self._sesion.get(CobroORM, cobro_id)
        return a_dominio(fila) if fila is not None else None

    async def buscar_para_actualizar(self, cobro_id: UUID) -> Cobro | None:
        """`SELECT ... FOR UPDATE`: el segundo que llega espera y ve el acumulado nuevo.

        `populate_existing` porque la sesion puede tener ya el cobro en su mapa de identidad
        (con un acumulado leido antes del bloqueo): sin refrescarlo, el bloqueo no serviria de
        nada. Todo camino que suma plata carga el cobro por aca.
        """
        sentencia = (
            select(CobroORM)
            .where(CobroORM.id == cobro_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return a_dominio(fila) if fila is not None else None

    async def buscar_por_payment_id(self, payment_id: str) -> Cobro | None:
        """La primera linea de la idempotencia del webhook (D20).

        Una consulta antes de hablar con MercadoPago: si ya procesamos este pago, no hace
        falta una llamada de red para descubrirlo.
        """
        sentencia = select(CobroORM).where(CobroORM.mp_payment_id == payment_id)
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return a_dominio(fila) if fila is not None else None

    async def buscar_por_preference_id(self, preference_id: str) -> Cobro | None:
        sentencia = select(CobroORM).where(CobroORM.mp_preference_id == preference_id)
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return a_dominio(fila) if fila is not None else None

    async def listar(self, filtros: FiltrosDeCobro) -> list[Cobro]:
        sentencia = self._con_filtros(select(CobroORM), filtros)
        # HU-E6-01: «ordenados por antiguedad». El mas viejo primero es lo que alguien que
        # revisa la mora quiere ver arriba.
        sentencia = sentencia.order_by(CobroORM.vence_el.asc(), CobroORM.created_at.asc())
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [a_dominio(fila) for fila in filas]

    async def metricas(self, filtros: FiltrosDeCobro) -> MetricasDeCobros:
        """Las dos bases del encabezado, sumadas **en la base** y en `Decimal` (D91, ADR-0010).

        - Por **fecha de creación**: `pendiente`, `en_mora` y `cobrado_de_lo_creado`.
        - Por **fecha de pago** menos **fecha de devolución**: `cobrado` (HU-E6-05 RN-11).

        Son tres agregaciones porque son tres poblaciones: un cobro creado en febrero y pagado en
        marzo está en la primera al mirar febrero y en la segunda al mirar marzo, y un reembolso
        de abril resta en abril aunque el pago fuera de febrero. `reembolso` se suma sin join
        contra `cobro`: lleva su propia `empresa_id` y su propia fecha. **Puede dar negativo** en
        un período que devolvió más de lo que cobró, y es lo que pasó con la caja.

        `cobrado_de_lo_creado` cuenta los tres estados pagados **por su monto bruto**: un cobro que
        se pagó y después se devolvió *se cobró*, y el reembolso no es una falla de cobranza. Así
        la tasa no pasa de 100 %. `filtros.estados` no interviene: el estado es del listado.
        """
        creados = en_periodo(
            select(CobroORM.estado, func.coalesce(func.sum(CobroORM.monto), CERO)),
            CobroORM.created_at,
            filtros,
        ).group_by(CobroORM.estado)
        totales = {estado: monto for estado, monto in (await self._sesion.execute(creados)).all()}

        pagados = en_periodo(
            select(func.coalesce(func.sum(CobroORM.monto), CERO)).where(
                CobroORM.estado.in_(ESTADOS_PAGADOS)
            ),
            CobroORM.fecha_pago,
            filtros,
        )
        devuelto = en_periodo(
            select(func.coalesce(func.sum(ReembolsoORM.monto), CERO)),
            ReembolsoORM.fecha_devolucion,
            filtros,
        )
        cobrado = (await self._sesion.execute(pagados)).scalar_one()
        restado = (await self._sesion.execute(devuelto)).scalar_one()
        return MetricasDeCobros(
            cobrado=cobrado - restado,
            pendiente=totales.get(EstadoCobro.PENDIENTE.value, CERO),
            en_mora=totales.get(EstadoCobro.VENCIDO.value, CERO),
            cobrado_de_lo_creado=sum((totales.get(e, CERO) for e in ESTADOS_PAGADOS), CERO),
        )

    async def de_comprobante(self, comprobante_id: UUID) -> list[Cobro]:
        sentencia = (
            select(CobroORM)
            .where(CobroORM.comprobante_id == comprobante_id)
            .order_by(CobroORM.created_at)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [a_dominio(fila) for fila in filas]

    async def abiertos_vencidos_a(self, ahora: datetime) -> list[Cobro]:
        sentencia = (
            select(CobroORM)
            .where(CobroORM.estado == EstadoCobro.PENDIENTE.value)
            .where(CobroORM.vence_el <= ahora)
            .order_by(CobroORM.vence_el)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [a_dominio(fila) for fila in filas]

    async def abiertos(self) -> list[Cobro]:
        sentencia = (
            select(CobroORM)
            .where(CobroORM.estado.in_([EstadoCobro.PENDIENTE.value, EstadoCobro.VENCIDO.value]))
            .order_by(CobroORM.vence_el)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [a_dominio(fila) for fila in filas]

    @staticmethod
    def _con_filtros(sentencia: _Sentencia, filtros: FiltrosDeCobro) -> _Sentencia:
        sentencia = en_periodo(sentencia, CobroORM.created_at, filtros)
        if filtros.estados:
            sentencia = sentencia.where(
                CobroORM.estado.in_([estado.value for estado in filtros.estados])
            )
        return sentencia


class RepositorioRecordatoriosPostgres:
    """Recordatorios, sobre PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, recordatorio: Recordatorio) -> None:
        # **El `flush` va en su propio savepoint** (U5, H1b). En PostgreSQL un `IntegrityError`
        # aborta la transacción entera: sin el savepoint, atrapar el duplicado dejaba la sesión
        # inservible y el «no es un error, seguí» del barrido tiraba a todos los cobros que
        # venían después. Con él, sólo se deshace este `INSERT`.
        try:
            async with self._sesion.begin_nested():
                self._sesion.add(
                    RecordatorioORM(
                        id=recordatorio.id,
                        cobro_id=recordatorio.cobro_id,
                        paso=recordatorio.paso,
                        canal=recordatorio.canal,
                        enviado_en=recordatorio.enviado_en,
                        estado_entrega=(
                            recordatorio.estado_entrega.value
                            if recordatorio.estado_entrega
                            else None
                        ),
                        externo_id=recordatorio.externo_id,
                        ultimo_error=recordatorio.ultimo_error,
                    )
                )
                await self._sesion.flush()
        except IntegrityError as exc:
            # El indice unico `(cobro_id, paso)`, no una lectura previa: un «existe? -> no ->
            # insertá» pierde contra dos barridos solapados, que es exactamente el caso que
            # HS-T3 RN-05 describe.
            raise RecordatorioDuplicado(
                f"El paso {recordatorio.paso} del cobro {recordatorio.cobro_id} ya fue enviado"
            ) from exc

    async def guardar(self, recordatorio: Recordatorio) -> None:
        fila = await self._sesion.get(RecordatorioORM, recordatorio.id)
        if fila is None:  # pragma: no cover - siempre se guarda algo recien agregado
            raise LookupError(f"El recordatorio {recordatorio.id} no existe")
        fila.enviado_en = recordatorio.enviado_en
        fila.estado_entrega = (
            recordatorio.estado_entrega.value if recordatorio.estado_entrega else None
        )
        fila.externo_id = recordatorio.externo_id
        fila.ultimo_error = recordatorio.ultimo_error
        await self._sesion.flush()

    async def buscar_por_externo_id(
        self, externo_id: str, *, para_actualizar: bool = False
    ) -> Recordatorio | None:
        """Por el `wamid`. RLS (`aislamiento_por_cobro`) acota a los cobros de la empresa.

        Con `para_actualizar` bloquea solo la fila de `recordatorio` (`FOR UPDATE`): la política
        es `FOR ALL`, así que el bloqueo respeta el mismo `USING` que la lectura.
        """
        sentencia = select(RecordatorioORM).where(RecordatorioORM.externo_id == externo_id)
        if para_actualizar:
            sentencia = sentencia.with_for_update().execution_options(populate_existing=True)
        fila = (await self._sesion.execute(sentencia)).scalars().first()
        return _recordatorio_a_dominio(fila) if fila is not None else None

    async def de_cobro(self, cobro_id: UUID) -> list[Recordatorio]:
        sentencia = (
            select(RecordatorioORM)
            .where(RecordatorioORM.cobro_id == cobro_id)
            .order_by(RecordatorioORM.paso)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_recordatorio_a_dominio(fila) for fila in filas]

    async def de_cobros(self, cobro_ids: list[UUID]) -> dict[UUID, list[Recordatorio]]:
        if not cobro_ids:
            return {}
        sentencia = (
            select(RecordatorioORM)
            .where(RecordatorioORM.cobro_id.in_(cobro_ids))
            .order_by(RecordatorioORM.paso)
        )
        agrupados: dict[UUID, list[Recordatorio]] = {}
        for fila in (await self._sesion.execute(sentencia)).scalars().all():
            agrupados.setdefault(fila.cobro_id, []).append(_recordatorio_a_dominio(fila))
        return agrupados


def _recordatorio_a_dominio(fila: RecordatorioORM) -> Recordatorio:
    return Recordatorio(
        id=fila.id,
        cobro_id=fila.cobro_id,
        paso=fila.paso,
        canal=fila.canal,
        enviado_en=fila.enviado_en,
        estado_entrega=EstadoEntrega(fila.estado_entrega) if fila.estado_entrega else None,
        externo_id=fila.externo_id,
        ultimo_error=fila.ultimo_error,
    )


async def empresas_con_cobros_abiertos(sesion: AsyncSession) -> list[EmpresaId]:
    """Que empresas tienen algo pendiente, para los dos barridos del epico.

    La septima funcion `SECURITY DEFINER` del sistema, y la misma forma que las seis
    anteriores: **devuelve ids y nada mas**. La sesion que se le pasa tiene que ser una
    **sin** empresa (`sesion_sin_empresa`): con una puesta, la politica acotaria al llamador a
    un solo inquilino y el barrido cobraria siempre a la misma empresa.
    """
    filas = await sesion.execute(text("SELECT empresa_id FROM empresas_con_cobros_abiertos()"))
    return [EmpresaId(fila[0]) for fila in filas]


__all__ = [
    "ESTADOS_PAGADOS",
    "RepositorioCobroPostgres",
    "RepositorioRecordatoriosPostgres",
    "empresas_con_cobros_abiertos",
    "en_periodo",
]
