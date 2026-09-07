"""PostgreSQL adapter for `PortRepositorioVinculo`.

Same two conventions as every repository in this system: the mapping is written by hand
in both directions so the domain keeps no framework dependency (rule R1), and `empresa_id`
never reaches a `WHERE` clause because Row-Level Security already scopes the statement.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.spreadsheet_sync.domain.mapeo import (
    EntradaDeMapeo,
    EstadoMapeo,
    Mapeo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.valores import (
    DireccionSync,
    ProveedorPlanilla,
    ReferenciaDeArchivo,
)
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.contexts.spreadsheet_sync.infrastructure.models import (
    EntradaDeMapeoORM,
    MapeoORM,
    VinculoDePlanillaORM,
)
from cheatsheet.shared.empresa import EmpresaId


def _referencia(fila: VinculoDePlanillaORM) -> ReferenciaDeArchivo | None:
    if fila.archivo_clave is None or fila.archivo_nombre is None or fila.archivo_tamano is None:
        return None
    return ReferenciaDeArchivo(
        clave=fila.archivo_clave,
        nombre_original=fila.archivo_nombre,
        tamano_bytes=fila.archivo_tamano,
    )


def _a_dominio(fila: VinculoDePlanillaORM) -> VinculoDePlanilla:
    return VinculoDePlanilla(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        proveedor=ProveedorPlanilla(fila.proveedor),
        direccion=DireccionSync(fila.direccion),
        hoja_empresa=fila.hoja_empresa,
        hoja_cheatsheet=fila.hoja_cheatsheet,
        identificador_externo=fila.identificador_externo,
        configuracion_integracion_id=fila.configuracion_integracion_id,
        archivo=_referencia(fila),
        mapeo_vigente_id=fila.mapeo_vigente_id,
        ultima_lectura=fila.ultima_lectura,
        ultima_escritura=fila.ultima_escritura,
        pausado=fila.pausado,
        motivo_de_pausa=fila.motivo_de_pausa,
        created_at=fila.created_at,
        updated_at=fila.updated_at,
    )


class RepositorioVinculoPostgres:
    """Spreadsheet links, backed by PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, vinculo: VinculoDePlanilla) -> None:
        self._sesion.add(
            VinculoDePlanillaORM(
                id=vinculo.id,
                empresa_id=vinculo.empresa_id,
                configuracion_integracion_id=vinculo.configuracion_integracion_id,
                mapeo_vigente_id=vinculo.mapeo_vigente_id,
                proveedor=vinculo.proveedor.value,
                direccion=vinculo.direccion.value,
                identificador_externo=vinculo.identificador_externo,
                hoja_empresa=vinculo.hoja_empresa,
                hoja_cheatsheet=vinculo.hoja_cheatsheet,
                archivo_clave=vinculo.archivo.clave if vinculo.archivo else None,
                archivo_nombre=vinculo.archivo.nombre_original if vinculo.archivo else None,
                archivo_tamano=vinculo.archivo.tamano_bytes if vinculo.archivo else None,
                ultima_lectura=vinculo.ultima_lectura,
                ultima_escritura=vinculo.ultima_escritura,
                pausado=vinculo.pausado,
                motivo_de_pausa=vinculo.motivo_de_pausa,
                created_at=vinculo.created_at,
                updated_at=vinculo.updated_at,
            )
        )
        await self._sesion.flush()

    async def actualizar(self, vinculo: VinculoDePlanilla) -> None:
        fila = await self._sesion.get(VinculoDePlanillaORM, vinculo.id)
        if fila is None:
            raise LookupError(f"El vinculo {vinculo.id} no existe para esta empresa")
        fila.mapeo_vigente_id = vinculo.mapeo_vigente_id
        fila.direccion = vinculo.direccion.value
        fila.hoja_cheatsheet = vinculo.hoja_cheatsheet
        fila.ultima_lectura = vinculo.ultima_lectura
        fila.ultima_escritura = vinculo.ultima_escritura
        fila.pausado = vinculo.pausado
        fila.motivo_de_pausa = vinculo.motivo_de_pausa
        fila.updated_at = vinculo.updated_at
        await self._sesion.flush()

    async def buscar_por_id(self, vinculo_id: UUID) -> VinculoDePlanilla | None:
        fila = await self._sesion.get(VinculoDePlanillaORM, vinculo_id)
        return _a_dominio(fila) if fila is not None else None

    async def listar(self) -> list[VinculoDePlanilla]:
        sentencia = select(VinculoDePlanillaORM).order_by(VinculoDePlanillaORM.created_at.desc())
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def eliminar(self, vinculo_id: UUID) -> None:
        await self._sesion.execute(
            delete(VinculoDePlanillaORM).where(VinculoDePlanillaORM.id == vinculo_id)
        )
        await self._sesion.flush()


def _entrada_a_dominio(fila: EntradaDeMapeoORM) -> EntradaDeMapeo:
    return EntradaDeMapeo(
        id=fila.id,
        columna_origen=fila.columna_origen,
        atributo_destino=fila.atributo_destino,
        score=fila.score,
        ejemplo=fila.ejemplo,
        corregida_a_mano=fila.corregida_a_mano,
    )


def _mapeo_a_dominio(fila: MapeoORM, entradas: list[EntradaDeMapeoORM]) -> Mapeo:
    return Mapeo(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        huella_encabezado=fila.huella_encabezado,
        estado=EstadoMapeo(fila.estado),
        version=fila.version,
        # Ordered by the column's position in the sheet, which is the order the review
        # screen shows and the order the user read them in.
        entradas=[_entrada_a_dominio(e) for e in entradas],
        created_at=fila.created_at,
        updated_at=fila.updated_at,
    )


class RepositorioMapeoPostgres:
    """Mappings and their entries, backed by PostgreSQL.

    The entries are written with a delete-and-reinsert rather than a per-row diff. A
    mapping has as many entries as the spreadsheet has columns -- dozens, not thousands --
    and the diff would be more code for the same number of round trips.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, mapeo: Mapeo) -> None:
        self._sesion.add(
            MapeoORM(
                id=mapeo.id,
                empresa_id=mapeo.empresa_id,
                huella_encabezado=mapeo.huella_encabezado,
                estado=mapeo.estado.value,
                version=mapeo.version,
                created_at=mapeo.created_at,
                updated_at=mapeo.updated_at,
            )
        )
        self._agregar_entradas(mapeo)
        await self._sesion.flush()

    async def actualizar(self, mapeo: Mapeo) -> None:
        fila = await self._sesion.get(MapeoORM, mapeo.id)
        if fila is None:
            raise LookupError(f"El mapeo {mapeo.id} no existe para esta empresa")
        fila.estado = mapeo.estado.value
        fila.version = mapeo.version
        fila.updated_at = mapeo.updated_at

        await self._sesion.execute(
            delete(EntradaDeMapeoORM).where(EntradaDeMapeoORM.mapeo_id == mapeo.id)
        )
        self._agregar_entradas(mapeo)
        await self._sesion.flush()

    async def buscar_por_id(self, mapeo_id: UUID) -> Mapeo | None:
        fila = await self._sesion.get(MapeoORM, mapeo_id)
        if fila is None:
            return None
        return _mapeo_a_dominio(fila, await self._entradas_de(mapeo_id))

    async def buscar_por_huella(self, huella: str) -> Mapeo | None:
        sentencia = select(MapeoORM).where(MapeoORM.huella_encabezado == huella)
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        if fila is None:
            return None
        return _mapeo_a_dominio(fila, await self._entradas_de(fila.id))

    async def _entradas_de(self, mapeo_id: UUID) -> list[EntradaDeMapeoORM]:
        sentencia = (
            select(EntradaDeMapeoORM)
            .where(EntradaDeMapeoORM.mapeo_id == mapeo_id)
            .order_by(EntradaDeMapeoORM.columna_origen)
        )
        return list((await self._sesion.execute(sentencia)).scalars().all())

    def _agregar_entradas(self, mapeo: Mapeo) -> None:
        for entrada in mapeo.entradas:
            self._sesion.add(
                EntradaDeMapeoORM(
                    id=entrada.id,
                    mapeo_id=mapeo.id,
                    empresa_id=mapeo.empresa_id,
                    columna_origen=entrada.columna_origen,
                    atributo_destino=entrada.atributo_destino,
                    score=entrada.score,
                    ejemplo=entrada.ejemplo,
                    corregida_a_mano=entrada.corregida_a_mano,
                )
            )
