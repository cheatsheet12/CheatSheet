"""La reportería contra el motor: aislamiento, el índice del mes y las dos funciones nuevas.

Lo que sólo existe en PostgreSQL, y por eso sólo se puede probar acá:

1. **`uq_paquete_empresa_periodo`** — un mes tiene un paquete. Se prueba **intentando el
   duplicado**, como el épico 5 probó D14 y el 6 probó D20: confiar en que el código no lo
   intente no prueba nada sobre el barrido que corre solo a las tres de la mañana.

2. **`empresa_de_token_contable`** — la función `SECURITY DEFINER` que traduce un enlace de
   correo en un inquilino. Es la puerta del contador externo, y se prueba desde una sesión
   **sin empresa**, que es como corre de verdad.

3. **RLS sobre las cuatro tablas.** Un reporte de otra empresa no se ve, y el mismo id que
   devuelve una fila con una empresa puesta devuelve `None` con otra.

4. **`empresas_con_paquete_activo`** — el barrido mensual. Que sólo traiga las que tienen el
   envío activo **y** un contador cargado es lo que hace que no se arme un paquete que no va a
   ir a ningún lado.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from cheatsheet.contexts.reporting.domain.paquete import (
    ConfiguracionDelPaquete,
    ContenidoDelPaquete,
    PaqueteContable,
    TokenDeAccesoContable,
)
from cheatsheet.contexts.reporting.domain.reporte import (
    FormatoReporte,
    Periodo,
    Reporte,
    TipoReporte,
)
from cheatsheet.contexts.reporting.infrastructure.repositories import (
    RepositorioPaquetePostgres,
    RepositorioReportePostgres,
    RepositorioTokenContablePostgres,
    empresa_de_token_contable,
    empresas_con_paquete_activo,
)
from cheatsheet.platform.database import sesion_de_empresa, sesion_sin_empresa
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 4, 5, 12, 0, tzinfo=UTC)
MARZO = Periodo.del_mes(2026, 3)

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_USUARIO = text(
    "INSERT INTO usuario "
    "(id, empresa_id, email, nombre, rol, estado, pref_idioma, pref_zona_horaria, "
    "pref_suscripciones) "
    "VALUES (:id, :empresa_id, :email, 'Ana Perez', 'ADMINISTRADOR', 'ACTIVO', 'es-AR', "
    "'America/Argentina/Buenos_Aires', '{}'::jsonb)"
)


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


async def _usuario(engine_dueno: AsyncEngine, empresa_id: EmpresaId) -> UsuarioId:
    usuario_id = UsuarioId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            CREAR_USUARIO,
            {
                "id": usuario_id,
                "empresa_id": empresa_id,
                "email": f"{usuario_id}@cheatsheet.ar",
            },
        )
    return usuario_id


def _reporte(empresa_id: EmpresaId, usuario_id: UsuarioId) -> Reporte:
    return Reporte(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        tipo=TipoReporte.FACTURACION,
        formato=FormatoReporte.CSV,
        periodo=MARZO,
        created_at=AHORA,
    )


def _paquete(empresa_id: EmpresaId, *, mes: int = 3) -> PaqueteContable:
    paquete = PaqueteContable(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        periodo_anio=2026,
        periodo_mes=mes,
        created_at=AHORA,
    )
    paquete.registrar_totales(ContenidoDelPaquete.FACTURAS.value, 3, Decimal("12500.55"))
    return paquete


def _token(empresa_id: EmpresaId, paquete_id: uuid.UUID, *, digesto: str) -> TokenDeAccesoContable:
    return TokenDeAccesoContable(
        id=uuid.uuid4(),
        paquete_id=paquete_id,
        empresa_id=empresa_id,
        valor_hash=digesto,
        email_contador="contador@estudio.com.ar",
        vencimiento=AHORA + timedelta(days=30),
        created_at=AHORA,
    )


async def _agregar_token(
    sesiones: async_sessionmaker[AsyncSession],
    empresa_id: EmpresaId,
    token: TokenDeAccesoContable,
) -> None:
    """Guarda un token en su propia transacción, para que el `pytest.raises` mire una sola cosa."""
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioTokenContablePostgres(sesion).agregar(token)


# ------------------------------------------------------------------ ida y vuelta


async def test_un_reporte_sobrevive_entero_a_la_ida_y_vuelta(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    usuario_id = await _usuario(engine_dueno, empresa_id)
    reporte = _reporte(empresa_id, usuario_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioReportePostgres(sesion)
        await repo.agregar(reporte)
        reporte.empezar()
        reporte.completar("reportes/x.csv")
        await repo.guardar(reporte)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioReportePostgres(sesion).buscar_por_id(reporte.id)

    assert leido is not None
    assert leido.periodo == MARZO
    assert leido.es_descargable


async def test_los_importes_del_paquete_vuelven_como_texto(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El JSONB guarda cadenas. Si alguien las convirtiera a número, este test se caería.

    Es el mismo test que `billing` y `payments` tienen sobre sus columnas de dinero, aplicado
    al único lugar del sistema donde un importe vive adentro de un JSON.
    """
    empresa_id = await _empresa(engine_dueno)
    paquete = _paquete(empresa_id)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioPaquetePostgres(sesion).agregar(paquete)

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leido = await RepositorioPaquetePostgres(sesion).buscar_por_id(paquete.id)

    assert leido is not None
    assert leido.totales_por_tipo["FACTURAS"] == {"cantidad": "3", "total": "12500.55"}


# ------------------------------------------------------------------ un mes, un paquete


async def test_dos_paquetes_del_mismo_mes_no_entran(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`uq_paquete_empresa_periodo`, probado intentando el duplicado.

    Es el caso del barrido que corre dos veces: dos procesos de Beat, o un reintento manual
    sobre uno automático. Sin el índice, el contador tendría dos paquetes de marzo con
    contenidos distintos y ninguna forma de saber cuál abrir.
    """
    empresa_id = await _empresa(engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioPaquetePostgres(sesion).agregar(_paquete(empresa_id))

    with pytest.raises(IntegrityError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioPaquetePostgres(sesion).agregar(_paquete(empresa_id))


async def test_otro_mes_si_entra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioPaquetePostgres(sesion)
        await repo.agregar(_paquete(empresa_id, mes=3))
        await repo.agregar(_paquete(empresa_id, mes=2))

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        listados = await RepositorioPaquetePostgres(sesion).listar()

    # Del más nuevo al más viejo: es el orden en que el contador los busca.
    assert [uno.etiqueta for uno in listados] == ["2026-03", "2026-02"]


# ------------------------------------------------------------------ aislamiento


async def test_un_reporte_de_otra_empresa_no_se_ve(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    una = await _empresa(engine_dueno)
    otra = await _empresa(engine_dueno)
    usuario_id = await _usuario(engine_dueno, una)
    reporte = _reporte(una, usuario_id)

    async with sesion_de_empresa(sesiones, una) as sesion:
        await RepositorioReportePostgres(sesion).agregar(reporte)

    async with sesion_de_empresa(sesiones, otra) as sesion:
        assert await RepositorioReportePostgres(sesion).buscar_por_id(reporte.id) is None
        assert await RepositorioReportePostgres(sesion).listar() == []


async def test_el_token_de_otra_empresa_no_se_ve_desde_adentro(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    una = await _empresa(engine_dueno)
    otra = await _empresa(engine_dueno)
    paquete = _paquete(una)
    async with sesion_de_empresa(sesiones, una) as sesion:
        await RepositorioPaquetePostgres(sesion).agregar(paquete)
        await RepositorioTokenContablePostgres(sesion).agregar(
            _token(una, paquete.id, digesto="b" * 64)
        )

    async with sesion_de_empresa(sesiones, otra) as sesion:
        repo = RepositorioTokenContablePostgres(sesion)
        assert await repo.buscar_por_hash("b" * 64) is None
        assert await repo.activo_de_la_empresa() is None


# ------------------------------------------------------------------ la puerta del contador


async def test_la_funcion_traduce_el_enlace_en_una_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`empresa_de_token_contable`, llamada como se llama de verdad: **sin empresa puesta**.

    Es el paso que ocurre antes de que exista un inquilino. Si esta función no corriera fuera
    de RLS, el contador no podría entrar nunca — y si devolviera algo más que un id, sería una
    ventana a los datos de una empresa desde afuera de la sesión.
    """
    empresa_id = await _empresa(engine_dueno)
    paquete = _paquete(empresa_id)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioPaquetePostgres(sesion).agregar(paquete)
        await RepositorioTokenContablePostgres(sesion).agregar(
            _token(empresa_id, paquete.id, digesto="c" * 64)
        )

    async with sesion_sin_empresa(sesiones) as sesion:
        assert await empresa_de_token_contable(sesion, "c" * 64) == empresa_id
        assert await empresa_de_token_contable(sesion, "d" * 64) is None


async def test_un_enlace_revocado_sigue_resolviendo_la_empresa(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Y tiene que ser así: la función no sabe de reglas de negocio.

    Quien decide es el caso de uso, que con el token en la mano puede contestar «el acceso ya
    no está disponible» en vez de «ese enlace no existe» — dos frases que para quien pregunta
    son la misma, pero que del lado de adentro significan cosas distintas.
    """
    empresa_id = await _empresa(engine_dueno)
    paquete = _paquete(empresa_id)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioTokenContablePostgres(sesion)
        await RepositorioPaquetePostgres(sesion).agregar(paquete)
        token = _token(empresa_id, paquete.id, digesto="e" * 64)
        await repo.agregar(token)
        token.revocar()
        await repo.guardar(token)

    async with sesion_sin_empresa(sesiones) as sesion:
        assert await empresa_de_token_contable(sesion, "e" * 64) == empresa_id


async def test_dos_empresas_no_pueden_compartir_digesto(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El único índice del sistema que es global y no por empresa, y por qué tiene que serlo.

    La búsqueda por hash corre antes de saber de qué empresa es el enlace. Dos filas con el
    mismo digesto convertirían esa consulta en una ambigüedad, y el azar elegiría a qué
    empresa dejar entrar.
    """
    una = await _empresa(engine_dueno)
    otra = await _empresa(engine_dueno)
    for empresa_id in (una, otra):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioPaquetePostgres(sesion).agregar(_paquete(empresa_id))

    async with sesion_de_empresa(sesiones, una) as sesion:
        paquete = await RepositorioPaquetePostgres(sesion).del_periodo(2026, 3)
        assert paquete is not None
        await RepositorioTokenContablePostgres(sesion).agregar(
            _token(una, paquete.id, digesto="f" * 64)
        )

    async with sesion_de_empresa(sesiones, otra) as sesion:
        de_la_otra = await RepositorioPaquetePostgres(sesion).del_periodo(2026, 3)
    assert de_la_otra is not None

    with pytest.raises(IntegrityError):
        await _agregar_token(sesiones, otra, _token(otra, de_la_otra.id, digesto="f" * 64))


# ------------------------------------------------------------------ el barrido mensual


async def test_el_barrido_solo_ve_las_que_tienen_el_envio_activo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    activa = await _empresa(engine_dueno)
    apagada = await _empresa(engine_dueno)
    otro_dia = await _empresa(engine_dueno)

    async with sesion_de_empresa(sesiones, activa) as sesion:
        configuracion = ConfiguracionDelPaquete(
            empresa_id=activa,
            dia_de_envio=5,
            email_contador="contador@estudio.com.ar",
            updated_at=AHORA,
        )
        configuracion.activar(AHORA)
        await RepositorioPaquetePostgres(sesion).guardar_configuracion(configuracion)

    async with sesion_de_empresa(sesiones, apagada) as sesion:
        await RepositorioPaquetePostgres(sesion).guardar_configuracion(
            ConfiguracionDelPaquete(empresa_id=apagada, dia_de_envio=5, updated_at=AHORA)
        )

    async with sesion_de_empresa(sesiones, otro_dia) as sesion:
        configuracion = ConfiguracionDelPaquete(
            empresa_id=otro_dia,
            dia_de_envio=20,
            email_contador="otro@estudio.com.ar",
            updated_at=AHORA,
        )
        configuracion.activar(AHORA)
        await RepositorioPaquetePostgres(sesion).guardar_configuracion(configuracion)

    async with sesion_sin_empresa(sesiones) as sesion:
        del_cinco = await empresas_con_paquete_activo(sesion, 5)

    assert del_cinco == [activa]


async def test_la_configuracion_se_reemplaza_y_no_se_duplica(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """`empresa_id` es la clave primaria: una empresa no puede tener dos configuraciones."""
    empresa_id = await _empresa(engine_dueno)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        repo = RepositorioPaquetePostgres(sesion)
        await repo.guardar_configuracion(
            ConfiguracionDelPaquete(empresa_id=empresa_id, dia_de_envio=5, updated_at=AHORA)
        )
        await repo.guardar_configuracion(
            ConfiguracionDelPaquete(
                empresa_id=empresa_id,
                dia_de_envio=12,
                contenido=frozenset({ContenidoDelPaquete.FACTURAS}),
                updated_at=AHORA,
            )
        )

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        leida = await RepositorioPaquetePostgres(sesion).configuracion()

    assert leida is not None
    assert leida.dia_de_envio == 12
    assert leida.contenido == frozenset({ContenidoDelPaquete.FACTURAS})


async def test_la_base_se_niega_a_activar_sin_contador(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La misma invariante que el agregado, en el esquema.

    No es redundancia: el agregado la comprueba para dar el mensaje de la historia, y el
    `CHECK` la comprueba para que ninguna otra vía de escritura —una migración de datos, un
    `psql` a mano— pueda dejar una empresa con el envío activo y sin destinatario.
    """
    empresa_id = await _empresa(engine_dueno)
    with pytest.raises(IntegrityError):
        async with engine_dueno.begin() as conexion:
            await conexion.execute(
                text(
                    "INSERT INTO configuracion_de_paquete "
                    "(empresa_id, activo, dia_de_envio, formatos, contenido, updated_at) "
                    "VALUES (:id, true, 5, '[]'::jsonb, '[]'::jsonb, :ahora)"
                ),
                {"id": empresa_id, "ahora": AHORA},
            )
