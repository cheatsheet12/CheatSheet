"""In-memory doubles for the integrations ports.

Hand-written rather than mocked, for the reason `identity`'s conftest gives: each one
really satisfies its `Protocol`, so a port that changes breaks these at typecheck time
instead of leaving them agreeing with an interface that no longer exists.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    PortConectorDeIntegracion,
    PortVerificadorDeConexion,
    ResultadoDeVerificacion,
)
from cheatsheet.contexts.integrations.domain.configuracion import ConfiguracionDeIntegracion
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
    def __init__(self, *, excepcion: Exception | None = None) -> None:
        self.excepcion = excepcion

    async def conectar(self, material: MaterialDeConexion) -> bytes:
        if self.excepcion is not None:
            raise self.excepcion
        return material.contenido


class RegistroFalso:
    def __init__(self, pares: dict[SistemaExterno, ParDeAdaptadores]) -> None:
        self.pares = pares

    def conector(self, sistema: SistemaExterno) -> PortConectorDeIntegracion | None:
        par = self.pares.get(sistema)
        return par.conector if par is not None else None

    def verificador(self, sistema: SistemaExterno) -> PortVerificadorDeConexion | None:
        par = self.pares.get(sistema)
        return par.verificador if par is not None else None


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
