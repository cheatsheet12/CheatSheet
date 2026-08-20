"""In-memory doubles for the integrations ports.

Hand-written rather than mocked, for the reason `identity`'s conftest gives: each one
really satisfies its `Protocol`, so a port that changes breaks these at typecheck time
instead of leaving them agreeing with an interface that no longer exists.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.ports import (
    DatosDePadron,
    MaterialDeConexion,
    PedidoDeAutorizacion,
    PortAutorizacionOAuth,
    PortConectorDeIntegracion,
    PortConsultaDePadron,
    PortEmisorDeTickets,
    PortRenovacionDeCredencial,
    PortVerificadorDeConexion,
    ResultadoDeConexion,
    ResultadoDeVerificacion,
    TicketEmitido,
)
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
from cheatsheet.contexts.integrations.domain.ticket import ServicioDeArca, TicketDeAcceso
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    CredencialCifrada,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.registro import ParDeAdaptadores
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import EventoDeDominio

from tests.conftest import INSTANTE_FIJO

ALGORITMO_FALSO = "FALSO/v1"


class RepositorioIntegracionesEnMemoria:
    def __init__(self) -> None:
        self.filas: dict[tuple[EmpresaId, SistemaExterno], ConfiguracionDeIntegracion] = {}

    async def agregar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        self.filas[(configuracion.empresa_id, configuracion.sistema)] = configuracion

    async def guardar(self, configuracion: ConfiguracionDeIntegracion) -> None:
        self.filas[(configuracion.empresa_id, configuracion.sistema)] = configuracion

    async def buscar(
        self, empresa_id: EmpresaId, sistema: SistemaExterno
    ) -> ConfiguracionDeIntegracion | None:
        return self.filas.get((empresa_id, sistema))

    async def listar(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]:
        return [c for (e, _), c in self.filas.items() if e == empresa_id]

    async def listar_pendientes(self, empresa_id: EmpresaId) -> list[ConfiguracionDeIntegracion]:
        return [c for c in await self.listar(empresa_id) if c.esta_pendiente]


class CifradoFalso:
    """Reversible, not secure. The real AES-GCM adapter has its own test."""

    def cifrar(self, plano: bytes) -> CredencialCifrada:
        return CredencialCifrada(contenido=b"cifrado:" + plano, algoritmo=ALGORITMO_FALSO)

    def descifrar(self, credencial: CredencialCifrada) -> bytes:
        return credencial.contenido.removeprefix(b"cifrado:")


class VerificadorProgramado:
    """Answers whatever the test told it to, including by hanging or raising."""

    def __init__(
        self,
        *,
        resultado: ResultadoDeVerificacion | None = None,
        demora: float | None = None,
        excepcion: Exception | None = None,
    ) -> None:
        self.resultado = resultado or ResultadoDeVerificacion(EstadoDeConexion.CONECTADO)
        self.demora = demora
        self.excepcion = excepcion
        self.llamadas = 0

    async def verificar(
        self,
        credencial: bytes,  # noqa: ARG002 — a programmed double ignores both
        parametros: dict[str, Any],  # noqa: ARG002
    ) -> ResultadoDeVerificacion:
        self.llamadas += 1
        if self.demora is not None:
            await asyncio.sleep(self.demora)
        if self.excepcion is not None:
            raise self.excepcion
        return self.resultado


class ConectorProgramado:
    def __init__(
        self,
        *,
        excepcion: Exception | None = None,
        estado: EstadoDeConexion = EstadoDeConexion.CONECTADO,
        detalle: str | None = None,
        parametros: dict[str, Any] | None = None,
    ) -> None:
        self.excepcion = excepcion
        self.estado = estado
        self.detalle = detalle
        self.parametros = parametros or {}
        self.recibidos = 0
        #: Lo que llegó por `efimeros`. Se guarda acá para poder afirmar que el verificador
        #: de PKCE llegó al adaptador **y** que no terminó en los parámetros persistidos.
        self.efimeros_recibidos: dict[str, str] = {}

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        self.recibidos += 1
        self.efimeros_recibidos = dict(material.efimeros)
        if self.excepcion is not None:
            raise self.excepcion
        return ResultadoDeConexion(
            credencial=material.contenido,
            estado=self.estado,
            detalle=self.detalle,
            parametros=self.parametros,
        )


class AutorizacionProgramada:
    """Builds a URL that says what it was asked for, so a test can read it back."""

    def __init__(self, base: str = "https://proveedor.invalid/authorize") -> None:
        self.base = base
        self.pedidos: list[PedidoDeAutorizacion] = []

    def url_de_autorizacion(self, pedido: PedidoDeAutorizacion) -> str:
        self.pedidos.append(pedido)
        return f"{self.base}?state={pedido.estado}&code_challenge={pedido.desafio}"


class RenovadorProgramado:
    """Answers with a fresh credential, or with whatever the test told it to raise."""

    def __init__(
        self,
        *,
        credencial: bytes = b"acceso-nuevo\nrefresco-nuevo",
        estado: EstadoDeConexion = EstadoDeConexion.CONECTADO,
        detalle: str | None = None,
        parametros: dict[str, Any] | None = None,
        excepcion: Exception | None = None,
    ) -> None:
        self.credencial = credencial
        self.estado = estado
        self.detalle = detalle
        self.parametros = parametros or {}
        self.excepcion = excepcion
        self.llamadas = 0
        self.recibida: bytes | None = None

    async def renovar(self, credencial: bytes) -> ResultadoDeConexion:
        self.llamadas += 1
        self.recibida = credencial
        if self.excepcion is not None:
            raise self.excepcion
        return ResultadoDeConexion(
            credencial=self.credencial,
            estado=self.estado,
            detalle=self.detalle,
            parametros=self.parametros,
        )


class RegistroFalso:
    def __init__(self, pares: dict[SistemaExterno, ParDeAdaptadores]) -> None:
        self.pares = pares

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None:
        par = self.pares.get(sistema)
        return par.conector if par is not None else None

    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None:
        par = self.pares.get(sistema)
        return par.verificador if par is not None else None

    def emisor_de_tickets(self, sistema: SistemaExterno) -> PortEmisorDeTickets | None:
        par = self.pares.get(sistema)
        return par.emisor if par is not None else None

    def consulta_de_padron(self, sistema: SistemaExterno) -> PortConsultaDePadron | None:
        par = self.pares.get(sistema)
        return par.padron if par is not None else None

    def autorizacion(self, sistema: SistemaExterno) -> PortAutorizacionOAuth | None:
        par = self.pares.get(sistema)
        return par.autorizacion if par is not None else None

    def renovador(self, sistema: SistemaExterno) -> PortRenovacionDeCredencial | None:
        par = self.pares.get(sistema)
        return par.renovador if par is not None else None


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


def configuracion_conectada(
    empresa_id: EmpresaId,
    sistema: SistemaExterno,
    *,
    estado: EstadoDeConexion = EstadoDeConexion.CONECTADO,
    parametros: dict[str, Any] | None = None,
) -> ConfiguracionDeIntegracion:
    return ConfiguracionDeIntegracion(
        id=uuid4(),
        empresa_id=empresa_id,
        sistema=sistema,
        credencial=CredencialCifrada(contenido=b"cifrado:secreto", algoritmo=ALGORITMO_FALSO),
        ambiente=Ambiente.HOMOLOGACION,
        estado=estado,
        detalle_estado=None,
        verificado_en=INSTANTE_FIJO,
        parametros=dict(parametros or {}),
    )


@pytest.fixture
def integraciones() -> RepositorioIntegracionesEnMemoria:
    return RepositorioIntegracionesEnMemoria()


@pytest.fixture
def cifrado() -> CifradoFalso:
    return CifradoFalso()


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


@pytest.fixture
def empresa_id() -> EmpresaId:
    return EmpresaId(uuid4())


class RepositorioTicketsEnMemoria:
    """Implements `PortRepositorioTickets`."""

    def __init__(self) -> None:
        self.filas: dict[tuple[EmpresaId, ServicioDeArca], TicketDeAcceso] = {}

    async def agregar(self, ticket: TicketDeAcceso) -> None:
        self.filas[(ticket.empresa_id, ticket.servicio)] = ticket

    async def guardar(self, ticket: TicketDeAcceso) -> None:
        self.filas[(ticket.empresa_id, ticket.servicio)] = ticket

    async def buscar(
        self, empresa_id: EmpresaId, servicio: ServicioDeArca
    ) -> TicketDeAcceso | None:
        return self.filas.get((empresa_id, servicio))


class EmisorProgramado:
    """Implements `PortEmisorDeTickets`. Cuenta las llamadas, que es medio test por sí solo."""

    def __init__(
        self,
        *,
        expira_en: datetime | None = None,
        excepcion: Exception | None = None,
        contenido: bytes = b"token\nfirma",
    ) -> None:
        self.expira_en = expira_en or (INSTANTE_FIJO + timedelta(hours=12))
        self.excepcion = excepcion
        self.contenido = contenido
        self.llamadas = 0

    async def emitir(self, credencial: bytes, servicio: ServicioDeArca) -> TicketEmitido:
        del credencial
        self.llamadas += 1
        if self.excepcion is not None:
            raise self.excepcion
        return TicketEmitido(servicio=servicio, contenido=self.contenido, expira_en=self.expira_en)


class PadronProgramado:
    """Implements `PortConsultaDePadron`. Guarda con qué lo llamaron.

    Que registre `ticket` y `parametros` no es curiosidad: el CUIT que ARCA exige saber es
    el **del certificado**, y confundirlo con el consultado es un error que devolvería los
    datos de la empresa equivocada.
    """

    def __init__(
        self,
        *,
        datos: DatosDePadron | None = None,
        excepcion: Exception | None = None,
    ) -> None:
        self.datos = datos
        self.excepcion = excepcion
        self.llamadas = 0
        self.ultimo_ticket: bytes | None = None
        self.ultimos_parametros: Mapping[str, Any] | None = None
        self.ultimo_cuit: str | None = None

    async def consultar(
        self, *, ticket: bytes, parametros: Mapping[str, Any], cuit: str
    ) -> DatosDePadron | None:
        self.llamadas += 1
        self.ultimo_ticket = ticket
        self.ultimos_parametros = parametros
        self.ultimo_cuit = cuit
        if self.excepcion is not None:
            raise self.excepcion
        return self.datos
