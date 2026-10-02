"""La corrección de datos existentes contra el motor — HU-E4-05 RN-09.

Lo que no se puede probar con un doble, y por eso vive acá:

1. **La misma transacción**: el cambio de nombre y su respaldo se escriben juntos o no se
   escribe ninguno.
2. **Que no se toque `updated_at` ni un comprobante**: la hoja propia decide qué enviar por
   `updated_at`, y RN-09 dice que la corrección no toca comprobantes ni hojas.
3. **El `CHECK NOT VALID` de servicios**, que PostgreSQL exige igual en cada `UPDATE`, y el
   **índice único de categorías**, que es la segunda barrera después del dominio.
4. **El turno por empresa** (`pg_try_advisory_xact_lock`) y **la RLS** de la tabla nueva.

Los datos «viejos» se siembran con SQL directo, porque los agregados ya normalizan y no
dejarían escribir un nombre sin normalizar.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from alembic import command
from cheatsheet.contexts.billing.domain.comprobante import EstadoComprobante
from cheatsheet.contexts.master_data.domain.correccion import (
    Cambio,
    EntidadCorregible,
    MotivoDeOmision,
    planificar_correccion,
)
from cheatsheet.contexts.master_data.infrastructure.correccion import (
    TAMANO_DE_LOTE,
    CorreccionDeNombresPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base
from tests.integracion.test_comprobantes_postgres import _comprobante, _guardar, _punto
from tests.integracion.test_migraciones import _config

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CUIT_DE_EMPRESA = "30712345671"
ANTES = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_CLIENTE = text(
    "INSERT INTO cliente (id, empresa_id, nombre, cuit, origen, presente_en_planilla, activo, "
    "created_at, updated_at) "
    "VALUES (:id, :empresa, :nombre, :cuit, 'PANEL', false, true, :ahora, :ahora)"
)
CREAR_SERVICIO = text(
    "INSERT INTO servicio (id, empresa_id, nombre, precio, alicuota_iva, agendable, "
    "duracion_estandar_min, origen, presente_en_planilla, activo, created_at, updated_at) "
    "VALUES (:id, :empresa, :nombre, 100.00, 0.2100, :agendable, :duracion, 'PANEL', false, "
    "true, :ahora, :ahora)"
)
CREAR_CATEGORIA = text(
    "INSERT INTO categoria_empresa (id, empresa_id, nombre, aplica_a, created_at) "
    "VALUES (:id, :empresa, :nombre, :ambito, :ahora)"
)
QUITAR_REGLA_DE_DURACION = text(
    "ALTER TABLE servicio DROP CONSTRAINT IF EXISTS ck_servicio_duracion_en_rango"
)
PONER_REGLA_DE_DURACION = text(
    "ALTER TABLE servicio ADD CONSTRAINT ck_servicio_duracion_en_rango "
    "CHECK ((agendable AND duracion_estandar_min IS NOT NULL "
    "AND duracion_estandar_min BETWEEN 5 AND 480) "
    "OR (NOT agendable AND duracion_estandar_min IS NULL)) NOT VALID"
)


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


async def _cliente(
    engine_dueno: AsyncEngine, empresa_id: EmpresaId, nombre: str, cuit: str | None = None
) -> uuid.UUID:
    cliente_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            CREAR_CLIENTE,
            {
                "id": cliente_id,
                "empresa": empresa_id,
                "nombre": nombre,
                "cuit": cuit,
                "ahora": ANTES,
            },
        )
    return cliente_id


async def _servicio(
    engine_dueno: AsyncEngine,
    empresa_id: EmpresaId,
    nombre: str,
    *,
    agendable: bool = False,
    duracion: int | None = None,
) -> uuid.UUID:
    servicio_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            CREAR_SERVICIO,
            {
                "id": servicio_id,
                "empresa": empresa_id,
                "nombre": nombre,
                "agendable": agendable,
                "duracion": duracion,
                "ahora": ANTES,
            },
        )
    return servicio_id


async def _categoria(
    engine_dueno: AsyncEngine, empresa_id: EmpresaId, nombre: str, ambito: str = "CLIENTE"
) -> uuid.UUID:
    categoria_id = uuid.uuid4()
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            CREAR_CATEGORIA,
            {
                "id": categoria_id,
                "empresa": empresa_id,
                "nombre": nombre,
                "ambito": ambito,
                "ahora": ANTES,
            },
        )
    return categoria_id


async def _nombre(engine_dueno: AsyncEngine, tabla: str, fila_id: uuid.UUID) -> str:
    consultas = {
        "cliente": text("SELECT nombre FROM cliente WHERE id = :id"),
        "servicio": text("SELECT nombre FROM servicio WHERE id = :id"),
        "categoria": text("SELECT nombre FROM categoria_empresa WHERE id = :id"),
    }
    async with engine_dueno.connect() as conexion:
        return str((await conexion.execute(consultas[tabla], {"id": fila_id})).scalar_one())


async def _respaldos(engine_dueno: AsyncEngine, empresa_id: EmpresaId | None = None) -> int:
    async with engine_dueno.connect() as conexion:
        if empresa_id is None:
            consulta = text("SELECT count(*) FROM respaldo_de_normalizacion")
            return int((await conexion.execute(consulta)).scalar_one())
        consulta = text("SELECT count(*) FROM respaldo_de_normalizacion WHERE empresa_id = :e")
        return int((await conexion.execute(consulta, {"e": empresa_id})).scalar_one())


async def _correr(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
) -> tuple[uuid.UUID, Sequence[Cambio], int]:
    """Read, plan and apply in one transaction, as `AplicarCorreccion` does."""
    corrida_id = uuid.uuid4()
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        puerto = CorreccionDeNombresPostgres(sesion)
        plan = planificar_correccion(await puerto.leer_nombres())
        escritos = await puerto.aplicar(corrida_id, plan.cambios, datetime.now(UTC))
    return corrida_id, escritos, len(plan.omisiones)


async def _restaurar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, corrida_id: uuid.UUID
) -> tuple[int, int]:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        return await CorreccionDeNombresPostgres(sesion).restaurar(corrida_id)


async def _aplicar_y_fallar(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId
) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        puerto = CorreccionDeNombresPostgres(sesion)
        plan = planificar_correccion(await puerto.leer_nombres())
        await puerto.aplicar(uuid.uuid4(), plan.cambios, datetime.now(UTC))
        raise RuntimeError("falla forzada despues del respaldo")


# ----------------------------------------------------------------- 12: la misma transacción


async def test_aplicar_escribe_el_nombre_y_el_respaldo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id, "JUAN PEREZ")
    servicio_id = await _servicio(engine_dueno, empresa_id, "CORTE DE PELO")
    categoria_id = await _categoria(engine_dueno, empresa_id, "VIP  GOLD")

    corrida_id, escritos, _ = await _correr(sesiones, empresa_id)

    assert len(escritos) == 3
    assert await _nombre(engine_dueno, "cliente", cliente_id) == "Juan Perez"
    assert await _nombre(engine_dueno, "servicio", servicio_id) == "Corte de pelo"
    assert await _nombre(engine_dueno, "categoria", categoria_id) == "Vip gold"
    async with engine_dueno.connect() as conexion:
        filas = (
            await conexion.execute(
                text(
                    "SELECT entidad, valor_original, valor_normalizado, campo "
                    "FROM respaldo_de_normalizacion WHERE corrida_id = :c ORDER BY entidad"
                ),
                {"c": corrida_id},
            )
        ).all()
    assert [tuple(f) for f in filas] == [
        ("CATEGORIA", "VIP  GOLD", "Vip gold", "nombre"),
        ("CLIENTE", "JUAN PEREZ", "Juan Perez", "nombre"),
        ("SERVICIO", "CORTE DE PELO", "Corte de pelo", "nombre"),
    ]


async def test_un_fallo_despues_del_respaldo_no_deja_nada(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id, "JUAN PEREZ")

    with pytest.raises(RuntimeError):
        await _aplicar_y_fallar(sesiones, empresa_id)

    assert await _nombre(engine_dueno, "cliente", cliente_id) == "JUAN PEREZ"
    assert await _respaldos(engine_dueno) == 0


async def test_los_lotes_de_quinientos_cubren_mas_de_un_lote(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            text(
                "INSERT INTO cliente (id, empresa_id, nombre, origen, presente_en_planilla, "
                "activo, created_at, updated_at) "
                "SELECT gen_random_uuid(), :e, 'CLIENTE ' || n, 'PANEL', false, true, :a, :a "
                "FROM generate_series(1, :n) AS n"
            ),
            {"e": empresa_id, "n": TAMANO_DE_LOTE + 1, "a": ANTES},
        )

    _, escritos, _ = await _correr(sesiones, empresa_id)

    assert len(escritos) == TAMANO_DE_LOTE + 1
    assert await _respaldos(engine_dueno, empresa_id) == TAMANO_DE_LOTE + 1


# ------------------------------------------------------------------------- 13: idempotente


async def test_aplicar_dos_veces_la_segunda_no_cambia_nada(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    await _cliente(engine_dueno, empresa_id, "JUAN PEREZ")
    await _correr(sesiones, empresa_id)
    antes = await _respaldos(engine_dueno)

    _, escritos, omitidos = await _correr(sesiones, empresa_id)

    assert (len(escritos), omitidos) == (0, 0)
    assert await _respaldos(engine_dueno) == antes


# ------------------------------------------------- 14: ni updated_at ni un comprobante cambian


async def test_no_se_mueve_updated_at_ni_se_toca_un_comprobante(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id, "JUAN PEREZ")
    servicio_id = await _servicio(engine_dueno, empresa_id, "CORTE DE PELO")
    punto = await _punto(sesiones, empresa_id)
    await _guardar(
        sesiones,
        empresa_id,
        _comprobante(empresa_id, cliente_id, punto, numero=1, estado=EstadoComprobante.AUTORIZADO),
    )
    foto = text("SELECT coalesce(string_agg(c::text, '|' ORDER BY c.id), '') FROM comprobante c")
    async with engine_dueno.connect() as conexion:
        comprobantes_antes = (await conexion.execute(foto)).scalar_one()

    await _correr(sesiones, empresa_id)

    async with engine_dueno.connect() as conexion:
        filas = (
            (
                await conexion.execute(
                    text(
                        "SELECT updated_at FROM cliente WHERE id = :c "
                        "UNION ALL SELECT updated_at FROM servicio WHERE id = :s"
                    ),
                    {"c": cliente_id, "s": servicio_id},
                )
            )
            .scalars()
            .all()
        )
        comprobantes_despues = (await conexion.execute(foto)).scalar_one()
    assert filas == [ANTES, ANTES]
    assert comprobantes_antes != ""
    assert comprobantes_despues == comprobantes_antes


# ------------------------------------------------------------ 15: servicio fuera de regla


async def test_un_servicio_con_duracion_fuera_de_regla_se_omite_y_la_transaccion_sigue(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    sano = await _servicio(engine_dueno, empresa_id, "CORTE DE PELO")
    # La restriccion es `NOT VALID` pero protege toda escritura nueva: para sembrar un dato
    # viejo hay que sacarla un momento, y se vuelve a poner pase lo que pase.
    async with engine_dueno.begin() as conexion:
        await conexion.execute(QUITAR_REGLA_DE_DURACION)
    try:
        viejo = await _servicio(
            engine_dueno, empresa_id, "TINTURA COMPLETA", agendable=True, duracion=9999
        )
        _, escritos, omitidos = await _correr(sesiones, empresa_id)
    finally:
        async with engine_dueno.begin() as conexion:
            await conexion.execute(PONER_REGLA_DE_DURACION)

    assert [c.id for c in escritos] == [sano]
    assert omitidos == 1
    assert await _nombre(engine_dueno, "servicio", sano) == "Corte de pelo"
    assert await _nombre(engine_dueno, "servicio", viejo) == "TINTURA COMPLETA"


# ----------------------------------------------------------------------------- 16: restaurar


async def test_restaurar_devuelve_el_original_y_conserva_lo_editado_despues(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    editado = await _cliente(engine_dueno, empresa_id, "JUAN PEREZ")
    intacto = await _cliente(engine_dueno, empresa_id, "ANA GOMEZ")
    categoria = await _categoria(engine_dueno, empresa_id, "VIP  GOLD")
    corrida_id, _, _ = await _correr(sesiones, empresa_id)
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            text("UPDATE cliente SET nombre = 'Juan Perez Editado' WHERE id = :id"),
            {"id": editado},
        )

    restaurados, conservados = await _restaurar(sesiones, empresa_id, corrida_id)

    assert (restaurados, conservados) == (2, 1)
    assert await _nombre(engine_dueno, "cliente", intacto) == "ANA GOMEZ"
    assert await _nombre(engine_dueno, "cliente", editado) == "Juan Perez Editado"
    assert await _nombre(engine_dueno, "categoria", categoria) == "VIP  GOLD"
    segunda = await _restaurar(sesiones, empresa_id, corrida_id)
    assert segunda[0] == 0


async def test_el_respaldo_es_inmutable_para_la_aplicacion(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    await _cliente(engine_dueno, empresa_id, "JUAN PEREZ")
    await _correr(sesiones, empresa_id)

    for sentencia in (
        "UPDATE respaldo_de_normalizacion SET valor_original = 'x'",
        "DELETE FROM respaldo_de_normalizacion",
    ):
        with pytest.raises(ProgrammingError, match=r"permission denied|permiso denegado"):
            async with sesion_de_empresa(sesiones, empresa_id) as sesion:
                await sesion.execute(text(sentencia))
    assert await _respaldos(engine_dueno) == 1


# --------------------------------------------------------------------------- 17: aislamiento


async def test_una_empresa_no_lee_ni_cambia_ni_restaura_lo_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    de_a = await _cliente(engine_dueno, empresa_a, "JUAN PEREZ")
    de_b = await _cliente(engine_dueno, empresa_b, "ANA GOMEZ")

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        vistos = {r.id for r in await CorreccionDeNombresPostgres(sesion).leer_nombres()}
    corrida_a, escritos, _ = await _correr(sesiones, empresa_a)

    assert vistos == {de_a}
    assert [c.id for c in escritos] == [de_a]
    assert await _nombre(engine_dueno, "cliente", de_b) == "ANA GOMEZ"
    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        puerto_b = CorreccionDeNombresPostgres(sesion)
        assert await puerto_b.listar_corridas() == []
        assert await puerto_b.existe_corrida(corrida_a) is False
        assert await puerto_b.restaurar(corrida_a) == (0, 0)
    assert await _nombre(engine_dueno, "cliente", de_a) == "Juan Perez"
    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        corridas = await CorreccionDeNombresPostgres(sesion).listar_corridas()
    assert [(c.corrida_id, c.cantidad) for c in corridas] == [(corrida_a, 1)]


# ---------------------------------------------------------------------------- 18: el turno


async def test_un_segundo_turno_simultaneo_de_la_misma_empresa_no_se_consigue(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    async with sesion_de_empresa(sesiones, empresa_a) as primera:
        assert await CorreccionDeNombresPostgres(primera).tomar_turno() is True
        async with sesion_de_empresa(sesiones, empresa_a) as segunda:
            assert await CorreccionDeNombresPostgres(segunda).tomar_turno() is False
        async with sesion_de_empresa(sesiones, empresa_b) as de_otra:
            assert await CorreccionDeNombresPostgres(de_otra).tomar_turno() is True

    async with sesion_de_empresa(sesiones, empresa_a) as despues:
        assert await CorreccionDeNombresPostgres(despues).tomar_turno() is True


# ------------------------------------------------------------- 19: la colision del indice


async def test_una_colision_que_solo_ve_el_indice_se_omite_y_el_resto_se_aplica(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    await _categoria(engine_dueno, empresa_id, "Vip gold")
    choca = await _categoria(engine_dueno, empresa_id, "Vip  Gold")
    libre = await _categoria(engine_dueno, empresa_id, "OTRA CATEGORIA")
    cambios = [
        Cambio(EntidadCorregible.CATEGORIA, choca, "Vip  Gold", "Vip gold"),
        Cambio(EntidadCorregible.CATEGORIA, libre, "OTRA CATEGORIA", "Otra categoria"),
    ]

    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        escritos = await CorreccionDeNombresPostgres(sesion).aplicar(
            uuid.uuid4(), cambios, datetime.now(UTC)
        )

    assert [c.id for c in escritos] == [libre]
    assert await _nombre(engine_dueno, "categoria", choca) == "Vip  Gold"
    assert await _nombre(engine_dueno, "categoria", libre) == "Otra categoria"
    assert await _respaldos(engine_dueno) == 1


# ------------------------------------------------------------------------ 20: el CUIT no cambia


async def test_el_cuit_guardado_nunca_cambia_y_no_hay_motivo_de_colision_de_cuit(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    empresa_id = await _empresa(engine_dueno)
    cliente_id = await _cliente(engine_dueno, empresa_id, "FERRETERIA LOPEZ SRL", CUIT_DE_EMPRESA)

    await _correr(sesiones, empresa_id)

    async with engine_dueno.connect() as conexion:
        fila = (
            await conexion.execute(
                text("SELECT nombre, cuit FROM cliente WHERE id = :id"), {"id": cliente_id}
            )
        ).one()
    assert (fila.nombre, fila.cuit) == ("Ferreteria Lopez SRL", CUIT_DE_EMPRESA)
    assert {m.value for m in MotivoDeOmision} == {
        "COLISION_DE_CATEGORIA",
        "NOMBRE_INVALIDO",
        "DURACION_FUERA_DE_REGLA",
    }


# ------------------------------------------------------------------------- 22: la migración


async def test_la_migracion_0030_sube_y_baja(
    engine_dueno: AsyncEngine, esquema_migrado: None
) -> None:
    config = _config()
    existe = text("SELECT to_regclass('public.respaldo_de_normalizacion') IS NOT NULL")

    async with engine_dueno.connect() as conexion:
        assert (await conexion.execute(existe)).scalar_one() is True
        privilegios = set(
            (
                await conexion.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name = 'respaldo_de_normalizacion' "
                        "AND grantee = 'cheatsheet_app'"
                    )
                )
            ).scalars()
        )
        flags = (
            await conexion.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname = 'respaldo_de_normalizacion'"
                )
            )
        ).one()
    assert privilegios == {"SELECT", "INSERT"}
    assert tuple(flags) == (True, True)

    await asyncio.to_thread(command.downgrade, config, "0028")
    async with engine_dueno.connect() as conexion:
        assert (await conexion.execute(existe)).scalar_one() is False
    await asyncio.to_thread(command.upgrade, config, "head")
    async with engine_dueno.connect() as conexion:
        assert (await conexion.execute(existe)).scalar_one() is True
