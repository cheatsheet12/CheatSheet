"""Puertos de `payments`.

Donde cada uno se niega es donde están las garantías.

`PortRepositorioCobro` no tiene `eliminar`: un cobro aprobado es plata que entró, y se
reembolsa. Tiene `buscar_por_payment_id`, que es lo que hace posible la idempotencia del
webhook (decisión **D20**) sin depender de Redis.

`PortPasarelaDePago` es el ACL contra MercadoPago. Sus tres operaciones son las tres que este
épico necesita, y el `verificar_firma` que las precede: **una notificación cuya firma no
valida no llega a este puerto**, se descarta antes (HS-T1 RN-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.shared.empresa import EmpresaId


@dataclass(frozen=True, slots=True)
class FiltrosDeCobro:
    """HU-E6-01 RN-02. Cada campo opcional; ausente significa «no filtrar por esto».

    Vive en la capa de aplicación y no en `domain/`, por lo que el guarda de arquitectura le
    enseñó al épico 4 cuando atrapó la misma forma: un filtro es un pedido de afuera, no un
    concepto que el agregado conozca.
    """

    desde: datetime | None = None
    hasta: datetime | None = None
    estados: tuple[EstadoCobro, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricasDeCobros:
    """El encabezado de PAN-COB-01 (HU-E6-01 RN-01).

    Cuatro números sobre el período activo. `cobrado` agrupa `APROBADO` y `en_mora` agrupa
    `VENCIDO`, que es lo que la historia dice con todas las letras — y por eso los nombres de
    este DTO son los de la **pantalla** y no los del enum: es lo que se muestra.
    """

    cobrado: Decimal
    pendiente: Decimal
    en_mora: Decimal

    @property
    def tasa_de_cobro(self) -> Decimal:
        """Cobrado sobre el total del período, en porcentaje.

        Con un total de cero devuelve cero y no rompe: un período sin cobros tiene tasa cero,
        no tasa indefinida, y una pantalla que muestra «—» donde debería ir un número lleva a
        alguien a pensar que el sistema falló.
        """
        total = self.cobrado + self.pendiente + self.en_mora
        if total == 0:
            return Decimal("0.00")
        return ((self.cobrado / total) * 100).quantize(Decimal("0.01"))


@dataclass(frozen=True, slots=True)
class PagoRecibido:
    """Lo que una notificación de MercadoPago dice, traducido fuera de su vocabulario.

    `payment_id` es lo que hace idempotente el procesamiento (**D20**), y por eso es lo único
    obligatorio: el resto puede faltar en una notificación parcial, y el sistema tiene que
    poder ir a buscarlo.
    """

    payment_id: str
    preference_id: str | None
    estado: str
    monto: Decimal | None = None

    @property
    def esta_aprobado(self) -> bool:
        """MercadoPago dice `approved`. Cualquier otra cosa **no es un pago confirmado**.

        `pending`, `in_process` y `authorized` llegan por webhook igual que `approved`, y
        tratarlas como pago sería dar por saldada una deuda que todavía puede rechazarse.
        """
        return self.estado.lower() == "approved"


class PortRepositorioCobro(Protocol):
    """Persistencia de cobros, siempre dentro de una empresa (RLS).

    **Sin `eliminar`.** Un cobro aprobado es plata que entró: se reembolsa, no se borra. Uno
    pendiente se cancela, que deja el motivo y el rastro que HU-E6-04 RN-04 pide.
    """

    async def agregar(self, cobro: Cobro) -> None: ...

    async def guardar(self, cobro: Cobro) -> None: ...

    async def buscar_por_id(self, cobro_id: UUID) -> Cobro | None: ...

    async def buscar_por_payment_id(self, payment_id: str) -> Cobro | None:
        """El cobro que ya registró este pago. **La idempotencia del webhook** (D20).

        Devuelve `None` cuando nunca se procesó. Que exista este método y no una clave en
        Redis es lo que hace que la protección sobreviva a un `FLUSHALL` y se pueda verificar
        con una consulta.
        """
        ...

    async def buscar_por_preference_id(self, preference_id: str) -> Cobro | None:
        """El cobro dueño de una preferencia. Cómo el webhook encuentra a quién aprobar.

        MercadoPago manda el `payment_id` y a veces el `preference_id`; el segundo es el que
        nosotros generamos, así que es el que ata la notificación a una fila nuestra.
        """
        ...

    async def listar(self, filtros: FiltrosDeCobro) -> list[Cobro]:
        """Ordenados por antigüedad del vencimiento (HU-E6-01: «en mora por antigüedad»)."""
        ...

    async def metricas(self, filtros: FiltrosDeCobro) -> MetricasDeCobros:
        """Los tres totales del encabezado, sumados **en la base**.

        No en Python sobre `listar`: las métricas son del período entero y el listado se
        pagina, así que sumarlas sobre la página mostraría un total que cambia al pasar de
        hoja.
        """
        ...

    async def de_comprobante(self, comprobante_id: UUID) -> list[Cobro]:
        """Todos los cobros de un comprobante (HU-E6-06 RN-04: pagos parciales)."""
        ...

    async def abiertos_vencidos_a(self, ahora: datetime) -> list[Cobro]:
        """Los que ya pasaron su vencimiento y todavía figuran `PENDIENTE` (D23)."""
        ...

    async def abiertos(self) -> list[Cobro]:
        """Los que siguen esperando plata. Lo que el barrido de recordatorios recorre."""
        ...


class PortRepositorioRecordatorios(Protocol):
    """Los recordatorios de un cobro. Entidad interna: no se consulta sin su padre."""

    async def agregar(self, recordatorio: Recordatorio) -> None:
        """Raises `RecordatorioDuplicado` desde el índice único `(cobro_id, paso)`.

        Es la idempotencia de HS-T3 RN-05, y está en el índice y no en una comprobación
        previa: un «¿existe? → no → insertá» pierde contra dos barridos solapados, que es
        exactamente el caso que la regla describe.
        """
        ...

    async def guardar(self, recordatorio: Recordatorio) -> None: ...

    async def de_cobro(self, cobro_id: UUID) -> list[Recordatorio]: ...

    async def de_cobros(self, cobro_ids: list[UUID]) -> dict[UUID, list[Recordatorio]]:
        """Los de varios cobros de una vez. El barrido recorre todos los abiertos, y una
        consulta por cobro serían N+1 sobre una tabla que crece con cada recordatorio."""
        ...


class PortPasarelaDePago(Protocol):
    """MercadoPago, detrás de un ACL (ADR-0003).

    Las tres operaciones que el épico necesita. **La validación de la firma no está acá**: una
    notificación que no valida se descarta antes de llegar a este puerto (HS-T1 RN-01), y
    ponerla como método sugeriría que es parte del diálogo con el proveedor cuando en realidad
    es la puerta.
    """

    async def crear_link(
        self, *, empresa_id: EmpresaId, cobro: Cobro, url_de_retorno: str
    ) -> LinkDePago:
        """Raises `PasarelaNoDisponible` cuando MercadoPago no responde.

        HU-E6-03 lo pide explícito: si no responde, **el cobro no se crea**. Un cobro sin link
        es una deuda que nadie puede pagar y que igual manda recordatorios.
        """
        ...

    async def consultar_pago(self, *, empresa_id: EmpresaId, payment_id: str) -> PagoRecibido:
        """Qué dice MercadoPago de un pago. El webhook manda un id, no el estado."""
        ...

    async def reembolsar(self, *, empresa_id: EmpresaId, payment_id: str, monto: Decimal) -> bool:
        """`True` si MercadoPago aceptó (HU-E6-05 RN-03). `False` si lo rechazó.

        Un booleano y no una excepción, porque un rechazo **es una respuesta**: el cobro
        mantiene su estado y se avisa al administrador. No poder preguntar es otra cosa, y eso
        sí levanta `PasarelaNoDisponible`.
        """
        ...


class PortEnvioDeRecordatorio(Protocol):
    """Por dónde sale un recordatorio (HS-T3 RN-02).

    Devuelve el estado de entrega que el canal informó, para que RN-04 tenga qué registrar.
    """

    async def enviar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> EstadoEntrega: ...


@dataclass(frozen=True, slots=True)
class PasoDeCadena:
    """Un eslabón de la cadena de escalamiento, en el vocabulario de `payments`.

    **`business_config` tiene su propia clase con la misma forma**, y esa duplicación es la
    correcta: un puerto es el contrato del *consumidor*. La regla R3 impide que este contexto
    importe el dominio del otro, y la traducción vive en el ACL de `infrastructure/` -- que es
    exactamente lo que ADR-0003 pide.

    `dias` se cuenta desde el **vencimiento** del cobro, no desde el paso anterior.
    """

    dias: int
    canal: str


class PortCadenaDeEscalamiento(Protocol):
    """Cuál es la cadena de recordatorios de esta empresa (HU-E11-01 RN-02).

    Devuelve los pasos ya ordenados y ya resueltos por prioridad: la resolución de RN-05 es
    cosa de `business_config`, y este contexto recibe la respuesta, no las filas.

    **Nunca devuelve una lista vacía.** Sin regla configurada devuelve el default, porque
    HS-T3 tiene como precondición que exista una cadena y una empresa que nunca entró a
    PAN-CFG-RN no puede quedarse sin recordatorios y sin enterarse.
    """

    async def pasos(self, *, empresa_id: EmpresaId) -> tuple[PasoDeCadena, ...]: ...


class PortSaldoDeComprobante(Protocol):
    """Lo que `billing` publica para que un cobro pueda descontar (HU-E6-06).

    Dos operaciones y ninguna más: cuánto falta, y descontá esto. `payments` no ve el
    comprobante ni sus ítems — es un ACL sobre el servicio de aplicación del otro contexto
    (R3, ADR-0003).
    """

    async def saldo_pendiente(self, comprobante_id: UUID) -> Decimal | None:
        """`None` cuando el comprobante no existe o no es de esta empresa."""
        ...

    async def registrar_cobro(self, comprobante_id: UUID, monto: Decimal) -> None:
        """Reduce el saldo pendiente (RN-03). **Sólo al aprobarse el cobro** (D26)."""
        ...


__all__ = [
    "FiltrosDeCobro",
    "MetricasDeCobros",
    "PagoRecibido",
    "PasoDeCadena",
    "PortCadenaDeEscalamiento",
    "PortEnvioDeRecordatorio",
    "PortPasarelaDePago",
    "PortRepositorioCobro",
    "PortRepositorioRecordatorios",
    "PortSaldoDeComprobante",
]
