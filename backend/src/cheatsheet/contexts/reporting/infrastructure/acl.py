"""Los cuatro ACL de `reporting`, en el vocabulario del tablero.

**Los cuatro son de sólo lectura, y eso es la garantía del épico.** Ninguno tiene un método
que emita, cobre, reserve ni cancele: un bug en el tablero no puede tocar un comprobante
porque desde acá no hay cómo. Lo que se importa de los otros contextos son sus **casos de uso
de consulta** y sus filtros —nunca su `domain/` ni su `infrastructure/` (regla R3)— y lo que
devuelven se lee por atributo, sin nombrar sus tipos, igual que `SaldoViaBilling` del épico 6.

Cada uno pide exactamente lo que una métrica o un listado necesita:

- `FacturacionViaBilling` cuenta **sólo lo autorizado**. Un borrador no facturó nada y un
  rechazado tampoco; sumarlos daría un tablero que no coincide con lo que ARCA registró, que
  es el único número contra el que alguien lo va a comparar.
- `CobranzasViaPayments` reusa `MetricasDelPeriodo`, que es el mismo cálculo que ve PAN-COB-01.
  Recalcularlo acá haría que dos pantallas del sistema dieran cifras distintas del mismo mes.
  Su `detalle` (cobrado por semana y cobros por estado) sale de la misma definición.
- `AgendaViaSchedulingLeida` cuenta **turnos gestionados**: los que existieron en el período,
  en cualquier estado. Un turno cancelado también fue trabajo.
- `BitacoraViaObservability` cuenta operaciones con `contar`, que no las trae. Un mes de una
  empresa activa son decenas de miles de filas, y traerlas para medirlas sería trabajo hecho
  para tirar.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from cheatsheet.contexts.billing.application.consultas import ListarComprobantes
from cheatsheet.contexts.billing.application.ports import (
    EstadoComprobante,
    FiltrosDeComprobante,
    PortRepositorioComprobante,
)
from cheatsheet.contexts.observability.application.consultas import (
    ContarOperaciones,
    ListarOperaciones,
)
from cheatsheet.contexts.observability.application.ports import (
    FiltrosDeBitacora,
    PortRegistroDeAuditoria,
)
from cheatsheet.contexts.payments.application.cobranza_del_periodo import (
    DetalleDeCobranzaDelPeriodo,
    PortConsultasDeCobranza,
)
from cheatsheet.contexts.payments.application.cobros import ListarCobros, MetricasDelPeriodo
from cheatsheet.contexts.payments.application.ports import FiltrosDeCobro, PortRepositorioCobro
from cheatsheet.contexts.reporting.application.ports import (
    CobrosPorEstado,
    DetalleDeCobranzas,
    FilaDeReporte,
    TotalesDeAgenda,
    TotalesDeCobranzas,
    TotalesDeFacturacion,
)
from cheatsheet.contexts.reporting.domain.reporte import Periodo
from cheatsheet.contexts.scheduling.application.ports import FiltrosDeAgenda, PortRepositorioTurno
from cheatsheet.contexts.scheduling.application.turnos import VerAgenda

CERO = Decimal("0.00")

#: La zona en la que se recortan los períodos.
#:
#: La misma que usa la agenda, y por el mismo motivo: un comprobante emitido a las 22 de un
#: 31 de marzo es de marzo para quien lo emitió, aunque en UTC ya sea abril. Un reporte mensual
#: que corta en UTC le corre el cierre a todas las empresas del país.
ZONA_DEL_REPORTE = ZoneInfo("America/Argentina/Buenos_Aires")

#: Cuántas filas trae como mucho un listado exportable.
#:
#: Un tope y no «todo»: el mes de una empresa grande puede tener miles de comprobantes, y un
#: reporte sin techo es la consulta que tumba el proceso. Está anotado en los pendientes: el
#: día que un mes real lo alcance, esto se convierte en generación por lotes.
TOPE_DE_FILAS = 5000


def _limites(periodo: Periodo) -> tuple[datetime, datetime]:
    """El período como dos instantes, en la zona del reporte.

    El cierre es el **final** del último día y no su medianoche: un cobro de las 18 del último
    día del mes es de ese mes, y cortar en `00:00` lo dejaría afuera sin que nadie lo note
    hasta que el total no cierre.
    """
    desde = datetime.combine(periodo.desde, time.min, tzinfo=ZONA_DEL_REPORTE)
    hasta = datetime.combine(periodo.hasta, time.max, tzinfo=ZONA_DEL_REPORTE)
    return desde, hasta


def _autorizados(periodo: Periodo) -> FiltrosDeComprobante:
    """El filtro que trae los comprobantes con CAE del período.

    El estado se filtra en la consulta y no en memoria: un mes con miles de borradores no
    tiene por qué viajar entero hasta este proceso para que se descarte casi todo.

    Devuelve el filtro en vez de los comprobantes, y no es un rodeo: el tipo que `billing`
    devuelve vive en su `domain/`, y una función que lo anunciara tendría que importarlo —
    que es exactamente lo que R3 prohíbe. Llamando al caso de uso en el lugar donde se usa el
    resultado, el tipo se infiere y nadie lo nombra.
    """
    return FiltrosDeComprobante(
        desde=periodo.desde, hasta=periodo.hasta, estados=(EstadoComprobante.AUTORIZADO,)
    )


def _semana_de(momento: datetime) -> str:
    """La etiqueta de la semana ISO, `2026-W09`. Lo que agrupa el gráfico de RN-03."""
    anio, semana, _ = momento.astimezone(ZONA_DEL_REPORTE).isocalendar()
    return f"{anio}-W{semana:02d}"


def _semana_del_dia(dia: date) -> str:
    """La misma etiqueta que `_semana_de`, para un día que ya es local (el de la fecha de pago)."""
    anio, semana, _ = dia.isocalendar()
    return f"{anio}-W{semana:02d}"


class FacturacionViaBilling:
    """`PortFacturacion`. **Sólo lectura**, y sólo comprobantes autorizados."""

    def __init__(self, comprobantes: PortRepositorioComprobante) -> None:
        self._comprobantes = comprobantes

    async def totales(self, periodo: Periodo) -> TotalesDeFacturacion:
        emitidos = await ListarComprobantes(self._comprobantes).ejecutar(_autorizados(periodo))
        por_tipo: dict[str, Decimal] = {}
        por_semana: dict[str, Decimal] = {}
        facturas = CERO
        notas = CERO

        for uno in emitidos:
            tipo = uno.tipo.value
            por_tipo[tipo] = por_tipo.get(tipo, CERO) + uno.total
            momento = uno.fecha_emision or uno.created_at
            semana = _semana_de(momento)
            # Una nota de crédito **resta** en el gráfico semanal y en el neto: es lo que
            # significa anular, y sumarla mostraría que un mes de devoluciones fue un mes
            # récord.
            firmado = -uno.total if uno.tipo.es_nota_de_credito else uno.total
            por_semana[semana] = por_semana.get(semana, CERO) + firmado
            if uno.tipo.es_nota_de_credito:
                notas += uno.total
            else:
                facturas += uno.total

        return TotalesDeFacturacion(
            total=facturas - notas,
            cantidad=len(emitidos),
            por_tipo=por_tipo,
            por_semana=dict(sorted(por_semana.items())),
            facturas=facturas,
            notas=notas,
        )

    async def filas(
        self, periodo: Periodo, *, solo_notas_de_credito: bool | None = None
    ) -> list[FilaDeReporte]:
        emitidos = await ListarComprobantes(self._comprobantes).ejecutar(_autorizados(periodo))
        if solo_notas_de_credito is not None:
            emitidos = [
                uno for uno in emitidos if uno.tipo.es_nota_de_credito is solo_notas_de_credito
            ]
        return [
            FilaDeReporte(
                {
                    "fecha": f"{(uno.fecha_emision or uno.created_at):%d/%m/%Y}",
                    "tipo": uno.tipo.value,
                    "numero": str(uno.numero or ""),
                    "cuit": uno.receptor.cuit,
                    "razon_social": uno.receptor.nombre,
                    "neto": str(uno.subtotal),
                    "iva": str(uno.total_iva),
                    # Los importes salen como **texto**, con el punto decimal, tal como los
                    # guarda el `Decimal`. Formatearlos con coma acá los volvería números en
                    # una planilla en inglés y texto en una en español.
                    "total": str(uno.total),
                    "cae": uno.cae.codigo if uno.cae is not None else "",
                }
            )
            for uno in emitidos[:TOPE_DE_FILAS]
        ]


class CobranzasViaPayments:
    """`PortCobranzas`. **Sólo lectura.** Reusa las métricas que ve PAN-COB-01."""

    def __init__(self, cobros: PortRepositorioCobro, consultas: PortConsultasDeCobranza) -> None:
        self._cobros = cobros
        self._consultas = consultas

    async def totales(self, periodo: Periodo) -> TotalesDeCobranzas:
        desde, hasta = _limites(periodo)
        metricas = await MetricasDelPeriodo(self._cobros).ejecutar(
            ahora=hasta, filtros=FiltrosDeCobro(desde=desde, hasta=hasta)
        )
        return TotalesDeCobranzas(
            cobrado=metricas.cobrado,
            pendiente=metricas.pendiente,
            en_mora=metricas.en_mora,
            # La tasa es de `payments`: la calcula sobre lo creado en el período para que no
            # pase de 100 %, y recalcularla acá con el `cobrado` rompería esa garantía.
            tasa_de_cobro=metricas.tasa_de_cobro,
        )

    async def detalle(self, periodo: Periodo) -> DetalleDeCobranzas:
        """Cobrado por semana y cobros por estado, con la definición de `totales`."""
        desde, hasta = _limites(periodo)
        detalle = await DetalleDeCobranzaDelPeriodo(self._consultas).ejecutar(
            filtros=FiltrosDeCobro(desde=desde, hasta=hasta), zona=ZONA_DEL_REPORTE
        )
        por_semana: dict[str, Decimal] = {}
        for dia, monto in detalle.cobrado_por_dia.items():
            semana = _semana_del_dia(dia)
            por_semana[semana] = por_semana.get(semana, CERO) + monto
        return DetalleDeCobranzas(
            por_semana=dict(sorted(por_semana.items())),
            # Por atributo (`.value`, `.cantidad`, `.monto`): el tipo de `payments` no se nombra.
            por_estado={
                estado.value: CobrosPorEstado(cantidad=uno.cantidad, monto=uno.monto)
                for estado, uno in detalle.por_estado.items()
            },
        )

    async def filas(self, periodo: Periodo) -> list[FilaDeReporte]:
        desde, hasta = _limites(periodo)
        cobros = await ListarCobros(self._cobros).ejecutar(FiltrosDeCobro(desde=desde, hasta=hasta))
        return [
            FilaDeReporte(
                {
                    "fecha": f"{uno.created_at:%d/%m/%Y}",
                    "descripcion": uno.descripcion,
                    "monto": str(uno.monto),
                    "estado": uno.estado.value,
                    "vence": f"{uno.vence_el:%d/%m/%Y}",
                    "pagado": f"{uno.fecha_pago:%d/%m/%Y}" if uno.fecha_pago else "",
                }
            )
            for uno in cobros[:TOPE_DE_FILAS]
        ]


class AgendaViaSchedulingLeida:
    """`PortAgendaLeida`. **Sólo lectura**, y sin una sola operación que cambie un turno.

    Es el mismo contexto que el ACL del épico 8 alcanza para reservar y cancelar, y esta clase
    es deliberadamente otra: la que reporta no necesita poder reservar, y darle esa capacidad
    «porque ya está» es cómo un módulo de lectura termina con permisos de escritura.
    """

    def __init__(self, turnos: PortRepositorioTurno) -> None:
        self._turnos = turnos

    async def totales(self, periodo: Periodo) -> TotalesDeAgenda:
        desde, hasta = _limites(periodo)
        turnos = await VerAgenda(self._turnos).ejecutar(FiltrosDeAgenda(desde=desde, hasta=hasta))
        estados = [uno.estado.value for uno in turnos]
        return TotalesDeAgenda(
            gestionados=len(estados),
            completados=estados.count("COMPLETADO"),
            no_show=estados.count("NO_SHOW"),
        )


class BitacoraViaObservability:
    """`PortBitacora`. **Sólo lectura** sobre el registro de auditoría."""

    def __init__(self, registros: PortRegistroDeAuditoria) -> None:
        self._registros = registros

    async def cuantas_operaciones(self, periodo: Periodo) -> int:
        desde, hasta = _limites(periodo)
        return await ContarOperaciones(self._registros).ejecutar(
            FiltrosDeBitacora(desde=desde, hasta=hasta)
        )

    async def filas(self, periodo: Periodo) -> list[FilaDeReporte]:
        desde, hasta = _limites(periodo)
        registros = await ListarOperaciones(self._registros).ejecutar(
            FiltrosDeBitacora(desde=desde, hasta=hasta, limite=TOPE_DE_FILAS)
        )
        return [
            FilaDeReporte(
                {
                    "fecha": f"{uno.timestamp.astimezone(ZONA_DEL_REPORTE):%d/%m/%Y %H:%M}",
                    "modulo": uno.modulo.value,
                    "accion": uno.accion,
                    "entidad": uno.entidad_afectada,
                    "resultado": uno.resultado.value,
                    # Quién lo inició, no quién es: el log de operaciones va adentro del
                    # paquete que se le manda a un contador, y el id de un usuario no le dice
                    # nada a nadie de afuera.
                    "iniciador": uno.iniciador.value,
                }
            )
            for uno in registros
        ]


__all__ = [
    "TOPE_DE_FILAS",
    "ZONA_DEL_REPORTE",
    "AgendaViaSchedulingLeida",
    "BitacoraViaObservability",
    "CobranzasViaPayments",
    "FacturacionViaBilling",
]
