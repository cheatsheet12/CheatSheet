"""Los dobles de `reporting`, escritos a mano.

Como en el resto del sistema: implementaciones de verdad de los puertos y no `Mock`, porque un
`Mock` satisface cualquier interfaz, incluida una que ya no existe. El día que un puerto cambie
de forma, este archivo falla — que es el punto de tener un puerto.

**Los cuatro ACL falsos no calculan nada**: devuelven los números que el test les puso. Lo que
se prueba con ellos es qué hace la reportería con esos números; que los números salgan bien de
`billing`, `payments`, `scheduling` y `observability` se prueba contra el motor, en
`tests/integracion/test_reporteria_postgres.py`.

`ArchivosEnMemoria` puede **fallar a pedido**: es la única forma de probar que un reporte que no
se pudo guardar queda en `FALLIDO` y no desaparece.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from cheatsheet.contexts.reporting.application.ports import (
    FilaDeReporte,
    TotalesDeAgenda,
    TotalesDeCobranzas,
    TotalesDeFacturacion,
)
from cheatsheet.contexts.reporting.domain.paquete import (
    ConfiguracionDelPaquete,
    PaqueteContable,
    TokenDeAccesoContable,
)
from cheatsheet.contexts.reporting.domain.reporte import Periodo, Reporte
from cheatsheet.shared.events import EventoDeDominio

CERO = Decimal("0.00")


class PublicadorEnMemoria:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


class RepositorioReportesEnMemoria:
    def __init__(self, *reportes: Reporte) -> None:
        self.reportes: dict[UUID, Reporte] = {uno.id: uno for uno in reportes}

    async def agregar(self, reporte: Reporte) -> None:
        self.reportes[reporte.id] = reporte

    async def guardar(self, reporte: Reporte) -> None:
        self.reportes[reporte.id] = reporte

    async def buscar_por_id(self, reporte_id: UUID) -> Reporte | None:
        return self.reportes.get(reporte_id)

    async def listar(self, *, limite: int = 50) -> list[Reporte]:
        return list(self.reportes.values())[:limite]


class RepositorioPaquetesEnMemoria:
    def __init__(self, *paquetes: PaqueteContable) -> None:
        self.paquetes: dict[UUID, PaqueteContable] = {uno.id: uno for uno in paquetes}
        self.config: ConfiguracionDelPaquete | None = None

    async def agregar(self, paquete: PaqueteContable) -> None:
        self.paquetes[paquete.id] = paquete

    async def guardar(self, paquete: PaqueteContable) -> None:
        self.paquetes[paquete.id] = paquete

    async def buscar_por_id(self, paquete_id: UUID) -> PaqueteContable | None:
        return self.paquetes.get(paquete_id)

    async def del_periodo(self, anio: int, mes: int) -> PaqueteContable | None:
        for uno in self.paquetes.values():
            if uno.periodo_anio == anio and uno.periodo_mes == mes:
                return uno
        return None

    async def listar(self, *, limite: int = 24) -> list[PaqueteContable]:
        ordenados = sorted(
            self.paquetes.values(),
            key=lambda uno: (uno.periodo_anio, uno.periodo_mes),
            reverse=True,
        )
        return ordenados[:limite]

    async def configuracion(self) -> ConfiguracionDelPaquete | None:
        return self.config

    async def guardar_configuracion(self, configuracion: ConfiguracionDelPaquete) -> None:
        self.config = configuracion


class RepositorioTokensEnMemoria:
    def __init__(self, *tokens: TokenDeAccesoContable) -> None:
        self.tokens: list[TokenDeAccesoContable] = list(tokens)

    async def agregar(self, token: TokenDeAccesoContable) -> None:
        self.tokens.append(token)

    async def guardar(self, token: TokenDeAccesoContable) -> None:
        self.tokens = [token if uno.id == token.id else uno for uno in self.tokens]

    async def activo_de_la_empresa(self) -> TokenDeAccesoContable | None:
        vivos = [uno for uno in self.tokens if not uno.revocado]
        return vivos[-1] if vivos else None

    async def buscar_por_hash(self, valor_hash: str) -> TokenDeAccesoContable | None:
        for uno in self.tokens:
            if uno.valor_hash == valor_hash:
                return uno
        return None


class ArchivosEnMemoria:
    """`PortArchivos` en un dict. Puede fallar a pedido: ver el docstring del módulo."""

    def __init__(self) -> None:
        self.guardados: dict[str, bytes] = {}
        self.falla = False

    async def guardar(self, *, clave: str, contenido: bytes, tipo: str) -> str:
        del tipo
        if self.falla:
            raise RuntimeError("el almacenamiento no responde")
        self.guardados[clave] = contenido
        return clave

    async def leer(self, clave: str) -> bytes:
        return self.guardados[clave]


class FacturacionFalsa:
    def __init__(
        self,
        *,
        totales: TotalesDeFacturacion | None = None,
        filas: list[FilaDeReporte] | None = None,
        notas: list[FilaDeReporte] | None = None,
    ) -> None:
        self.totales_fijos = totales or TotalesDeFacturacion(
            total=CERO, cantidad=0, por_tipo={}, por_semana={}
        )
        self.filas_fijas = filas or []
        self.notas_fijas = notas or []
        self.periodos: list[Periodo] = []

    async def totales(self, periodo: Periodo) -> TotalesDeFacturacion:
        self.periodos.append(periodo)
        return self.totales_fijos

    async def filas(
        self, periodo: Periodo, *, solo_notas_de_credito: bool | None = None
    ) -> list[FilaDeReporte]:
        del periodo
        if solo_notas_de_credito is True:
            return self.notas_fijas
        if solo_notas_de_credito is False:
            return self.filas_fijas
        return [*self.filas_fijas, *self.notas_fijas]


class CobranzasFalsas:
    def __init__(
        self,
        *,
        totales: TotalesDeCobranzas | None = None,
        filas: list[FilaDeReporte] | None = None,
    ) -> None:
        self.totales_fijos = totales or TotalesDeCobranzas(
            cobrado=CERO, pendiente=CERO, en_mora=CERO
        )
        self.filas_fijas = filas or []

    async def totales(self, periodo: Periodo) -> TotalesDeCobranzas:
        del periodo
        return self.totales_fijos

    async def filas(self, periodo: Periodo) -> list[FilaDeReporte]:
        del periodo
        return self.filas_fijas


class AgendaFalsa:
    def __init__(self, *, gestionados: int = 0, completados: int = 0, no_show: int = 0) -> None:
        self.datos = TotalesDeAgenda(
            gestionados=gestionados, completados=completados, no_show=no_show
        )

    async def totales(self, periodo: Periodo) -> TotalesDeAgenda:
        del periodo
        return self.datos


class BitacoraFalsa:
    def __init__(self, *, cuantas: int = 0, filas: list[FilaDeReporte] | None = None) -> None:
        self.cuantas_fijas = cuantas
        self.filas_fijas = filas or []

    async def cuantas_operaciones(self, periodo: Periodo) -> int:
        del periodo
        return self.cuantas_fijas

    async def filas(self, periodo: Periodo) -> list[FilaDeReporte]:
        del periodo
        return self.filas_fijas


class AvisoAlContadorFalso:
    """`PortAvisoAlContador`. Guarda el enlace **para que el test pueda usarlo**, que es lo
    mismo que hace el contador con el mail: es el único lugar donde el valor en claro existe."""

    def __init__(self) -> None:
        self.enviados: list[tuple[str, str]] = []
        self.falla = False

    async def enviar_enlace(
        self, *, email: str, enlace: str, empresa: str, vence: datetime
    ) -> None:
        del empresa, vence
        if self.falla:
            from cheatsheet.contexts.reporting.application.errors import InvitacionNoEnviada

            raise InvitacionNoEnviada("el servidor de correo no responde")
        self.enviados.append((email, enlace))


class EnlaceFijo:
    """`PortTokenDeAcceso` determinista: emite siempre el mismo valor.

    Un generador real obligaría a espiar el mail para saber qué enlace probar; acá el test
    sabe cuál es. El hash sigue siendo un hash de verdad, porque lo que se prueba es que **lo
    que se guarda no es el valor**.
    """

    def __init__(self, valor: str = "enlace-de-prueba") -> None:
        self.valor = valor

    def emitir(self) -> str:
        return self.valor

    def hashear(self, token: str) -> str:
        import hashlib

        return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = [
    "AgendaFalsa",
    "ArchivosEnMemoria",
    "AvisoAlContadorFalso",
    "BitacoraFalsa",
    "CobranzasFalsas",
    "EnlaceFijo",
    "FacturacionFalsa",
    "PublicadorEnMemoria",
    "RepositorioPaquetesEnMemoria",
    "RepositorioReportesEnMemoria",
    "RepositorioTokensEnMemoria",
]
