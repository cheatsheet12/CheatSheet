"""La DLQ contra el motor que la hace cumplir (HS-T6).

Cuatro cosas de esta unidad no se pueden probar con un doble, y son las cuatro que
importan si algún día salen mal:

1. **El aislamiento entre empresas.** Es una política de PostgreSQL. Un doble que filtra
   por `empresa_id` en Python probaría el doble, no la barrera.
2. **Que no haya `DELETE`.** El `GRANT` de la migración 0011 no lo incluye, a propósito:
   HS-T6 RN-04 guarda las tareas agotadas para analizarlas y eventualmente reprocesarlas.
3. **La función `empresas_con_tareas_fallidas()`**, que es `SECURITY DEFINER` y por lo
   tanto atraviesa RLS. Que devuelva **sólo ids**, y de todas las empresas, es su razón de
   ser y también su riesgo.
4. **El CHECK sobre `estado`.** La migración se apartó del enum del DER a propósito; lo
   que sostiene el catálogo cerrado del lado del motor es esa restricción.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.observability.domain.tarea_asincrona import EstadoTarea, TareaAsincrona
from cheatsheet.contexts.observability.infrastructure.tareas_repository import (
    RepositorioTareaAsincrona,
    empresas_con_tareas_fallidas,
)
from cheatsheet.platform.database import sesion_de_empresa, sesion_sin_empresa
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    """La fila de `empresa` que exige la FK, creada con el rol dueño."""
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


def _tarea(empresa_id: EmpresaId, *, sufijo: str = "1") -> TareaAsincrona:
    ahora = datetime.now(UTC)
    return TareaAsincrona(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        tipo="spreadsheet_sync.procesar_planilla",
        payload={"archivo": f"planilla-{sufijo}.xlsx"},
        clave_idempotencia=ClaveDeIdempotencia.de(
            empresa_id=empresa_id, tipo="procesar", payload={"n": sufijo}
        ),
        created_at=ahora,
        updated_at=ahora,
    )


async def _guardar_fallida(
    sesiones: async_sessionmaker[AsyncSession], empresa_id: EmpresaId, *, sufijo: str = "1"
) -> TareaAsincrona:
    tarea = _tarea(empresa_id, sufijo=sufijo)
    tarea.marcar_en_curso(ahora=tarea.created_at)
    tarea.marcar_fallida(motivo="timeout", ahora=tarea.created_at)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioTareaAsincrona(sesion).agregar(tarea)
    return tarea


async def test_una_empresa_no_ve_las_tareas_de_otra(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Caso 7 del plan. La barrera es de PostgreSQL, no de la aplicación."""
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    tarea = await _guardar_fallida(sesiones, empresa_a)

    async with sesion_de_empresa(sesiones, empresa_b) as sesion:
        assert await RepositorioTareaAsincrona(sesion).buscar_por_id(tarea.id) is None
        assert await RepositorioTareaAsincrona(sesion).listar_fallidas(limite=10) == []

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        recuperada = await RepositorioTareaAsincrona(sesion).buscar_por_id(tarea.id)
    assert recuperada is not None
    assert recuperada.estado is EstadoTarea.FALLIDA


async def test_la_misma_clave_en_dos_empresas_convive(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La unicidad es por empresa, no global.

    Dos empresas corren legítimamente el mismo trabajo sobre el mismo payload; una
    restricción global haría de la segunda un duplicado de la primera.
    """
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)

    clave = ClaveDeIdempotencia("misma:clave:para:las:dos")
    for empresa_id in (empresa_a, empresa_b):
        tarea = _tarea(empresa_id)
        tarea.clave_idempotencia = clave
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await RepositorioTareaAsincrona(sesion).agregar(tarea)

    async with sesion_de_empresa(sesiones, empresa_a) as sesion:
        assert await RepositorioTareaAsincrona(sesion).buscar_por_clave(clave) is not None


async def test_la_misma_clave_dos_veces_en_una_empresa_es_rechazada(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """ADR-009: una clave identifica un efecto, y el índice único es lo que lo garantiza."""
    empresa_id = await _empresa(engine_dueno)
    clave = ClaveDeIdempotencia("una:sola:vez")

    for _ in range(2):
        tarea = _tarea(empresa_id)
        tarea.clave_idempotencia = clave
        try:
            async with sesion_de_empresa(sesiones, empresa_id) as sesion:
                await RepositorioTareaAsincrona(sesion).agregar(tarea)
        except IntegrityError:
            return

    pytest.fail("La segunda tarea con la misma clave tendria que haber sido rechazada")


async def test_no_se_puede_borrar_una_tarea(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """RN-04: lo que se derivó a la DLQ se guarda para analizarlo, no se limpia.

    El rol de la aplicación no tiene `DELETE` sobre esta tabla. Es el mismo argumento que
    protege la bitácora, llegado desde otra regla.
    """
    empresa_id = await _empresa(engine_dueno)
    tarea = await _guardar_fallida(sesiones, empresa_id)

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("DELETE FROM tarea_asincrona WHERE id = :id"), {"id": tarea.id}
            )


async def test_un_estado_fuera_del_catalogo_es_rechazado(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El CHECK de la migración 0011, que reemplaza al enum del DER."""
    empresa_id = await _empresa(engine_dueno)
    tarea = await _guardar_fallida(sesiones, empresa_id)

    with pytest.raises((IntegrityError, DBAPIError)):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                text("UPDATE tarea_asincrona SET estado = 'INVENTADO' WHERE id = :id"),
                {"id": tarea.id},
            )


async def test_la_funcion_del_barrido_ve_todas_las_empresas_y_solo_ids(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El agujero deliberado en la barrera, y su forma exacta.

    Beat corre sin empresa, así que RLS le muestra —correctamente— nada. La función
    `SECURITY DEFINER` es lo que le deja descubrir a quién barrer, y devuelve ids y nada
    más: sin ella el barrido no existiría, y con una más ancha sería una fuga.
    """
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    await _guardar_fallida(sesiones, empresa_a, sufijo="a")
    await _guardar_fallida(sesiones, empresa_b, sufijo="b")

    async with sesion_sin_empresa(sesiones) as sesion:
        # Sin la función, una sesión sin empresa no ve una sola fila.
        directas = await RepositorioTareaAsincrona(sesion).listar_fallidas(limite=10)
        assert directas == []

        empresas = await empresas_con_tareas_fallidas(sesion)

    assert set(empresas) == {empresa_a, empresa_b}


async def test_una_tarea_completada_no_aparece_en_el_barrido(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """El índice parcial y la función filtran por `FALLIDA`, que es todo lo que se barre."""
    empresa_id = await _empresa(engine_dueno)
    tarea = _tarea(empresa_id)
    tarea.marcar_en_curso(ahora=tarea.created_at)
    tarea.marcar_completada(ahora=tarea.created_at)
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await RepositorioTareaAsincrona(sesion).agregar(tarea)

    async with sesion_sin_empresa(sesiones) as sesion:
        assert await empresas_con_tareas_fallidas(sesion) == []
