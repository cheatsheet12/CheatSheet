"""The existing Celery task must process a linked Google sheet, not silently skip it."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cheatsheet.contexts.spreadsheet_sync.application.ports import FilaLeida, PlanillaLeida
from cheatsheet.contexts.spreadsheet_sync.domain.valores import DireccionSync, ProveedorPlanilla
from cheatsheet.contexts.spreadsheet_sync.domain.vinculo import VinculoDePlanilla
from cheatsheet.platform.settings import AdaptadorDePlanilla
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers import tasks_spreadsheet as modulo

pytestmark = pytest.mark.asyncio


async def test_worker_processes_linked_google_rows_with_company_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empresa = EmpresaId(uuid4())
    ahora = datetime(2026, 10, 12, tzinfo=UTC)
    credencial_id = uuid4()
    vinculo = VinculoDePlanilla(
        id=uuid4(),
        empresa_id=empresa,
        proveedor=ProveedorPlanilla.GOOGLE_SHEETS,
        direccion=DireccionSync.SOLO_LECTURA,
        hoja_empresa="Clientes",
        identificador_externo="document-1",
        configuracion_integracion_id=credencial_id,
        created_at=ahora,
        updated_at=ahora,
    )
    leida = PlanillaLeida(
        columnas=("Nombre",), filas=(FilaLeida(numero=2, celdas={"Nombre": "Ana"}),)
    )
    llamada: dict[str, object] = {}

    class Vinculos:
        async def buscar_por_id(self, _id: object) -> VinculoDePlanilla:
            return vinculo

    async def unidad_de_trabajo(
        _recursos: object, empresa_id: EmpresaId
    ) -> AsyncIterator[SimpleNamespace]:
        assert empresa_id == empresa
        yield SimpleNamespace(
            sesion=object(), reloj=SimpleNamespace(ahora=lambda: ahora), publicador=object()
        )

    class Credenciales:
        async def obtener(self, **kwargs: object) -> str:
            assert kwargs["empresa_id"] == empresa
            assert kwargs["configuracion_id"] == credencial_id
            return "company-token"

    class Lector:
        async def leer_hoja(self, **kwargs: object) -> PlanillaLeida:
            assert kwargs["token"] == "company-token"
            assert kwargs["hoja"] == "Clientes"
            return leida

    class Procesador:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        async def ejecutar(self, **kwargs: object) -> object:
            llamada.update(kwargs)
            return SimpleNamespace(
                procesamiento=SimpleNamespace(
                    id=uuid4(),
                    estado=SimpleNamespace(value="COMPLETADO"),
                    filas_ok=1,
                    filas_error=0,
                )
            )

    monkeypatch.setattr(modulo, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(
        modulo,
        "Planillas",
        SimpleNamespace(
            armar=lambda _unidad: SimpleNamespace(
                vinculos=Vinculos(), procesamientos=object(), mapeos=object()
            )
        ),
    )
    monkeypatch.setattr(
        modulo,
        "DatosMaestros",
        SimpleNamespace(
            armar=lambda _unidad: SimpleNamespace(clientes=object(), servicios=object())
        ),
    )
    monkeypatch.setattr(modulo, "IngestaEnMasterData", lambda **_kwargs: object())
    monkeypatch.setattr(
        modulo, "credenciales_de_planilla", lambda _sesion, _settings: Credenciales()
    )
    monkeypatch.setattr(modulo, "lectura_de_planilla", lambda _settings: Lector(), raising=False)
    monkeypatch.setattr(modulo, "ProcesarPlanilla", Procesador)
    settings = SimpleNamespace(planilla_adaptador=AdaptadorDePlanilla.GOOGLE)

    assert (
        await modulo.procesar_planilla(
            SimpleNamespace(settings=settings),  # type: ignore[arg-type]
            empresa_id=empresa,
            vinculo_id=vinculo.id,
        )
        == 1
    )
    lectura = llamada["lectura_remota"]
    assert callable(lectura)
    assert await lectura() == leida
