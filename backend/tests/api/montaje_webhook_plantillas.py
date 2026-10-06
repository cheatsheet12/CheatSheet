"""El montaje compartido de los tests del webhook de plantillas (U6): app, repos y eventos."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.errors import registrar_manejadores
from cheatsheet.api.routers import whatsapp
from cheatsheet.contexts.business_config.domain.plantilla import (
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from fastapi import FastAPI

from tests.conftest import INSTANTE_FIJO, settings_de_prueba
from tests.contexts.business_config.application.dobles_plantillas import (
    RepositorioPlantillasEnMemoria,
)

EMPRESA_A = EmpresaId(uuid4())
EMPRESA_B = EmpresaId(uuid4())
WABA_A = "100200300"
WABA_B = "400500600"
T0 = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)


@dataclass(frozen=True)
class UnidadDePrueba:
    reloj: RelojFijo
    empresa: EmpresaId


@dataclass
class Montaje:
    app: FastAPI
    repos: dict[EmpresaId, RepositorioPlantillasEnMemoria]
    plantillas: dict[EmpresaId, PlantillaDeNotificacion]


def plantilla(empresa: EmpresaId) -> PlantillaDeNotificacion:
    return PlantillaDeNotificacion(
        id=uuid4(),
        empresa_id=empresa,
        codigo="recordatorio_de_cobro",
        canal=CanalNotificacion.WHATSAPP,
        idioma="es_AR",
        cuerpo="Hola {{nombre}}, tu cobro de {{concepto}} por $ {{monto}}: {{link}} Gracias.",
        estado_aprobacion=EstadoDeAprobacion.PENDIENTE,
        nombre_en_meta="recordatorio_de_cobro",
        meta_plantilla_id=f"meta-{empresa}",
    )


def montar(
    monkeypatch: pytest.MonkeyPatch, duenos: dict[str, list[EmpresaId]] | None = None
) -> Montaje:
    plantillas = {EMPRESA_A: plantilla(EMPRESA_A), EMPRESA_B: plantilla(EMPRESA_B)}
    repos = {empresa: RepositorioPlantillasEnMemoria(una) for empresa, una in plantillas.items()}
    duenos = duenos if duenos is not None else {WABA_A: [EMPRESA_A], WABA_B: [EMPRESA_B]}

    class _SesionSinEmpresa:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_: object) -> None:
            return None

    async def empresas_de_la_cuenta(_sesion: object, waba_id: str) -> list[EmpresaId]:
        return duenos.get(waba_id, [])

    async def unidad_de_trabajo(
        _recursos: object, empresa_id: EmpresaId
    ) -> AsyncIterator[UnidadDePrueba]:
        yield UnidadDePrueba(RelojFijo(INSTANTE_FIJO), empresa_id)

    class _Piezas:
        def __init__(self, unidad: UnidadDePrueba) -> None:
            self.plantillas = repos[unidad.empresa]

        @classmethod
        def armar(cls, unidad: UnidadDePrueba) -> _Piezas:
            return cls(unidad)

    monkeypatch.setattr(whatsapp, "sesion_sin_empresa", lambda _sesiones: _SesionSinEmpresa())
    monkeypatch.setattr(whatsapp, "empresas_de_la_cuenta_de_whatsapp", empresas_de_la_cuenta)
    monkeypatch.setattr(whatsapp, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(whatsapp, "ConfiguracionDeNegocio", _Piezas)

    recursos = Recursos(
        settings=settings_de_prueba(),
        engine=None,  # type: ignore[arg-type]
        sesiones=None,  # type: ignore[arg-type]
        redis=None,  # type: ignore[arg-type]
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    app = FastAPI()
    registrar_manejadores(app)
    app.include_router(whatsapp.crear_router(recursos))
    return Montaje(app, repos, plantillas)


def evento(
    waba: str,
    evento: str,
    *,
    meta_id: object = None,
    momento: datetime = T0,
    **valor: object,
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": waba,
                "time": int(momento.timestamp()),
                "changes": [
                    {
                        "field": "message_template_status_update",
                        "value": {
                            "event": evento,
                            "message_template_id": meta_id,
                            "message_template_name": "recordatorio_de_cobro",
                            "message_template_language": "es_AR",
                            **valor,
                        },
                    }
                ],
            }
        ],
    }


def firmar(crudo: bytes) -> str:
    secreto = settings_de_prueba().whatsapp_webhook_secret
    return "sha256=" + hmac.new(secreto.encode(), crudo, hashlib.sha256).hexdigest()


async def enviar(
    montaje: Montaje,
    cuerpo: dict[str, Any] | bytes,
    ruta: str = "/webhooks/whatsapp",
    *,
    firma: str | None = None,
) -> httpx.Response:
    crudo = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        return await cliente.post(
            ruta, content=crudo, headers={"x-hub-signature-256": firma or firmar(crudo)}
        )


def estado(montaje: Montaje, empresa: EmpresaId) -> PlantillaDeNotificacion:
    return montaje.repos[empresa].filas[montaje.plantillas[empresa].id]


def id_de(empresa: EmpresaId) -> str:
    return f"meta-{empresa}"


__all__ = [
    "EMPRESA_A",
    "EMPRESA_B",
    "T0",
    "WABA_A",
    "WABA_B",
    "Montaje",
    "enviar",
    "estado",
    "evento",
    "id_de",
    "montar",
]
