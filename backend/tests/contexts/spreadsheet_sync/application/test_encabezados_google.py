"""Google links feed the same mapping proposal as uploaded files."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.mapeos import LeerEncabezados
from cheatsheet.contexts.spreadsheet_sync.application.ports import FilaLeida, PlanillaLeida
from cheatsheet.contexts.spreadsheet_sync.domain.valores import DireccionSync, ProveedorPlanilla
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio


async def test_google_link_reads_its_source_sheet_and_returns_examples() -> None:
    ahora = datetime(2026, 10, 12, tzinfo=UTC)
    vinculo = VinculoDePlanilla(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        proveedor=ProveedorPlanilla.GOOGLE_SHEETS,
        direccion=DireccionSync.LECTURA_Y_ESCRITURA,
        hoja_empresa="Clientes",
        hoja_cheatsheet="CheatSheet (no editar)",
        identificador_externo="document-1",
        configuracion_integracion_id=uuid4(),
        created_at=ahora,
        updated_at=ahora,
    )

    class Vinculos:
        async def buscar_por_id(self, _id: object) -> VinculoDePlanilla:
            return vinculo

    class Google:
        async def leer_hoja(self, **kwargs: object) -> PlanillaLeida:
            assert kwargs == {
                "token": "company-token",
                "identificador": "document-1",
                "hoja": "Clientes",
                "max_filas": 100,
            }
            return PlanillaLeida(
                columnas=("Nombre", "CUIT"),
                filas=(FilaLeida(numero=2, celdas={"Nombre": "Ana", "CUIT": "030123"}),),
            )

    columnas = await LeerEncabezados(
        vinculos=Vinculos(),  # type: ignore[arg-type]
        almacenamiento=None,  # type: ignore[arg-type]
        lector=None,  # type: ignore[arg-type]
        lector_remoto=Google(),
    ).ejecutar(vinculo_id=vinculo.id, token="company-token")

    assert [(columna.nombre, columna.ejemplo) for columna in columnas] == [
        ("Nombre", "Ana"),
        ("CUIT", "030123"),
    ]
