"""Identity against a real PostgreSQL: isolation, the pre-tenant path, and the race.

Cases 32 to 35 and 37 of the `usuarios-y-preferencias` plan.

**Three of these exist because of a defect the in-memory doubles could not see.** Signing
in, rotating and signing out used to open their transaction with an invented
`EmpresaId(uuid4())` and then write the real one. Row-Level Security rejects that
`INSERT`, and — worse — makes the sign-out `UPDATE` match no rows, so revoking silently
did nothing. Every unit test passed. These do not run against a double.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cheatsheet.contexts.identity.application.errors import UltimoAdministradorActivo
from cheatsheet.contexts.identity.application.invitaciones import (
    AceptarInvitacion,
    InvitarUsuario,
)
from cheatsheet.contexts.identity.application.registro import RegistrarEmpresa
from cheatsheet.contexts.identity.application.sesiones import (
    CerrarSesion,
    EmisorDeSesiones,
    IniciarSesion,
)
from cheatsheet.contexts.identity.application.usuarios import DesactivarUsuario
from cheatsheet.contexts.identity.domain.valores import Email, HashDeContrasena, RolUsuario
from cheatsheet.contexts.identity.infrastructure.repositories import (
    RepositorioEmpresaPostgres,
    RepositorioInvitacionPostgres,
    RepositorioRefreshTokenPostgres,
    RepositorioUsuarioPostgres,
)
from cheatsheet.contexts.identity.infrastructure.resolucion import (
    empresa_de_email,
    empresa_de_invitacion,
    empresa_de_refresh,
)
from cheatsheet.contexts.identity.infrastructure.seguridad import (
    EmisorDeTokensJWT,
    hashear_token_opaco,
)
from cheatsheet.contexts.identity.infrastructure.tokens_invitacion import (
    TokenDeInvitacionAleatorio,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
SECRETO = "fake-secret-for-tests"
VIDA_INVITACION = timedelta(days=7)


class HasherFalso:
    """Argon2id is exercised in its own unit test. Here it would only add seconds."""

    def hashear(self, contrasena: str) -> HashDeContrasena:
        return HashDeContrasena(f"hash::{contrasena}")

    def verificar(self, contrasena: str, hash_guardado: HashDeContrasena) -> bool:
        return hash_guardado.valor == f"hash::{contrasena}"


class PublicadorNulo:
    """The audit sink has its own tests; wiring it here would prove nothing new."""

    async def publicar(self, evento: object) -> None:
        """`evento` is ignored on purpose: this double exists to swallow it."""


def _tokens() -> EmisorDeTokensJWT:
    return EmisorDeTokensJWT(secreto=SECRETO, vida_acceso=timedelta(minutes=15))


def _emisor(sesion: AsyncSession) -> EmisorDeSesiones:
    return EmisorDeSesiones(
        tokens=_tokens(),
        refrescos=RepositorioRefreshTokenPostgres(sesion),
        vida_refresh=timedelta(days=30),
    )


async def _crear_cuenta(
    sesiones: async_sessionmaker[AsyncSession], email: str
) -> tuple[EmpresaId, uuid.UUID]:
    """A company with one active administrator, through the real use case."""
    empresa_id = EmpresaId(uuid.uuid4())
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        registrada = await RegistrarEmpresa(
            empresas=RepositorioEmpresaPostgres(sesion),
            usuarios=RepositorioUsuarioPostgres(sesion),
            hasher=HasherFalso(),
            publicador=PublicadorNulo(),
        ).ejecutar(
            empresa_id=empresa_id,
            email=Email(email),
            contrasena=CONTRASENA,
            nombre="Ana Perez",
            version_terminos="1.0",
            ahora=datetime.now(UTC),
        )
    return empresa_id, registrada.usuario.id


# ------------------------------------------------------- caso 33: el login sí escribe


@pytest.mark.asyncio
async def test_el_login_escribe_su_refresh_token(sesiones: async_sessionmaker[AsyncSession]):
    """The defect, reproduced: the row has to exist after signing in.

    Before the fix this raised, because the transaction announced a company that was not
    the one being written.
    """
    empresa_id, _ = await _crear_cuenta(sesiones, "ana@empresa.com")
    email = Email("ana@empresa.com")

    resuelta = await empresa_de_email(sesiones, email)
    assert resuelta == empresa_id  # the SECURITY DEFINER lookup, before any transaction

    async with sesion_de_empresa(sesiones, resuelta) as sesion:
        sesion_emitida = await IniciarSesion(
            usuarios=RepositorioUsuarioPostgres(sesion),
            hasher=HasherFalso(),
            emisor=_emisor(sesion),
        ).ejecutar(email=email, contrasena=CONTRASENA, ahora=datetime.now(UTC))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        guardado = await RepositorioRefreshTokenPostgres(sesion).buscar_por_hash(
            hashear_token_opaco(sesion_emitida.refresh_token)
        )
    assert guardado is not None
    assert not guardado.revocado


@pytest.mark.asyncio
async def test_el_refresh_token_se_guarda_hasheado(sesiones: async_sessionmaker[AsyncSession]):
    """Whoever reads a dump of this table finds no usable session."""
    empresa_id, _ = await _crear_cuenta(sesiones, "ana@empresa.com")
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        emitida = await IniciarSesion(
            usuarios=RepositorioUsuarioPostgres(sesion),
            hasher=HasherFalso(),
            emisor=_emisor(sesion),
        ).ejecutar(email=Email("ana@empresa.com"), contrasena=CONTRASENA, ahora=datetime.now(UTC))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        guardados = (
            (await sesion.execute(text("SELECT hash_del_token FROM refresh_token"))).scalars().all()
        )
    assert emitida.refresh_token not in guardados
    assert hashear_token_opaco(emitida.refresh_token) in guardados


# ------------------------------------------------------ caso 34: el logout sí revoca


@pytest.mark.asyncio
async def test_el_logout_revoca_de_verdad(sesiones: async_sessionmaker[AsyncSession]):
    """The silent half of the defect: the `UPDATE` matched no rows and reported success."""
    empresa_id, _ = await _crear_cuenta(sesiones, "ana@empresa.com")
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        emitida = await IniciarSesion(
            usuarios=RepositorioUsuarioPostgres(sesion),
            hasher=HasherFalso(),
            emisor=_emisor(sesion),
        ).ejecutar(email=Email("ana@empresa.com"), contrasena=CONTRASENA, ahora=datetime.now(UTC))

    resuelta = await empresa_de_refresh(sesiones, hashear_token_opaco(emitida.refresh_token))
    assert resuelta == empresa_id

    async with sesion_de_empresa(sesiones, resuelta) as sesion:
        await CerrarSesion(
            refrescos=RepositorioRefreshTokenPostgres(sesion), tokens=_tokens()
        ).ejecutar(refresh_token=emitida.refresh_token)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        guardado = await RepositorioRefreshTokenPostgres(sesion).buscar_por_hash(
            hashear_token_opaco(emitida.refresh_token)
        )
    assert guardado is not None
    assert guardado.revocado


# ----------------------------------- casos 32 y 35: la invitación, aislada y sin sesión


async def _invitar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, ejecutor_id, email: str
) -> str:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        emitida = await InvitarUsuario(
            usuarios=RepositorioUsuarioPostgres(sesion),
            invitaciones=RepositorioInvitacionPostgres(sesion),
            tokens=TokenDeInvitacionAleatorio(),
            publicador=PublicadorNulo(),
            vida_invitacion=VIDA_INVITACION,
        ).ejecutar(
            empresa_id=empresa_id,
            ejecutor_id=ejecutor_id,
            rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
            email=Email(email),
            rol=RolUsuario.OPERADOR,
            ahora=datetime.now(UTC),
        )
    return emitida.token_en_claro


@pytest.mark.asyncio
async def test_una_empresa_no_ve_las_invitaciones_de_otra(
    sesiones: async_sessionmaker[AsyncSession],
):
    """Caso 32. Every new table with `empresa_id` earns this test."""
    empresa_a, admin_a = await _crear_cuenta(sesiones, "ana@empresa-a.com")
    empresa_b, admin_b = await _crear_cuenta(sesiones, "beto@empresa-b.com")
    await _invitar(sesiones, empresa_a, admin_a, "nuevo@empresa-a.com")
    await _invitar(sesiones, empresa_b, admin_b, "nuevo@empresa-b.com")

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        pendientes = await RepositorioInvitacionPostgres(sesion).listar_pendientes_de_empresa(
            empresa_a
        )
        total = (await sesion.execute(text("SELECT count(*) FROM invitacion"))).scalar_one()

    assert len(pendientes) == 1
    # Not "one of the two rows is filtered out" — the other one does not exist at all.
    assert total == 1


@pytest.mark.asyncio
async def test_no_se_puede_insertar_una_invitacion_de_otra_empresa(
    sesiones: async_sessionmaker[AsyncSession],
):
    """The `WITH CHECK` half of the policy: reading is filtered, writing is rejected."""
    empresa_a, _ = await _crear_cuenta(sesiones, "ana@empresa-a.com")
    empresa_b, admin_b = await _crear_cuenta(sesiones, "beto@empresa-b.com")

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_a) as sesion:
            await sesion.execute(
                text(
                    "INSERT INTO invitacion "
                    "(id, empresa_id, usuario_id, hash_del_token, expira_en, invitado_por,"
                    " revocada, created_at, updated_at) "
                    "VALUES (:id, :empresa, :usuario, :hash, :vence, :por,"
                    " false, now(), now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "empresa": empresa_b,
                    "usuario": admin_b,
                    "hash": "h::ajeno",
                    "vence": datetime.now(UTC) + VIDA_INVITACION,
                    "por": admin_b,
                },
            )


@pytest.mark.asyncio
async def test_aceptar_una_invitacion_funciona_sin_sesion_previa(
    sesiones: async_sessionmaker[AsyncSession],
):
    """Caso 35. The invited person has no session — the company comes from the token."""
    empresa_id, admin_id = await _crear_cuenta(sesiones, "ana@empresa.com")
    token = await _invitar(sesiones, empresa_id, admin_id, "nuevo@empresa.com")
    adaptador = TokenDeInvitacionAleatorio()

    resuelta = await empresa_de_invitacion(sesiones, adaptador.hashear(token))
    assert resuelta == empresa_id

    async with sesion_de_empresa(sesiones, resuelta) as sesion:
        emitida = await AceptarInvitacion(
            usuarios=RepositorioUsuarioPostgres(sesion),
            invitaciones=RepositorioInvitacionPostgres(sesion),
            tokens=adaptador,
            hasher=HasherFalso(),
            emisor=_emisor(sesion),
            publicador=PublicadorNulo(),
        ).ejecutar(
            token=token,
            nombre="Beto Gomez",
            contrasena=CONTRASENA,
            ahora=datetime.now(UTC),
        )

    assert emitida.access_token
    # And the account is now usable: signing in with it works, under RLS, end to end.
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await IniciarSesion(
            usuarios=RepositorioUsuarioPostgres(sesion),
            hasher=HasherFalso(),
            emisor=_emisor(sesion),
        ).ejecutar(email=Email("nuevo@empresa.com"), contrasena=CONTRASENA, ahora=datetime.now(UTC))


@pytest.mark.asyncio
async def test_el_token_de_invitacion_no_queda_en_claro_en_la_base(
    sesiones: async_sessionmaker[AsyncSession],
):
    """Caso 26 at the level that matters: the row itself."""
    empresa_id, admin_id = await _crear_cuenta(sesiones, "ana@empresa.com")
    token = await _invitar(sesiones, empresa_id, admin_id, "nuevo@empresa.com")

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        guardados = (
            (await sesion.execute(text("SELECT hash_del_token FROM invitacion"))).scalars().all()
        )

    assert token not in guardados
    assert TokenDeInvitacionAleatorio().hashear(token) in guardados


# --------------------------------------------- caso 37: la carrera del último admin


@pytest.mark.asyncio
async def test_la_carrera_del_ultimo_administrador_la_gana_uno_solo(
    sesiones: async_sessionmaker[AsyncSession],
):
    """Two administrators deactivating each other at the same instant.

    Without the row lock both read a count of 2, both proceed, and the company ends up
    with none. The lock is what makes the second transaction re-read a count that already
    includes the first one's change.
    """
    empresa_id, primero = await _crear_cuenta(sesiones, "ana@empresa.com")
    segundo_token = await _invitar(sesiones, empresa_id, primero, "beto@empresa.com")
    adaptador = TokenDeInvitacionAleatorio()
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await AceptarInvitacion(
            usuarios=RepositorioUsuarioPostgres(sesion),
            invitaciones=RepositorioInvitacionPostgres(sesion),
            tokens=adaptador,
            hasher=HasherFalso(),
            emisor=_emisor(sesion),
            publicador=PublicadorNulo(),
        ).ejecutar(
            token=segundo_token,
            nombre="Beto Gomez",
            contrasena=CONTRASENA,
            ahora=datetime.now(UTC),
        )
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        usuarios = RepositorioUsuarioPostgres(sesion)
        beto = await usuarios.buscar_por_email(Email("beto@empresa.com"))
        assert beto is not None
        beto.cambiar_rol(RolUsuario.ADMINISTRADOR)
        await usuarios.guardar(beto)

    async def desactivar(objetivo) -> str:
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await DesactivarUsuario(
                empresas=RepositorioEmpresaPostgres(sesion),
                usuarios=RepositorioUsuarioPostgres(sesion),
                refrescos=RepositorioRefreshTokenPostgres(sesion),
                publicador=PublicadorNulo(),
            ).ejecutar(
                empresa_id=empresa_id,
                ejecutor_id=objetivo,
                rol_del_ejecutor=RolUsuario.ADMINISTRADOR,
                usuario_id=objetivo,
                ahora=datetime.now(UTC),
            )
        return "ok"

    resultados = await asyncio.gather(
        desactivar(primero), desactivar(beto.id), return_exceptions=True
    )

    fallidos = [r for r in resultados if isinstance(r, UltimoAdministradorActivo)]
    assert len(fallidos) == 1, resultados

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        vivos = await RepositorioUsuarioPostgres(sesion).contar_administradores_activos(empresa_id)
    assert vivos == 1
