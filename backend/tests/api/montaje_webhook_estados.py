"""El montaje de los tests del webhook de estados de entrega (U7): repositorios en memoria y rutas.

Los repositorios son los dobles en memoria de cada contexto; la unidad de trabajo imita lo que
importa del real: **solo confirma si el cuerpo del `async for` termina** (una excepción adentro
descarta lo escrito), y un `wamid` solo existe en los repositorios de **su** empresa (lo que RLS
garantiza en PostgreSQL). Comparte empresas, WABA y firma con `montaje_webhook_plantillas`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cheatsheet.api import entregas
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.errors import registrar_manejadores
from cheatsheet.api.routers import whatsapp
from cheatsheet.contexts.conversational.domain.conversacion import (
    DireccionMensaje,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    EstadoEntrega as EstadoDeMensaje,
)
from cheatsheet.contexts.payments.domain.recordatorio import Recordatorio
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from fastapi import FastAPI

from tests.api.montaje_webhook_plantillas import EMPRESA_A, EMPRESA_B, WABA_A, WABA_B, firmar
from tests.conftest import INSTANTE_FIJO, settings_de_prueba
from tests.contexts.conversational.application.dobles import RepositorioMensajeEnMemoria
from tests.contexts.payments.application.test_cobros_y_recordatorios import RecordatoriosFalsos
from tests.contexts.payments.application.test_confirmacion import PublicadorFalso

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
RUTA_APP = "/webhooks/whatsapp"


class SesionSinEmpresa:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class RepositorioQueExplota(RepositorioMensajeEnMemoria):
    """Levanta al buscar `wamid-boom`: lo que pasa cuando algo nuestro se rompe."""

    async def buscar_por_externo_id(
        self, externo_id: str, *, para_actualizar: bool = False
    ) -> Mensaje | None:
        if externo_id == "wamid-boom":
            raise RuntimeError("se rompio algo nuestro")
        return await super().buscar_por_externo_id(externo_id, para_actualizar=para_actualizar)


@dataclass(frozen=True)
class UnidadDePrueba:
    reloj: RelojFijo
    empresa: EmpresaId
    publicador: PublicadorFalso


@dataclass
class Montaje:
    app: FastAPI
    mensajes: dict[EmpresaId, RepositorioMensajeEnMemoria]
    recordatorios: dict[EmpresaId, RecordatoriosFalsos]
    publicadores: dict[EmpresaId, PublicadorFalso]
    confirmadas: list[EmpresaId] = field(default_factory=list)


def saliente(empresa: EmpresaId, externo_id: str) -> Mensaje:
    return Mensaje(
        id=uuid4(),
        conversacion_id=uuid4(),
        empresa_id=empresa,
        direccion=DireccionMensaje.SALIENTE,
        tipo_contenido=TipoContenido.TEXTO,
        contenido="hola",
        momento=AHORA,
        origen=OrigenDelMensaje.AGENTE,
        estado_entrega=EstadoDeMensaje.ENVIADO,
        externo_id=externo_id,
    )


def recordatorio_nuevo(externo_id: str) -> Recordatorio:
    recordatorio = Recordatorio(id=uuid4(), cobro_id=uuid4(), paso=1, canal="WHATSAPP")
    recordatorio.marcar_enviado(AHORA, externo_id=externo_id)
    return recordatorio


async def montar(
    monkeypatch: pytest.MonkeyPatch, duenos: dict[str, list[EmpresaId]] | None = None
) -> Montaje:
    empresas = (EMPRESA_A, EMPRESA_B)
    duenos = duenos if duenos is not None else {WABA_A: [EMPRESA_A], WABA_B: [EMPRESA_B]}
    mensajes: dict[EmpresaId, RepositorioMensajeEnMemoria] = {
        EMPRESA_A: RepositorioQueExplota(saliente(EMPRESA_A, "wamid-agente-a")),
        EMPRESA_B: RepositorioQueExplota(saliente(EMPRESA_B, "wamid-agente-b")),
    }
    recordatorios = {empresa: RecordatoriosFalsos() for empresa in empresas}
    publicadores = {empresa: PublicadorFalso() for empresa in empresas}
    for empresa, wamid in ((EMPRESA_A, "wamid-cobro-a"), (EMPRESA_B, "wamid-cobro-b")):
        await recordatorios[empresa].agregar(recordatorio_nuevo(wamid))
    montaje = Montaje(FastAPI(), mensajes, recordatorios, publicadores)

    async def empresas_de_la_cuenta(_sesion: object, waba_id: str) -> list[EmpresaId]:
        return duenos.get(waba_id, [])

    async def unidad_de_trabajo(
        _recursos: object, empresa_id: EmpresaId
    ) -> AsyncIterator[UnidadDePrueba]:
        yield UnidadDePrueba(RelojFijo(INSTANTE_FIJO), empresa_id, publicadores[empresa_id])
        montaje.confirmadas.append(empresa_id)  # solo si el cuerpo del `async for` terminó

    class _Conversaciones:
        def __init__(self, unidad: UnidadDePrueba) -> None:
            self.mensajes = mensajes[unidad.empresa]

        @classmethod
        def armar(cls, unidad: UnidadDePrueba) -> _Conversaciones:
            return cls(unidad)

    class _Cobros:
        def __init__(self, unidad: UnidadDePrueba) -> None:
            self.recordatorios = recordatorios[unidad.empresa]

        @classmethod
        def armar(cls, unidad: UnidadDePrueba) -> _Cobros:
            return cls(unidad)

    monkeypatch.setattr(entregas, "sesion_sin_empresa", lambda _sesiones: SesionSinEmpresa())
    monkeypatch.setattr(entregas, "empresas_de_la_cuenta_de_whatsapp", empresas_de_la_cuenta)
    monkeypatch.setattr(entregas, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(entregas, "Conversaciones", _Conversaciones)
    monkeypatch.setattr(entregas, "Cobros", _Cobros)

    recursos = Recursos(
        settings=settings_de_prueba(),
        engine=None,  # type: ignore[arg-type]
        sesiones=None,  # type: ignore[arg-type]
        redis=None,  # type: ignore[arg-type]
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    registrar_manejadores(montaje.app)
    montaje.app.include_router(whatsapp.crear_router(recursos))
    return montaje


def estado(wamid: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": wamid,
        "status": status,
        "timestamp": "1760000000",
        "recipient_id": "549",
        **extra,
    }


def cuerpo(waba: str, *estados: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": waba, "changes": [{"field": "messages", "value": {"statuses": list(estados)}}]}
        ],
    }


async def enviar(montaje: Montaje, cuerpo: dict[str, Any], ruta: str = RUTA_APP) -> httpx.Response:
    crudo = json.dumps(cuerpo).encode()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        return await cliente.post(
            ruta, content=crudo, headers={"x-hub-signature-256": firmar(crudo)}
        )


def mensaje_de(montaje: Montaje, empresa: EmpresaId) -> Mensaje:
    (uno,) = montaje.mensajes[empresa].mensajes.values()
    return uno


def recordatorio_de(montaje: Montaje, empresa: EmpresaId) -> Recordatorio:
    (uno,) = montaje.recordatorios[empresa].guardados
    return uno
