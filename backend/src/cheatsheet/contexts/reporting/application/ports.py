"""Puertos de `reporting`.

**Este contexto sólo lee, y sus puertos lo dicen.** Los cuatro ACL hacia los demás contextos
—`PortFacturacion`, `PortCobranzas`, `PortAgendaLeida`, `PortBitacora`— tienen métodos que
devuelven números y filas, y ninguno que cambie nada. Es la propiedad que hace que un bug en el
tablero no pueda emitir un comprobante ni cancelar un turno.

Cada uno pide **exactamente lo que una métrica o un listado necesita**, y nada más. El tablero
de HU-E10-01 no ve comprobantes: ve totales. El reporte de facturación sí ve filas, pero las
que van a un CSV — no el agregado con su CAE y sus ítems.

`PortArchivos` es el mismo almacenamiento que `billing` usa para el PDF de un comprobante,
promovido a `platform/` en el épico 5. Un reporte generado es un archivo, y no hay razón para
que este contexto tenga el suyo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.reporting.domain.paquete import (
    ConfiguracionDelPaquete,
    PaqueteContable,
    TokenDeAccesoContable,
)
from cheatsheet.contexts.reporting.domain.reporte import Periodo, Reporte, TipoReporte
from cheatsheet.shared.empresa import EmpresaId


@dataclass(frozen=True, slots=True)
class TotalesDeFacturacion:
    """Lo que el tablero necesita saber de `billing`, y nada más.

    `por_tipo` es la distribución del primer criterio de HU-E10-01. `por_semana` es el gráfico
    de RN-03: el facturado neto agrupado por semana del período.
    """

    #: El **neto**: lo facturado menos lo anulado por notas de crédito. Es el número del
    #: encabezado del tablero, y el que RN-03 pide graficar por semana.
    total: Decimal
    cantidad: int
    por_tipo: dict[str, Decimal]
    por_semana: dict[str, Decimal]
    #: Las dos mitades del neto, por separado. Existen porque HU-E10-04 RN-03 trata facturas y
    #: notas de crédito como dos contenidos que se activan de a uno, y un paquete que sólo
    #: lleva notas necesita saber cuánto suman **esas**.
    facturas: Decimal = Decimal("0.00")
    notas: Decimal = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class TotalesDeCobranzas:
    cobrado: Decimal
    pendiente: Decimal
    en_mora: Decimal
    #: La que calcula `payments` (RN-08): sólo sobre lo creado en el período, así que no pasa
    #: de 100 %. Se toma tal cual y nunca se recalcula acá.
    tasa_de_cobro: Decimal = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class CobrosPorEstado:
    """Cuántos cobros creados en el período están hoy en un estado, y por cuánto."""

    cantidad: int
    monto: Decimal


@dataclass(frozen=True, slots=True)
class DetalleDeCobranzas:
    """Las dos series de los gráficos de cobranza (RN-07 de HU-E10-01)."""

    #: El cobrado neto por semana ISO (`2026-W09`), por fecha de pago menos lo devuelto.
    por_semana: dict[str, Decimal]
    #: Lo creado en el período por el nombre de su estado actual, en un orden estable.
    por_estado: dict[str, CobrosPorEstado]


@dataclass(frozen=True, slots=True)
class TotalesDeAgenda:
    """«Turnos gestionados» de RN-02: los que existieron en el período, en cualquier estado.

    Gestionados y no completados: un turno cancelado también fue trabajo, y la métrica que la
    historia pide es de actividad, no de resultado.
    """

    gestionados: int
    completados: int
    no_show: int


@dataclass(frozen=True, slots=True)
class FilaDeReporte:
    """Una línea de un listado exportable, ya aplanada.

    Un `dict` ordenado y no un agregado: lo que sale de acá va a un CSV o a un XML, y hacer que
    este contexto conozca `Comprobante` para después aplanarlo sería conocerlo para nada.
    """

    valores: dict[str, str]


class PortFacturacion(Protocol):
    """ACL sobre `billing`. **Sólo lectura.**"""

    async def totales(self, periodo: Periodo) -> TotalesDeFacturacion: ...

    async def filas(
        self, periodo: Periodo, *, solo_notas_de_credito: bool | None = None
    ) -> list[FilaDeReporte]:
        """Los comprobantes del período, aplanados para exportar.

        `solo_notas_de_credito` existe por HU-E10-04 RN-03: el paquete contable lleva
        «facturas» y «notas de crédito» como dos contenidos que se activan por separado, y
        partir una lista mezclada por el valor de una columna de texto sería decidir en la
        capa de aplicación algo que `billing` ya sabe. `None` es «todo», que es lo que pide
        el reporte suelto de HU-E10-03.
        """
        ...


class PortCobranzas(Protocol):
    """ACL sobre `payments`. **Sólo lectura.**"""

    async def totales(self, periodo: Periodo) -> TotalesDeCobranzas: ...

    async def detalle(self, periodo: Periodo) -> DetalleDeCobranzas:
        """Cobrado por semana y cobros por estado, con la misma definición que `totales`."""
        ...

    async def filas(self, periodo: Periodo) -> list[FilaDeReporte]: ...


class PortAgendaLeida(Protocol):
    """ACL sobre `scheduling`. **Sólo lectura.**"""

    async def totales(self, periodo: Periodo) -> TotalesDeAgenda: ...


class PortBitacora(Protocol):
    """ACL sobre `observability`. **Sólo lectura.**

    «Operaciones totales» de RN-02 es cuántas filas de bitácora hubo en el período: es la única
    métrica del tablero que mide *todo* lo que pasó, incluidas las cosas que ningún otro módulo
    cuenta.
    """

    async def cuantas_operaciones(self, periodo: Periodo) -> int: ...

    async def filas(self, periodo: Periodo) -> list[FilaDeReporte]: ...


class PortRepositorioReportes(Protocol):
    """Persistencia de reportes, siempre dentro de una empresa (RLS).

    **Sin `eliminar`.** El historial de HU-E10-03 es lo que contesta «qué le mandé a mi
    contador y cuándo»; borrar una fila es borrar esa respuesta.
    """

    async def agregar(self, reporte: Reporte) -> None: ...

    async def guardar(self, reporte: Reporte) -> None: ...

    async def buscar_por_id(self, reporte_id: UUID) -> Reporte | None: ...

    async def listar(self, *, limite: int = 50) -> list[Reporte]: ...


class PortRepositorioPaquetes(Protocol):
    """Paquetes contables y la configuración de su envío."""

    async def agregar(self, paquete: PaqueteContable) -> None: ...

    async def guardar(self, paquete: PaqueteContable) -> None: ...

    async def buscar_por_id(self, paquete_id: UUID) -> PaqueteContable | None: ...

    async def del_periodo(self, anio: int, mes: int) -> PaqueteContable | None:
        """El paquete de un mes, si ya se armó. **Un mes tiene un paquete.**

        Lo garantiza un índice único; este método existe para poder decirlo antes de intentar,
        y para que el barrido mensual no rehaga lo que ya está.
        """
        ...

    async def listar(self, *, limite: int = 24) -> list[PaqueteContable]: ...

    async def configuracion(self) -> ConfiguracionDelPaquete | None: ...

    async def guardar_configuracion(self, configuracion: ConfiguracionDelPaquete) -> None: ...


class PortRepositorioTokens(Protocol):
    """Los enlaces del contador.

    `buscar_por_hash` **no recibe empresa**: el contador entra sin sesión, así que el token es
    lo único que dice de qué empresa es. Por eso este método corre fuera de RLS, en el
    composition root, con la misma forma que las siete funciones `SECURITY DEFINER` del
    sistema — y por eso devuelve el token y no el paquete: quien decide si el acceso vale es el
    caso de uso, con `esta_vigente`.
    """

    async def agregar(self, token: TokenDeAccesoContable) -> None: ...

    async def guardar(self, token: TokenDeAccesoContable) -> None: ...

    async def activo_de_la_empresa(self) -> TokenDeAccesoContable | None:
        """El enlace vigente de esta empresa, si lo hay (HU-E10-05 RN-04: **uno a la vez**)."""
        ...

    async def buscar_por_hash(self, valor_hash: str) -> TokenDeAccesoContable | None:
        """El token que corresponde a un enlace, **dentro** de la empresa ya resuelta.

        Recibe el hash y nunca el valor en claro: lo que existe en la base es el digesto, y
        una firma que aceptara el valor invitaría a guardarlo «para comparar más rápido».
        """
        ...


class PortTokenDeAcceso(Protocol):
    """Cómo se emite y cómo se resume el enlace del contador.

    Un puerto y no una función suelta porque el caso de uso no puede importar `secrets` sin
    dejar de ser probable: un test necesita saber qué valor salió para después usarlo, y con
    un generador real eso obliga a espiar el mail.

    **No comparte el hasher del épico 1** aunque haga lo mismo. `hashear_token_opaco` vive en
    `identity/infrastructure/`, y este contexto no puede importarlo (R3); promoverlo a
    `platform/` por tres líneas acoplaría dos credenciales que nunca se comparan entre sí.
    """

    def emitir(self) -> str:
        """El valor en claro. Existe una sola vez: se manda por mail y se olvida."""
        ...

    def hashear(self, token: str) -> str: ...


class PortArchivos(Protocol):
    """Dónde queda el archivo generado. El mismo almacenamiento del épico 5."""

    async def guardar(self, *, clave: str, contenido: bytes, tipo: str) -> str: ...

    async def leer(self, clave: str) -> bytes: ...


class PortAvisoAlContador(Protocol):
    """Por dónde sale el mail con el enlace (HU-E10-05 RN-01).

    Es el mismo canal de email que el épico 1 usa para las invitaciones. **El enlace en claro
    pasa por acá una sola vez**: no se guarda, porque lo que se persiste es su hash.
    """

    async def enviar_enlace(
        self, *, email: str, enlace: str, empresa: str, vence: datetime
    ) -> None: ...


class PortEmpresasConPaquete(Protocol):
    """Qué empresas tienen el envío automático activo, para el barrido mensual.

    Corre **fuera de RLS**, como los siete barridos anteriores: la pregunta no es de ninguna
    empresa. Devuelve ids y nada más.
    """

    async def con_envio_activo(self, dia: int) -> Sequence[EmpresaId]: ...


__all__ = [
    "CobrosPorEstado",
    "DetalleDeCobranzas",
    "FilaDeReporte",
    "PortAgendaLeida",
    "PortArchivos",
    "PortAvisoAlContador",
    "PortBitacora",
    "PortCobranzas",
    "PortEmpresasConPaquete",
    "PortFacturacion",
    "PortRepositorioPaquetes",
    "PortRepositorioReportes",
    "PortRepositorioTokens",
    "PortTokenDeAcceso",
    "TipoReporte",
    "TotalesDeAgenda",
    "TotalesDeCobranzas",
    "TotalesDeFacturacion",
]
