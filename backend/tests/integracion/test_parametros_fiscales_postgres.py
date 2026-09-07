"""El catálogo fiscal contra el motor, y lo que lo hace distinto de todo lo demás.

`parametro_fiscal` es **la única tabla de negocio del sistema sin `empresa_id` y sin
política de RLS**. Eso no se puede probar con un doble: lo que hay que verificar es
justamente que la barrera que protege a todas las otras tablas acá **no está**, y que lo que
la reemplaza —el `GRANT` de sólo lectura y el índice único parcial— sí.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from cheatsheet.contexts.reference_data.domain.parametro import TipoCatalogoFiscal
from cheatsheet.contexts.reference_data.infrastructure.repositories import (
    RepositorioParametrosPostgres,
)
from cheatsheet.platform.database import sesion_de_empresa, sesion_sin_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
IVA = TipoCatalogoFiscal.ALICUOTA_IVA

INSERTAR = text(
    "INSERT INTO parametro_fiscal (id, tipo, codigo, valor, fecha_desde, fecha_hasta)"
    " VALUES (:id, :tipo, :codigo, :valor, :desde, :hasta)"
)


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


async def _sembrar(
    engine_dueno: AsyncEngine,
    *,
    codigo: str,
    valor: str,
    desde: date,
    hasta: date | None = None,
) -> None:
    """Escrito con el rol dueño, que es quien escribe acá también en producción: la
    migración y el barrido de Beat. El rol de la aplicación no puede — es el test de más
    abajo."""
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            INSERTAR,
            {
                "id": uuid.uuid4(),
                "tipo": IVA.value,
                "codigo": codigo,
                "valor": valor,
                "desde": desde,
                "hasta": hasta,
            },
        )


async def test_todas_las_empresas_ven_el_mismo_catalogo(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """La tabla no tiene `empresa_id`: el catálogo es de ARCA y es el mismo para todos.

    Es el único test del sistema que verifica **ausencia** de aislamiento, y por eso vale la
    pena que exista: alguien agregando RLS acá «por consistencia» rompería la unicidad del
    catálogo sin que nada más fallara.
    """
    empresa_a = await _empresa(engine_dueno)
    empresa_b = await _empresa(engine_dueno)
    await _sembrar(engine_dueno, codigo="5", valor="0.21", desde=date(2026, 1, 1))

    for empresa_id in (empresa_a, empresa_b):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            encontrado = await RepositorioParametrosPostgres(sesion).buscar_vigente_a(
                tipo=IVA, codigo="5", fecha=date(2026, 6, 1)
            )
        assert encontrado is not None
        assert encontrado.valor == "0.21"


async def test_tambien_se_lee_sin_empresa_declarada(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Sin `app.current_empresa` toda otra tabla devuelve cero filas. Esta no.

    Es lo que le permite al barrido de Beat leer el catálogo sin pedir prestada una empresa.
    """
    await _sembrar(engine_dueno, codigo="4", valor="0.105", desde=date(2026, 1, 1))

    async with sesion_sin_empresa(sesiones) as sesion:
        vigentes = await RepositorioParametrosPostgres(sesion).vigentes(tipo=IVA)

    assert any(p.codigo == "4" for p in vigentes)


async def test_el_rol_de_la_aplicacion_no_puede_escribir(
    sesiones: async_sessionmaker[AsyncSession], engine_dueno: AsyncEngine
) -> None:
    """Lo que reemplaza a RLS acá: el `GRANT` es `SELECT` y nada más.

    Un rol de aplicación que pudiera escribir sería un rol capaz de darle a una empresa una
    alícuota distinta de la de todas las demás — exactamente la falla que RLS previene en
    las otras 25 tablas, y que acá se previene no siendo escribible desde un request.
    """
    empresa_id = await _empresa(engine_dueno)

    with pytest.raises(ProgrammingError):
        async with sesion_de_empresa(sesiones, empresa_id) as sesion:
            await sesion.execute(
                INSERTAR,
                {
                    "id": uuid.uuid4(),
                    "tipo": IVA.value,
                    "codigo": "99",
                    "valor": "0.99",
                    "desde": date(2026, 1, 1),
                    "hasta": None,
                },
            )


async def test_dos_vigencias_abiertas_del_mismo_parametro_son_rechazadas(
    engine_dueno: AsyncEngine,
) -> None:
    """El invariante del agregado, en el motor: el índice único parcial.

    Dos filas del mismo `(tipo, codigo)` con `fecha_hasta IS NULL` son dos versiones
    vigentes a la vez, y el código de emisión tomaría la que el planner devolviera primero.
    """
    await _sembrar(engine_dueno, codigo="7", valor="0.21", desde=date(2026, 1, 1))

    with pytest.raises((IntegrityError, DBAPIError)):
        await _sembrar(engine_dueno, codigo="7", valor="0.25", desde=date(2026, 6, 1))


async def test_el_historico_cerrado_convive_sin_limite(
    engine_dueno: AsyncEngine, sesiones: async_sessionmaker[AsyncSession]
) -> None:
    """El índice es parcial justamente para esto: cualquier cantidad de filas cerradas."""
    await _sembrar(
        engine_dueno, codigo="8", valor="0.10", desde=date(2025, 1, 1), hasta=date(2025, 12, 31)
    )
    await _sembrar(
        engine_dueno, codigo="8", valor="0.15", desde=date(2026, 1, 1), hasta=date(2026, 5, 31)
    )
    await _sembrar(engine_dueno, codigo="8", valor="0.21", desde=date(2026, 6, 1))

    async with sesion_sin_empresa(sesiones) as sesion:
        repo = RepositorioParametrosPostgres(sesion)
        en_2025 = await repo.buscar_vigente_a(tipo=IVA, codigo="8", fecha=date(2025, 6, 1))
        en_marzo = await repo.buscar_vigente_a(tipo=IVA, codigo="8", fecha=date(2026, 3, 1))
        hoy = await repo.buscar_vigente_a(tipo=IVA, codigo="8", fecha=date(2026, 9, 1))

    assert en_2025 is not None
    assert en_2025.valor == "0.10"
    assert en_marzo is not None
    assert en_marzo.valor == "0.15"
    assert hoy is not None
    assert hoy.valor == "0.21"


async def test_un_tipo_fuera_del_catalogo_es_rechazado(engine_dueno: AsyncEngine) -> None:
    with pytest.raises((IntegrityError, DBAPIError)):
        async with engine_dueno.begin() as conexion:
            await conexion.execute(
                INSERTAR,
                {
                    "id": uuid.uuid4(),
                    "tipo": "INVENTADO",
                    "codigo": "1",
                    "valor": "x",
                    "desde": date(2026, 1, 1),
                    "hasta": None,
                },
            )
