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

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.identity.application.ports import (
    EstadoActualDelUsuario,
    MensajeDeInvitacion,
    PerfilDeGoogle,
    TokenEmitido,
)
from cheatsheet.contexts.identity.application.sesiones import EmisorDeSesiones
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.invitacion import Invitacion
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import (
    Email,
    EstadoUsuario,
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
        #: Which companies were locked, so a test can assert the serialisation happened
        #: without needing a real database to prove it.
        self.bloqueadas: list[EmpresaId] = []

    async def agregar(self, empresa: Empresa) -> None:
        self.empresas[empresa.id] = empresa

    async def guardar(self, empresa: Empresa) -> None:
        self.empresas[empresa.id] = empresa

    async def buscar_por_id(self, empresa_id: EmpresaId) -> Empresa | None:
        return self.empresas.get(empresa_id)

    async def existe_cuit(self, cuit: str) -> bool:
        return any(e.cuit is not None and e.cuit.valor == cuit for e in self.empresas.values())

    async def bloquear(self, empresa_id: EmpresaId) -> None:
        self.bloqueadas.append(empresa_id)


class RepositorioUsuarioEnMemoria:
    def __init__(self) -> None:
        self.usuarios: dict[UsuarioId, Usuario] = {}

    async def agregar(self, usuario: Usuario) -> None:
        self.usuarios[usuario.id] = usuario

    async def guardar(self, usuario: Usuario) -> None:
        self.usuarios[usuario.id] = usuario

    async def eliminar(self, usuario_id: UsuarioId) -> None:
        self.usuarios.pop(usuario_id, None)

    async def buscar_por_id(self, usuario_id: UsuarioId) -> Usuario | None:
        return self.usuarios.get(usuario_id)

    async def buscar_por_email(self, email: Email) -> Usuario | None:
        return next((u for u in self.usuarios.values() if u.email == email), None)

    async def listar_de_empresa(self, empresa_id: EmpresaId) -> Sequence[Usuario]:
        return [u for u in self.usuarios.values() if u.empresa_id == empresa_id]

    async def contar_administradores_activos(self, empresa_id: EmpresaId) -> int:
        return sum(
            1
            for u in self.usuarios.values()
            if u.empresa_id == empresa_id and u.es_administrador_activo
        )


class ConsultaDeUsuarioVigenteEnMemoria:
    """What the database would answer for the per-request session check.

    A missing key stands for "no row": a deleted user, or one that Row-Level Security hides
    because it belongs to another company.
    """

    def __init__(self) -> None:
        self.estados: dict[UsuarioId, EstadoActualDelUsuario] = {}
        self.consultas = 0

    def registrar(self, usuario: Usuario) -> None:
        self.estados[usuario.id] = EstadoActualDelUsuario(
            empresa_id=usuario.empresa_id, rol=usuario.rol, estado=usuario.estado
        )

    async def estado_actual(self, usuario_id: UsuarioId) -> EstadoActualDelUsuario | None:
        self.consultas += 1
        return self.estados.get(usuario_id)


class RepositorioInvitacionEnMemoria:
    def __init__(self) -> None:
        self.invitaciones: dict[UUID, Invitacion] = {}

    async def agregar(self, invitacion: Invitacion) -> None:
        self.invitaciones[invitacion.id] = invitacion

    async def guardar(self, invitacion: Invitacion) -> None:
        self.invitaciones[invitacion.id] = invitacion

    async def buscar_por_id(self, invitacion_id: UUID) -> Invitacion | None:
        return self.invitaciones.get(invitacion_id)

    async def buscar_por_hash(self, hash_del_token: str) -> Invitacion | None:
        return next(
            (i for i in self.invitaciones.values() if i.hash_del_token == hash_del_token), None
        )

    async def listar_pendientes_de_empresa(self, empresa_id: EmpresaId) -> Sequence[Invitacion]:
        return [
            i for i in self.invitaciones.values() if i.empresa_id == empresa_id and i.esta_pendiente
        ]


class RepositorioRefreshEnMemoria:
    def __init__(self) -> None:
        self.tokens: dict[UUID, RefreshToken] = {}

    async def agregar(self, token: RefreshToken) -> None:
        self.tokens[token.id] = token

    async def guardar(self, token: RefreshToken) -> None:
        self.tokens[token.id] = token

    async def buscar_por_hash(self, hash_del_token: str) -> RefreshToken | None:
        return next((t for t in self.tokens.values() if t.hash_del_token == hash_del_token), None)

    async def tomar_con_familia_bloqueada(self, hash_del_token: str) -> RefreshToken | None:
        # Same lookup as `buscar_por_hash`, inlined so a spy on one never sees the other.
        return next((t for t in self.tokens.values() if t.hash_del_token == hash_del_token), None)

    async def revocar_familia(self, familia_id: UUID) -> int:
        afectados = [t for t in self.tokens.values() if t.familia_id == familia_id]
        for token in afectados:
            token.revocar()
        return len(afectados)

    async def revocar_de_usuario(self, usuario_id: UsuarioId) -> int:
        afectados = [
            t for t in self.tokens.values() if t.usuario_id == usuario_id and not t.revocado
        ]
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


class TokenDeInvitacionFalso:
    """Sequential and reversible, for the same reason as `EmisorDeTokensFalso`."""

    def __init__(self) -> None:
        self.emitidos = 0

    def emitir(self) -> str:
        self.emitidos += 1
        return f"invitacion::{self.emitidos}"

    def hashear(self, token: str) -> str:
        return f"h::{token}"


class EnviadorDeEmailFalso:
    """Records what would have been sent. Opens no socket, like every double here."""

    def __init__(self, *, falla: bool = False) -> None:
        self.enviados: list[MensajeDeInvitacion] = []
        self.falla = falla

    async def enviar_invitacion(self, mensaje: MensajeDeInvitacion) -> None:
        if self.falla:
            from cheatsheet.contexts.identity.application.errors import EnvioDeEmailFallido

            raise EnvioDeEmailFallido("El servidor de correo no respondio")
        self.enviados.append(mensaje)


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
def invitaciones() -> RepositorioInvitacionEnMemoria:
    return RepositorioInvitacionEnMemoria()


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
def tokens_de_invitacion() -> TokenDeInvitacionFalso:
    return TokenDeInvitacionFalso()


@pytest.fixture
def enviador() -> EnviadorDeEmailFalso:
    return EnviadorDeEmailFalso()


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
    empresa_id: EmpresaId,
    *,
    estado: EstadoUsuario = EstadoUsuario.ACTIVO,
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
    email: str = "ana@empresa.com",
    nombre: str = "Ana Perez",
    con_contrasena: bool = True,
) -> Usuario:
    return Usuario(
        id=UsuarioId(uuid4()),
        empresa_id=empresa_id,
        email=Email(email),
        nombre=nombre,
        rol=rol,
        estado=estado,
        hash_de_contrasena=HashDeContrasena(f"hash::{CONTRASENA}") if con_contrasena else None,
    )


__all__ = [
    "CONTRASENA",
    "CUIT_INVALIDO",
    "CUIT_VALIDO",
    "INSTANTE_FIJO",
    "ConsultaDeUsuarioVigenteEnMemoria",
    "EmisorDeTokensFalso",
    "EnviadorDeEmailFalso",
    "HasherFalso",
    "PublicadorFalso",
    "RepositorioEmpresaEnMemoria",
    "RepositorioInvitacionEnMemoria",
    "RepositorioRefreshEnMemoria",
    "RepositorioUsuarioEnMemoria",
    "TokenDeInvitacionFalso",
    "usuario_de_prueba",
]
