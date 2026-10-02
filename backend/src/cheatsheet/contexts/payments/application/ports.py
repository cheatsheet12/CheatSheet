"""Puertos de `payments`.

Donde cada uno se niega es donde están las garantías.

`PortRepositorioCobro` no tiene `eliminar`: un cobro aprobado es plata que entró, y se
reembolsa. Tiene `buscar_por_payment_id`, que es lo que hace posible la idempotencia del
webhook (decisión **D20**) sin depender de Redis.

`PortPasarelaDePago` es el ACL contra MercadoPago, y el `verificar_firma` que lo precede:
**una notificación cuya firma no valida no llega a este puerto**, se descarta antes (HS-T1
RN-01). Sus cuatro operaciones se dividen en dos clases por cómo tratan un «no» del
proveedor: `reembolsar` lo devuelve como booleano porque un rechazo deja el mundo en un
estado conocido; `invalidar_link` levanta, porque un rechazo deja un link cobrable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
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
    """El encabezado de PAN-COB-01 (HU-E6-01 RN-01, D91).

    Cuatro números sobre el período activo. Los nombres son los de la **pantalla** y no los del
    enum: `cobrado` agrupa `APROBADO` y `en_mora` agrupa `VENCIDO`.

    **Cada número tiene su propia base, y no es la misma** (ADR-0010, punto 6):

    - `cobrado` es lo cobrado **en** el período: suma por *fecha de pago*. Un cobro creado en
      febrero y pagado en marzo suma en marzo.
    - `pendiente` y `en_mora` son de lo **creado** en el período: suma por fecha de creación.
    - `cobrado_de_lo_creado` es la parte de `cobrado` que además se creó en el período. Existe
      solo para que la tasa tenga un numerador que sea subconjunto de su denominador.
    """

    cobrado: Decimal
    pendiente: Decimal
    en_mora: Decimal
    cobrado_de_lo_creado: Decimal

    @property
    def tasa_de_cobro(self) -> Decimal:
        """Lo cobrado de lo creado en el período, sobre lo creado, en porcentaje.

        Se calcula con `cobrado_de_lo_creado` y **no** con `cobrado`: como el numerador está
        incluido en el denominador, **nunca supera 100 %**, por más que el período cobre pagos de
        cobros creados antes. Un pago posterior al cierre del período cuenta en la tasa de ese
        período (cohorte «al día de hoy»).

        Con un total de cero devuelve cero y no rompe: un período sin cobros tiene tasa cero,
        no tasa indefinida, y una pantalla que muestra «—» donde debería ir un número lleva a
        alguien a pensar que el sistema falló.
        """
        total = self.cobrado_de_lo_creado + self.pendiente + self.en_mora
        if total == 0:
            return Decimal("0.00")
        return ((self.cobrado_de_lo_creado / total) * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


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
    #: Cuándo aprobó MercadoPago el pago (`date_approved`), ya en UTC. `None` si el proveedor no
    #: lo informó o no se pudo leer: el dominio entonces usa el momento de la confirmación y
    #: marca la fecha como aproximada.
    fecha_aprobacion: datetime | None = None

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

    async def invalidar_link(
        self, *, empresa_id: EmpresaId, preference_id: str, ahora: datetime
    ) -> None:
        """Deja la preferencia sin poder cobrar (HU-E6-04 RN-03).

        **No devuelve nada, y un rechazo no es una respuesta aceptable.** Es la diferencia con
        `reembolsar`: allá un «no» del proveedor deja el mundo en un estado conocido y el cobro
        mantiene el suyo; acá un «no» deja un link que el cliente todavía puede pagar. Por eso
        cualquier cosa que no sea la confirmación de que murió levanta `PasarelaNoDisponible`,
        y la cancelación entera no ocurre.

        La única excepción es que MercadoPago no conozca la preferencia: no hay nada que
        pagar, así que cuenta como invalidada.
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


class PortClienteDeCobro(Protocol):
    """Lo que `master_data` publica para que un cobro tenga a quien cobrarle (D92).

    Una sola pregunta. `payments` no ve el CUIT ni el contacto del cliente: es un ACL sobre
    el puerto de aplicacion del otro contexto (R3, ADR-0003).
    """

    async def esta_activo(self, cliente_id: UUID) -> bool:
        """`False` cuando no existe, es de otra empresa o esta inactivo.

        Las tres se colapsan a proposito: bajo RLS las dos primeras no se distinguen, y para
        un cobro las tres significan lo mismo: no hay a quien cobrarle.
        """
        ...


class PortSaldoDeComprobante(Protocol):
    """Lo que `billing` publica para que un cobro pueda descontar (HU-E6-06).

    Tres operaciones y ninguna más: cuánto falta, de quién es, y descontá esto. `payments` no
    ve el comprobante ni sus ítems — es un ACL sobre el servicio de aplicación del otro
    contexto (R3, ADR-0003).
    """

    async def saldo_pendiente(self, comprobante_id: UUID) -> Decimal | None:
        """`None` cuando el comprobante no existe o no es de esta empresa."""
        ...

    async def cliente_de(self, comprobante_id: UUID) -> UUID | None:
        """El cliente del comprobante, o `None` si no existe o no es de esta empresa."""
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
    "PortClienteDeCobro",
    "PortEnvioDeRecordatorio",
    "PortPasarelaDePago",
    "PortRepositorioCobro",
    "PortRepositorioRecordatorios",
    "PortSaldoDeComprobante",
]
