"""Las plantillas en Meta contra el motor (U6, casos 11 a 14, 16 y 29).

Lo que un doble no puede probar, y por eso corre contra PostgreSQL:

1. **Las columnas nuevas viajan** en los dos sentidos, y los estados nuevos caben en la columna.
2. **RLS**: el webhook de la WABA de A nunca ve ni toca una plantilla de B, y el índice único
   `uq_plantilla_meta_id` impide dos filas con el mismo id de Meta **en la misma empresa** (y
   permite el mismo id en dos empresas distintas: son cuentas distintas).
3. **Las dos funciones `SECURITY DEFINER`** responden con el rol de la aplicación, sin empresa, y
   devuelven solo ids de empresa.
4. **La conciliación** siembra, manda y guarda de punta a punta sobre PostgreSQL.

Se saltean sin base y corren en CI.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from cheatsheet.contexts.business_config.application.conciliacion import (
    ConciliarPlantillasConMeta,
)
from cheatsheet.contexts.business_config.application.plantillas import (
    DE_FABRICA,
    ActualizarEstadoDesdeMeta,
    ListarPlantillas,
)
from cheatsheet.contexts.business_config.domain.plantilla import EstadoDeAprobacion
from cheatsheet.contexts.business_config.infrastructure.repositories import (
    RepositorioPlantillasPostgres,
)
from cheatsheet.contexts.integrations.infrastructure.repositories import (
    empresas_con_whatsapp_conectado,
    empresas_de_la_cuenta_de_whatsapp,
)
from cheatsheet.platform.database import sesion_de_empresa, sesion_sin_empresa
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.contexts.business_config.application.dobles_plantillas import RevisionDeMetaFalsa
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration, pytest.mark.asyncio]

AHORA = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
Sesiones = async_sessionmaker[AsyncSession]

CREAR_EMPRESA = text("INSERT INTO empresa (id, activa) VALUES (:id, true)")
CREAR_INTEGRACION = text(
    "INSERT INTO configuracion_de_integracion "
    "(id, empresa_id, sistema, credencial_contenido_cifrado, credencial_algoritmo, parametros, "
    "ambiente, estado) "
    "VALUES (:id, :empresa_id, 'WHATSAPP', '\\x00', 'x', CAST(:parametros AS jsonb), "
    "'SANDBOX', 'CONECTADO')"
)


async def _empresa(engine_dueno: AsyncEngine) -> EmpresaId:
    empresa_id = EmpresaId(uuid.uuid4())
    async with engine_dueno.begin() as conexion:
        await conexion.execute(CREAR_EMPRESA, {"id": empresa_id})
    return empresa_id


async def _sembrar(sesiones: Sesiones, empresa_id: EmpresaId) -> None:
    async with sesion_de_empresa(sesiones, empresa_id) as sesion:
        await ListarPlantillas(RepositorioPlantillasPostgres(sesion)).ejecutar(
            empresa_id=empresa_id, ahora=AHORA
        )


async def test_las_columnas_nuevas_y_los_estados_nuevos_viajan_completos(
    sesiones: Sesiones, engine_dueno: AsyncEngine
) -> None:
    empresa = await _empresa(engine_dueno)
    await _sembrar(sesiones, empresa)

    async with sesion_de_empresa(sesiones, empresa) as sesion:
        repositorio = RepositorioPlantillasPostgres(sesion)
        plantilla = await repositorio.buscar_por_codigo("turno_confirmado")
        assert plantilla is not None
        assert plantilla.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR
        assert plantilla.nombre_en_meta == "turno_confirmado"
        plantilla.registrar_envio_a_meta(
            meta_plantilla_id="meta-77", nombre_en_meta="turno_confirmado_v2", momento=AHORA
        )
        plantilla.aplicar_respuesta_de_meta(
            EstadoDeAprobacion.DESHABILITADA,
            motivo="SCAM",
            detalle="Detalle de Meta",
            momento=AHORA,
            categoria="MARKETING",
        )
        await repositorio.guardar(plantilla)

    async with sesion_de_empresa(sesiones, empresa) as sesion:
        leida = await RepositorioPlantillasPostgres(sesion).buscar_por_meta_id("meta-77")

    assert leida is not None
    assert leida.estado_aprobacion is EstadoDeAprobacion.DESHABILITADA
    assert leida.nombre_en_meta == "turno_confirmado_v2"
    assert (leida.motivo_meta, leida.detalle_meta) == ("SCAM", "Detalle de Meta")
    assert leida.categoria_en_meta == "MARKETING"
    assert leida.enviada_a_meta_en == AHORA
    assert leida.estado_meta_en == AHORA


async def test_el_webhook_de_a_nunca_ve_la_plantilla_de_b(
    sesiones: Sesiones, engine_dueno: AsyncEngine
) -> None:
    """Caso 14, contra RLS: dentro de la empresa A, el id de Meta de B no existe."""
    a, b = await _empresa(engine_dueno), await _empresa(engine_dueno)
    await _sembrar(sesiones, a)
    await _sembrar(sesiones, b)
    async with sesion_de_empresa(sesiones, b) as sesion:
        repositorio = RepositorioPlantillasPostgres(sesion)
        de_b = await repositorio.buscar_por_codigo("cobro_generado")
        assert de_b is not None
        de_b.vincular_con_meta("meta-de-b")
        await repositorio.guardar(de_b)

    async with sesion_de_empresa(sesiones, a) as sesion:
        cambio = await ActualizarEstadoDesdeMeta(RepositorioPlantillasPostgres(sesion)).ejecutar(
            estado="APPROVED", momento=AHORA, es_evento=True, meta_plantilla_id="meta-de-b"
        )

    assert cambio is False
    async with sesion_de_empresa(sesiones, b) as sesion:
        intacta = await RepositorioPlantillasPostgres(sesion).buscar_por_meta_id("meta-de-b")
    assert intacta is not None
    assert intacta.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR


async def _vincular_dos_con_el_mismo_id(sesiones: Sesiones, empresa: EmpresaId) -> None:
    async with sesion_de_empresa(sesiones, empresa) as sesion:
        repositorio = RepositorioPlantillasPostgres(sesion)
        for codigo in ("turno_confirmado", "turno_cancelado"):
            plantilla = await repositorio.buscar_por_codigo(codigo)
            assert plantilla is not None
            plantilla.vincular_con_meta("meta-repetido")
            await repositorio.guardar(plantilla)


async def test_el_indice_unico_impide_el_mismo_id_de_meta_dos_veces_en_la_misma_empresa(
    sesiones: Sesiones, engine_dueno: AsyncEngine
) -> None:
    empresa = await _empresa(engine_dueno)
    await _sembrar(sesiones, empresa)

    with pytest.raises(IntegrityError):
        await _vincular_dos_con_el_mismo_id(sesiones, empresa)


async def test_el_mismo_id_de_meta_en_dos_empresas_es_valido(
    sesiones: Sesiones, engine_dueno: AsyncEngine
) -> None:
    a, b = await _empresa(engine_dueno), await _empresa(engine_dueno)
    for empresa in (a, b):
        await _sembrar(sesiones, empresa)
        async with sesion_de_empresa(sesiones, empresa) as sesion:
            repositorio = RepositorioPlantillasPostgres(sesion)
            plantilla = await repositorio.buscar_por_codigo("turno_confirmado")
            assert plantilla is not None
            plantilla.vincular_con_meta("meta-compartido")
            await repositorio.guardar(plantilla)


async def test_las_funciones_security_definer_responden_con_el_rol_de_la_aplicacion(
    sesiones: Sesiones, engine_dueno: AsyncEngine
) -> None:
    """Caso 29: sin empresa puesta, `cheatsheet_app` las ejecuta y solo ve ids de empresa."""
    empresa = await _empresa(engine_dueno)
    waba = f"waba-{uuid.uuid4()}"
    async with engine_dueno.begin() as conexion:
        await conexion.execute(
            CREAR_INTEGRACION,
            {
                "id": uuid.uuid4(),
                "empresa_id": empresa,
                "parametros": json.dumps({"waba_id": waba}),
            },
        )

    async with sesion_sin_empresa(sesiones) as sesion:
        duenas = await empresas_de_la_cuenta_de_whatsapp(sesion, waba)
        desconocida = await empresas_de_la_cuenta_de_whatsapp(sesion, "no-existe")
        conectadas = await empresas_con_whatsapp_conectado(sesion)

    assert duenas == [empresa]
    assert desconocida == []
    assert empresa in conectadas


async def test_la_conciliacion_siembra_manda_y_guarda_sobre_postgres(
    sesiones: Sesiones, engine_dueno: AsyncEngine
) -> None:
    """Caso 16: una empresa sin plantillas termina con las seis creadas en Meta y aprobadas."""
    empresa = await _empresa(engine_dueno)
    revision = RevisionDeMetaFalsa()

    async with sesion_de_empresa(sesiones, empresa) as sesion:
        resumen = await ConciliarPlantillasConMeta(
            RepositorioPlantillasPostgres(sesion), revision
        ).ejecutar(empresa_id=empresa, ahora=AHORA)

    assert resumen.sembradas == len(DE_FABRICA)
    assert resumen.enviadas == len(DE_FABRICA)
    async with sesion_de_empresa(sesiones, empresa) as sesion:
        guardadas = await RepositorioPlantillasPostgres(sesion).listar()
    assert len(guardadas) == len(DE_FABRICA)
    assert all(una.estado_aprobacion is EstadoDeAprobacion.APROBADA for una in guardadas)
    assert len({una.meta_plantilla_id for una in guardadas}) == len(DE_FABRICA)
