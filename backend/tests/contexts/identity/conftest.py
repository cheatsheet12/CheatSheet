"""In-memory doubles for the identity ports.

Hand-written implementations, not mocks: each one really satisfies its `Protocol`, so
the day a port changes these fail to typecheck instead of happily agreeing with an
interface that no longer exists.

`HasherFalso` is the one that matters for speed. Argon2id is *designed* to be slow — 19
MiB and two passes per call — which is right in production and absurd in a unit test
that only wants to know whether the use case compared the right two things. The real
one is exercised in its own test, once.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.identity.application.ports import PerfilDeGoogle, TokenEmitido
from cheatsheet.contexts.identity.application.sesiones import EmisorDeSesiones
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import (
    Email,
    HashDeContrasena,
    RolUsuario,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import EventoDeDominio

from tests.conftest import INSTANTE_FIJO

#: A structurally valid CUIT: 30-71234567-1, check digit computed with ARCA's weights.
CUIT_VALIDO = "30712345671"
#: Same number with the wrong last digit.
CUIT_INVALIDO = "30712345670"
CONTRASENA = "una-contrasena-larga"


class RepositorioEmpresaEnMemoria:
    def __init__(self) -> None:
        self.empresas: dict[EmpresaId, Empresa] = {}

    async def agregar(self, empresa: Empresa) -> None:
        self.empresas[empresa.id] = empresa

    async def guardar(self, empresa: Empresa) -> None:
        self.empresas[empresa.id] = empresa

    async def buscar_por_id(self, empresa_id: EmpresaId) -> Empresa | None:
        return self.empresas.get(empresa_id)

    async def existe_cuit(self, cuit: str) -> bool:
        return any(e.cuit is not None and e.cuit.valor == cuit for e in self.empresas.values())


class RepositorioUsuarioEnMemoria:
    def __init__(self) -> None:
        self.usuarios: dict[UsuarioId, Usuario] = {}

    async def agregar(self, usuario: Usuario) -> None:
        self.usuarios[usuario.id] = usuario

    async def guardar(self, usuario: Usuario) -> None:
        self.usuarios[usuario.id] = usuario

    async def buscar_por_id(self, usuario_id: UsuarioId) -> Usuario | None:
        return self.usuarios.get(usuario_id)

    async def buscar_por_email(self, email: Email) -> Usuario | None:
        return next((u for u in self.usuarios.values() if u.email == email), None)


class RepositorioRefreshEnMemoria:
    def __init__(self) -> None:
        self.tokens: dict[UUID, RefreshToken] = {}

    async def agregar(self, token: RefreshToken) -> None:
        self.tokens[token.id] = token

    async def guardar(self, token: RefreshToken) -> None:
        self.tokens[token.id] = token

    async def buscar_por_hash(self, hash_del_token: str) -> RefreshToken | None:
        return next((t for t in self.tokens.values() if t.hash_del_token == hash_del_token), None)

    async def revocar_familia(self, familia_id: UUID) -> int:
        afectados = [t for t in self.tokens.values() if t.familia_id == familia_id]
        for token in afectados:
            token.revocar()
        return len(afectados)


class HasherFalso:
    """Reversible on purpose: a test needs to know *what* was hashed."""

    def hashear(self, contrasena: str) -> HashDeContrasena:
        return HashDeContrasena(f"hash::{contrasena}")

    def verificar(self, contrasena: str, hash_guardado: HashDeContrasena) -> bool:
        return hash_guardado.valor == f"hash::{contrasena}"


class EmisorDeTokensFalso:
    """Predictable tokens, so an assertion can name the exact value it expects."""

    def __init__(self) -> None:
        self.emitidos = 0

    def emitir_acceso(
        self, *, usuario_id: UsuarioId, empresa_id: EmpresaId, rol: str, ahora: datetime
    ) -> TokenEmitido:
        return TokenEmitido(
            valor=f"acceso::{empresa_id}::{usuario_id}::{rol}",
            expira_en=ahora + timedelta(minutes=15),
        )

    def emitir_refresh(self, ahora: datetime) -> TokenEmitido:
        self.emitidos += 1
        return TokenEmitido(valor=f"refresh::{self.emitidos}", expira_en=ahora)

    def hashear_refresh(self, token: str) -> str:
        return f"h::{token}"


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


@pytest.fixture
def empresas() -> RepositorioEmpresaEnMemoria:
    return RepositorioEmpresaEnMemoria()


@pytest.fixture
def usuarios() -> RepositorioUsuarioEnMemoria:
    return RepositorioUsuarioEnMemoria()


@pytest.fixture
def refrescos() -> RepositorioRefreshEnMemoria:
    return RepositorioRefreshEnMemoria()


@pytest.fixture
def hasher() -> HasherFalso:
    return HasherFalso()


@pytest.fixture
def tokens() -> EmisorDeTokensFalso:
    return EmisorDeTokensFalso()


@pytest.fixture
def publicador() -> PublicadorFalso:
    return PublicadorFalso()


@pytest.fixture
def emisor(tokens: EmisorDeTokensFalso, refrescos: RepositorioRefreshEnMemoria) -> EmisorDeSesiones:
    return EmisorDeSesiones(tokens=tokens, refrescos=refrescos, vida_refresh=timedelta(days=30))


@pytest.fixture
def perfil_de_google() -> PerfilDeGoogle:
    return PerfilDeGoogle(email=Email("ana@empresa.com"), nombre="Ana Perez")


def usuario_de_prueba(
    empresa_id: EmpresaId, *, activo: bool = True, con_contrasena: bool = True
) -> Usuario:
    return Usuario(
        id=UsuarioId(uuid4()),
        empresa_id=empresa_id,
        email=Email("ana@empresa.com"),
        nombre="Ana Perez",
        rol=RolUsuario.ADMINISTRADOR,
        activo=activo,
        hash_de_contrasena=HashDeContrasena(f"hash::{CONTRASENA}") if con_contrasena else None,
    )


__all__ = [
    "CONTRASENA",
    "CUIT_INVALIDO",
    "CUIT_VALIDO",
    "INSTANTE_FIJO",
    "EmisorDeTokensFalso",
    "HasherFalso",
    "PublicadorFalso",
    "RepositorioEmpresaEnMemoria",
    "RepositorioRefreshEnMemoria",
    "RepositorioUsuarioEnMemoria",
    "usuario_de_prueba",
]
