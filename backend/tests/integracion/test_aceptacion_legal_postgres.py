"""`aceptacion_legal` against a real PostgreSQL (HU-E1-03 RN-01/02, HU-E1-08 RN-02/03/04).

Cases 14, 15, 16, 17 and 21 to 23 of the `terminos-y-privacidad` plan. Isolation, the grants
and the partial unique indexes are properties of the engine, so they are checked there; the
API tests then read the table as its owner, without going through the code under test.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.contexts.identity.domain.legal import AceptacionLegal, DocumentoLegal
from cheatsheet.contexts.identity.infrastructure.aceptaciones import (
    RepositorioAceptacionLegalPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.workers import tasks_identity
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base
from tests.integracion.consentimiento import (
    CONSENTIMIENTO,
    VERSION_DE_PRIVACIDAD,
    VERSION_DE_TERMINOS,
)

pytestmark = [requiere_base, pytest.mark.integration]

CONTRASENA = "una-contrasena-larga"
AHORA = datetime(2026, 10, 10, 15, 0, tzinfo=UTC)
PERMISO_DENEGADO = r"permission denied|permiso denegado"


# ------------------------------------------------------------------------------ the table


async def _sembrar_usuario(engine_dueno: AsyncEngine) -> tuple[EmpresaId, UsuarioId]:
    """A company and one user, inserted as the owner (the application role cannot skip RLS)."""
    empresa_id, usuario_id = EmpresaId(uuid.uuid4()), UsuarioId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            text("INSERT INTO empresa (id, activa) VALUES (:id, true)"), {"id": empresa_id}
        )
        await conexion.execute(
            text(
                "INSERT INTO usuario (id, empresa_id, email, nombre, rol, estado, pref_idioma, "
                "pref_zona_horaria, pref_suscripciones) VALUES (:id, :empresa_id, :email, "
                "'Ana', 'ADMINISTRADOR', 'ACTIVO', 'es', 'America/Argentina/Buenos_Aires', "
                "'{}'::jsonb)"
            ),
            {"id": usuario_id, "empresa_id": empresa_id, "email": f"{usuario_id}@empresa.com"},
        )
    return empresa_id, usuario_id


def _aceptacion(
    empresa_id: EmpresaId,
    usuario_id: UsuarioId | None,
    documento: DocumentoLegal = DocumentoLegal.PRIVACIDAD,
    version: str = "1.0",
) -> AceptacionLegal:
    return AceptacionLegal.registrar(
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        documento=documento,
        version=version,
        fecha_aceptacion=AHORA,
    )


async def _guardar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, aceptacion: AceptacionLegal
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioAceptacionLegalPostgres(sesion).agregar(aceptacion)


@pytest.mark.asyncio
async def test_acepto_responde_por_usuario_documento_y_version(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    empresa_id, usuario_id = await _sembrar_usuario(engine_dueno)
    await _guardar(sesiones, empresa_id, _aceptacion(empresa_id, usuario_id))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioAceptacionLegalPostgres(sesion)
        assert await repo.acepto(usuario_id, DocumentoLegal.PRIVACIDAD, "1.0") is True
        assert await repo.acepto(usuario_id, DocumentoLegal.PRIVACIDAD, "2.0") is False
        assert await repo.acepto(usuario_id, DocumentoLegal.TERMINOS, "1.0") is False
        assert await repo.acepto(UsuarioId(uuid.uuid4()), DocumentoLegal.PRIVACIDAD, "1.0") is False


@pytest.mark.asyncio
async def test_una_empresa_no_ve_las_aceptaciones_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    """Case 21 (read side)."""
    empresa_a, usuario_a = await _sembrar_usuario(engine_dueno)
    empresa_b, usuario_b = await _sembrar_usuario(engine_dueno)
    await _guardar(sesiones, empresa_a, _aceptacion(empresa_a, usuario_a))

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        assert (
            await RepositorioAceptacionLegalPostgres(sesion).acepto(
                usuario_a, DocumentoLegal.PRIVACIDAD, "1.0"
            )
            is False
        )
        total = await sesion.execute(text("SELECT count(*) FROM aceptacion_legal"))
        assert total.scalar() == 0
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        total = await sesion.execute(text("SELECT count(*) FROM aceptacion_legal"))
        assert total.scalar() == 1
    assert usuario_b is not None


@pytest.mark.asyncio
async def test_una_empresa_no_puede_insertar_una_aceptacion_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    """Case 21 (write side): the `WITH CHECK` of the policy."""
    empresa_a, usuario_a = await _sembrar_usuario(engine_dueno)
    empresa_b, _ = await _sembrar_usuario(engine_dueno)

    with pytest.raises(DBAPIError, match=r"row-level security|seguridad a nivel de fila"):
        await _guardar(sesiones, empresa_b, _aceptacion(empresa_a, usuario_a))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE aceptacion_legal SET version = '9.9'",
        "DELETE FROM aceptacion_legal",
    ],
)
async def test_el_rol_de_la_aplicacion_no_puede_modificar_ni_borrar(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine, sentencia: str
):
    """Case 22: evidence is insert-only, enforced by the grants and not by Python."""
    empresa_id, usuario_id = await _sembrar_usuario(engine_dueno)
    await _guardar(sesiones, empresa_id, _aceptacion(empresa_id, usuario_id))

    with pytest.raises(ProgrammingError, match=PERMISO_DENEGADO):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(text(sentencia))


async def _insertar_sin_perdon(
    sesiones: async_sessionmaker[AsyncSession], aceptacion: AceptacionLegal
) -> None:
    """A plain `INSERT` (no `ON CONFLICT`): what the partial unique indexes alone enforce."""
    async with sesion_de_empresa(sesiones, aceptacion.empresa_id) as sesion:
        await sesion.execute(
            text(
                "INSERT INTO aceptacion_legal (id, empresa_id, usuario_id, documento, version, "
                "fecha_aceptacion) VALUES (:id, :e, :u, :d, :v, :f)"
            ),
            {
                "id": aceptacion.id,
                "e": aceptacion.empresa_id,
                "u": aceptacion.usuario_id,
                "d": aceptacion.documento.value,
                "v": aceptacion.version,
                "f": aceptacion.fecha_aceptacion,
            },
        )


@pytest.mark.asyncio
async def test_la_misma_version_de_privacidad_dos_veces_para_un_usuario_se_rechaza(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    """Case 23: the partial unique index is the guarantee."""
    empresa_id, usuario_id = await _sembrar_usuario(engine_dueno)
    await _guardar(sesiones, empresa_id, _aceptacion(empresa_id, usuario_id))

    with pytest.raises(IntegrityError, match="uq_aceptacion_legal_privacidad"):
        await _insertar_sin_perdon(sesiones, _aceptacion(empresa_id, usuario_id))

    # A different version of the same document is a new acceptance, not a duplicate.
    await _guardar(sesiones, empresa_id, _aceptacion(empresa_id, usuario_id, version="2.0"))


@pytest.mark.asyncio
async def test_el_repositorio_no_falla_ante_un_duplicado_y_dice_que_no_escribio_nada(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    """Case 29 (race): the second of two requests accepting the same version is not an error.

    `agregar` answers `False` and leaves the single row, so the caller publishes one audit
    event and the request that lost the race still succeeds.
    """
    empresa_id, usuario_id = await _sembrar_usuario(engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioAceptacionLegalPostgres(sesion)
        primera = await repo.agregar(_aceptacion(empresa_id, usuario_id))
        segunda = await repo.agregar(_aceptacion(empresa_id, usuario_id))
        total = await sesion.execute(text("SELECT count(*) FROM aceptacion_legal"))

    assert (primera, segunda) == (True, False)
    assert total.scalar() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("documento", [DocumentoLegal.PRIVACIDAD, DocumentoLegal.TERMINOS])
async def test_el_repositorio_no_traga_un_conflicto_que_no_es_el_del_indice(
    sesiones: async_sessionmaker[AsyncSession],
    engine_dueno: AsyncEngine,
    documento: DocumentoLegal,
):
    """The conflict target is named: a repeated primary key is a bug, not "already accepted"."""
    empresa_id, usuario_id = await _sembrar_usuario(engine_dueno)
    primera = _aceptacion(empresa_id, usuario_id, documento, version="1.0")
    await _guardar(sesiones, empresa_id, primera)

    mismo_id = replace(_aceptacion(empresa_id, usuario_id, documento, "2.0"), id=primera.id)
    with pytest.raises(IntegrityError, match="aceptacion_legal_pkey"):
        await _guardar(sesiones, empresa_id, mismo_id)


@pytest.mark.asyncio
async def test_la_misma_version_de_terminos_dos_veces_para_una_empresa_se_rechaza(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    empresa_id, usuario_id = await _sembrar_usuario(engine_dueno)
    terminos = DocumentoLegal.TERMINOS
    await _guardar(sesiones, empresa_id, _aceptacion(empresa_id, usuario_id, terminos, "1.1"))

    with pytest.raises(IntegrityError, match="uq_aceptacion_legal_terminos"):
        await _insertar_sin_perdon(sesiones, _aceptacion(empresa_id, None, terminos, "1.1"))


@pytest.mark.asyncio
async def test_la_privacidad_sin_usuario_la_rechaza_la_base(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    """`ck_aceptacion_legal_usuario`: only the backfilled terms may have no user."""
    empresa_id, _ = await _sembrar_usuario(engine_dueno)

    with pytest.raises(IntegrityError, match="ck_aceptacion_legal_usuario"):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text(
                    "INSERT INTO aceptacion_legal (id, empresa_id, usuario_id, documento, "
                    "version, fecha_aceptacion) VALUES (gen_random_uuid(), :e, NULL, "
                    "'PRIVACIDAD', '1.0', now())"
                ),
                {"e": empresa_id},
            )


@pytest.mark.asyncio
async def test_los_terminos_sin_usuario_son_validos(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    empresa_id, _ = await _sembrar_usuario(engine_dueno)

    await _guardar(
        sesiones, empresa_id, _aceptacion(empresa_id, None, DocumentoLegal.TERMINOS, "1.1")
    )


@pytest.mark.asyncio
async def test_un_documento_desconocido_lo_rechaza_la_base(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
):
    empresa_id, usuario_id = await _sembrar_usuario(engine_dueno)

    with pytest.raises(IntegrityError, match="ck_aceptacion_legal_documento"):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text(
                    "INSERT INTO aceptacion_legal (id, empresa_id, usuario_id, documento, "
                    "version, fecha_aceptacion) VALUES (gen_random_uuid(), :e, :u, "
                    "'COOKIES', '1.0', now())"
                ),
                {"e": empresa_id, "u": usuario_id},
            )


@pytest.mark.asyncio
async def test_no_se_puede_borrar_un_usuario_con_aceptaciones(
    engine_dueno: AsyncEngine, sesiones: async_sessionmaker[AsyncSession]
):
    """`ON DELETE RESTRICT`: evidence does not disappear with what it points at."""
    empresa_id, usuario_id = await _sembrar_usuario(engine_dueno)
    await _guardar(sesiones, empresa_id, _aceptacion(empresa_id, usuario_id))

    with pytest.raises(IntegrityError, match="aceptacion_legal"):
        async with engine_dueno.begin() as conexion:
            await conexion.execute(text("DELETE FROM usuario WHERE id = :u"), {"u": usuario_id})


# ---------------------------------------------------------------------------- through the API


class DespachadorEspia:
    def __init__(self) -> None:
        self.tareas: list[dict[str, Any]] = []

    def send_task(self, nombre: str, **kwargs: Any) -> None:
        self.tareas.append({"nombre": nombre, **kwargs})


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        database_url_migrations=os.environ["DATABASE_URL_MIGRATIONS"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


@pytest.fixture
def despachador(monkeypatch: pytest.MonkeyPatch) -> DespachadorEspia:
    espia = DespachadorEspia()
    monkeypatch.setattr(tasks_identity, "_despachador", lambda _settings: espia)
    return espia


@pytest_asyncio.fixture
async def cliente(esquema_migrado: None) -> AsyncIterator[httpx.AsyncClient]:
    settings = _settings()
    recursos = Recursos.crear(settings)
    app = create_app(settings, recursos)
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        yield cliente
    await recursos.cerrar()


def _registro(email: str, **cambios: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "email": email,
        "contrasena": CONTRASENA,
        "nombre": "Ana Perez",
        "consentimiento": CONSENTIMIENTO,
    }
    cuerpo.update(cambios)
    return cuerpo


async def _filas(engine: AsyncEngine, consulta: str, **parametros: Any) -> list[Any]:
    async with engine.connect() as conexion:
        return list((await conexion.execute(text(consulta), parametros)).all())


async def _empresas(engine: AsyncEngine) -> int:
    return len(await _filas(engine, "SELECT id FROM empresa"))


@pytest.mark.asyncio
async def test_el_registro_deja_estado_dos_filas_y_dos_eventos(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    """Case 14 against the real database."""
    respuesta = await cliente.post("/auth/registro", json=_registro("ana@empresa.com"))
    assert respuesta.status_code == 201, respuesta.text
    empresa_id = uuid.UUID(respuesta.json()["empresa_id"])
    usuario_id = uuid.UUID(respuesta.json()["usuario_id"])

    empresa = await _filas(
        engine_dueno,
        "SELECT terminos_version, terminos_fecha_aceptacion FROM empresa WHERE id = :e",
        e=empresa_id,
    )
    assert empresa[0].terminos_version == VERSION_DE_TERMINOS
    assert empresa[0].terminos_fecha_aceptacion is not None
    filas = await _filas(
        engine_dueno,
        "SELECT documento, version, usuario_id, empresa_id FROM aceptacion_legal "
        "ORDER BY documento",
    )
    assert [(f.documento, f.version, f.usuario_id, f.empresa_id) for f in filas] == [
        ("PRIVACIDAD", VERSION_DE_PRIVACIDAD, usuario_id, empresa_id),
        ("TERMINOS", VERSION_DE_TERMINOS, usuario_id, empresa_id),
    ]
    eventos = await _filas(
        engine_dueno,
        "SELECT accion, entidad_afectada, usuario_id FROM registro_de_auditoria "
        "WHERE accion LIKE 'aceptar_%' ORDER BY accion",
    )
    assert [(e.accion, e.entidad_afectada, e.usuario_id) for e in eventos] == [
        (
            "aceptar_politica_de_privacidad",
            f"Usuario:{usuario_id} privacidad {VERSION_DE_PRIVACIDAD}",
            usuario_id,
        ),
        ("aceptar_terminos", f"Empresa:{empresa_id} terminos {VERSION_DE_TERMINOS}", usuario_id),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cambios", "estado"),
    [
        ({"consentimiento": None}, 422),
        ({"consentimiento": {"version_privacidad": VERSION_DE_PRIVACIDAD}}, 422),
        ({"consentimiento": {"version_terminos": VERSION_DE_TERMINOS}}, 422),
        (
            {"consentimiento": {**CONSENTIMIENTO, "version_terminos": "0.9"}},
            409,
        ),
        (
            {"consentimiento": {**CONSENTIMIENTO, "version_privacidad": "0.9"}},
            409,
        ),
    ],
    ids=["sin-nada", "sin-terminos", "sin-privacidad", "terminos-viejos", "privacidad-vieja"],
)
async def test_el_registro_sin_consentimiento_valido_no_crea_nada(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine, cambios: dict[str, Any], estado: int
):
    """Cases 12 and 13 against the real database: the transaction leaves nothing behind."""
    respuesta = await cliente.post("/auth/registro", json=_registro("ana@empresa.com", **cambios))

    assert respuesta.status_code == estado, respuesta.text
    assert await _empresas(engine_dueno) == 0
    assert await _filas(engine_dueno, "SELECT id FROM usuario") == []
    assert await _filas(engine_dueno, "SELECT id FROM aceptacion_legal") == []


@pytest.mark.asyncio
async def test_el_registro_sin_la_clave_consentimiento_tambien_es_422(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    cuerpo = _registro("ana@empresa.com")
    del cuerpo["consentimiento"]

    respuesta = await cliente.post("/auth/registro", json=cuerpo)

    assert respuesta.status_code == 422, respuesta.text
    assert "términos y condiciones" in respuesta.text
    assert await _empresas(engine_dueno) == 0


async def _invitar(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia
) -> tuple[str, uuid.UUID]:
    registro = await cliente.post("/auth/registro", json=_registro("ana@empresa.com"))
    cabeceras = {"Authorization": f"Bearer {registro.json()['access_token']}"}
    invitacion = await cliente.post(
        "/usuarios/invitaciones",
        headers=cabeceras,
        json={"email": "beto@empresa.com", "rol": "OPERADOR"},
    )
    assert invitacion.status_code == 201, invitacion.text
    return str(despachador.tareas[-1]["kwargs"]["token"]), uuid.UUID(invitacion.json()["id"])


@pytest.mark.asyncio
async def test_aceptar_una_invitacion_registra_solo_la_privacidad(
    cliente: httpx.AsyncClient, despachador: DespachadorEspia, engine_dueno: AsyncEngine
):
    """Case 17, accepted side."""
    token, _ = await _invitar(cliente, despachador)

    respuesta = await cliente.post(
        "/auth/invitaciones/aceptar",
        json={
            "token": token,
            "nombre": "Beto Gomez",
            "contrasena": CONTRASENA,
            "version_privacidad": VERSION_DE_PRIVACIDAD,
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    beto = uuid.UUID(respuesta.json()["usuario_id"])
    filas = await _filas(
        engine_dueno,
        "SELECT documento, version FROM aceptacion_legal WHERE usuario_id = :u",
        u=beto,
    )
    assert [(f.documento, f.version) for f in filas] == [("PRIVACIDAD", VERSION_DE_PRIVACIDAD)]
    terminos = await _filas(
        engine_dueno, "SELECT id FROM aceptacion_legal WHERE documento = 'TERMINOS'"
    )
    assert len(terminos) == 1, "only the company's, recorded at sign-up"
    evento = await _filas(
        engine_dueno,
        "SELECT entidad_afectada FROM registro_de_auditoria WHERE usuario_id = :u "
        "AND accion = 'aceptar_politica_de_privacidad'",
        u=beto,
    )
    assert [e.entidad_afectada for e in evento] == [
        f"Usuario:{beto} privacidad {VERSION_DE_PRIVACIDAD}"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version", "estado"), [(None, 422), ("0.9", 409)], ids=["sin-version", "version-vieja"]
)
async def test_aceptar_una_invitacion_sin_privacidad_valida_deja_al_usuario_invitado(
    cliente: httpx.AsyncClient,
    despachador: DespachadorEspia,
    engine_dueno: AsyncEngine,
    version: str | None,
    estado: int,
):
    """Case 17, rejected side: the account stays `INVITADO` and no acceptance is recorded."""
    token, _ = await _invitar(cliente, despachador)
    cuerpo: dict[str, Any] = {"token": token, "nombre": "Beto Gomez", "contrasena": CONTRASENA}
    if version is not None:
        cuerpo["version_privacidad"] = version

    respuesta = await cliente.post("/auth/invitaciones/aceptar", json=cuerpo)

    assert respuesta.status_code == estado, respuesta.text
    beto = await _filas(engine_dueno, "SELECT estado FROM usuario WHERE email = 'beto@empresa.com'")
    assert [b.estado for b in beto] == ["INVITADO"]
    assert len(await _filas(engine_dueno, "SELECT id FROM aceptacion_legal")) == 2  # Ana's only


@pytest.mark.asyncio
async def test_google_con_cuenta_nueva_sin_consentimiento_no_crea_la_cuenta(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    """Case 15, rejected side."""
    respuesta = await cliente.post(
        "/auth/google/callback", json={"codigo": "simulado:nueva@empresa.com"}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert await _empresas(engine_dueno) == 0


@pytest.mark.asyncio
async def test_google_con_cuenta_nueva_y_consentimiento_registra_lo_mismo_que_el_email(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    """Case 15, accepted side."""
    respuesta = await cliente.post(
        "/auth/google/callback",
        json={"codigo": "simulado:nueva@empresa.com", "consentimiento": CONSENTIMIENTO},
    )

    assert respuesta.status_code == 201, respuesta.text
    filas = await _filas(
        engine_dueno, "SELECT documento, version FROM aceptacion_legal ORDER BY documento"
    )
    assert [(f.documento, f.version) for f in filas] == [
        ("PRIVACIDAD", VERSION_DE_PRIVACIDAD),
        ("TERMINOS", VERSION_DE_TERMINOS),
    ]


@pytest.mark.asyncio
async def test_google_con_cuenta_existente_inicia_sesion_sin_pedir_consentimiento(
    cliente: httpx.AsyncClient, engine_dueno: AsyncEngine
):
    """Case 16: only a new account owes the consent."""
    primera = await cliente.post(
        "/auth/google/callback",
        json={"codigo": "simulado:ana@empresa.com", "consentimiento": CONSENTIMIENTO},
    )
    assert primera.status_code == 201, primera.text

    segunda = await cliente.post(
        "/auth/google/callback", json={"codigo": "simulado:ana@empresa.com"}
    )

    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["usuario_id"] == primera.json()["usuario_id"]
    assert len(await _filas(engine_dueno, "SELECT id FROM aceptacion_legal")) == 2
