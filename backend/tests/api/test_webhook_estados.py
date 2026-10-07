"""El webhook de WhatsApp recibe los `statuses[]` de Meta y mueve el estado de entrega (U7).

Casos 1, 2, 5, 8, 10, 11, 12, 13 y 14. Los repositorios son los dobles en memoria de cada contexto;
la unidad de trabajo imita lo que importa del real: **solo confirma si el cuerpo del `async for`
termina** (una excepción adentro descarta lo escrito), y un `wamid` solo existe en los repositorios
de **su** empresa (lo que RLS garantiza en PostgreSQL).
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
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega as EstadoDeRecordatorio
from cheatsheet.contexts.payments.domain.recordatorio import Recordatorio
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId
from fastapi import FastAPI
from structlog.testing import capture_logs

from tests.api.montaje_webhook_plantillas import EMPRESA_A, EMPRESA_B, WABA_A, WABA_B, firmar
from tests.conftest import INSTANTE_FIJO, settings_de_prueba
from tests.contexts.conversational.application.dobles import RepositorioMensajeEnMemoria
from tests.contexts.payments.application.test_cobros_y_recordatorios import RecordatoriosFalsos
from tests.contexts.payments.application.test_confirmacion import PublicadorFalso

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
RUTA_APP = "/webhooks/whatsapp"


class _SesionSinEmpresa:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class RepositorioQueExplota(RepositorioMensajeEnMemoria):
    """Levanta al buscar `wamid-boom`: lo que pasa cuando algo nuestro se rompe."""

    async def buscar_por_externo_id(self, externo_id: str) -> Mensaje | None:
        if externo_id == "wamid-boom":
            raise RuntimeError("se rompio algo nuestro")
        return await super().buscar_por_externo_id(externo_id)


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


def _saliente(empresa: EmpresaId, externo_id: str) -> Mensaje:
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


def _recordatorio(externo_id: str) -> Recordatorio:
    recordatorio = Recordatorio(id=uuid4(), cobro_id=uuid4(), paso=1, canal="WHATSAPP")
    recordatorio.marcar_enviado(AHORA, externo_id=externo_id)
    return recordatorio


async def _montar(
    monkeypatch: pytest.MonkeyPatch, duenos: dict[str, list[EmpresaId]] | None = None
) -> Montaje:
    empresas = (EMPRESA_A, EMPRESA_B)
    duenos = duenos if duenos is not None else {WABA_A: [EMPRESA_A], WABA_B: [EMPRESA_B]}
    mensajes: dict[EmpresaId, RepositorioMensajeEnMemoria] = {
        EMPRESA_A: RepositorioQueExplota(_saliente(EMPRESA_A, "wamid-agente-a")),
        EMPRESA_B: RepositorioQueExplota(_saliente(EMPRESA_B, "wamid-agente-b")),
    }
    recordatorios = {empresa: RecordatoriosFalsos() for empresa in empresas}
    publicadores = {empresa: PublicadorFalso() for empresa in empresas}
    for empresa, wamid in ((EMPRESA_A, "wamid-cobro-a"), (EMPRESA_B, "wamid-cobro-b")):
        await recordatorios[empresa].agregar(_recordatorio(wamid))
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

    monkeypatch.setattr(entregas, "sesion_sin_empresa", lambda _sesiones: _SesionSinEmpresa())
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


def _estado(wamid: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": wamid,
        "status": status,
        "timestamp": "1760000000",
        "recipient_id": "549",
        **extra,
    }


def _cuerpo(waba: str, *estados: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": waba, "changes": [{"field": "messages", "value": {"statuses": list(estados)}}]}
        ],
    }


async def _enviar(montaje: Montaje, cuerpo: dict[str, Any], ruta: str = RUTA_APP) -> httpx.Response:
    crudo = json.dumps(cuerpo).encode()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        return await cliente.post(
            ruta, content=crudo, headers={"x-hub-signature-256": firmar(crudo)}
        )


def _mensaje(montaje: Montaje, empresa: EmpresaId) -> Mensaje:
    (uno,) = montaje.mensajes[empresa].mensajes.values()
    return uno


def _recordatorio_de(montaje: Montaje, empresa: EmpresaId) -> Recordatorio:
    (uno,) = montaje.recordatorios[empresa].guardados
    return uno


# ------------------------------------------------------------------ caso 1 y 2


@pytest.mark.parametrize("ruta", [RUTA_APP, f"{RUTA_APP}/{EMPRESA_A}"])
async def test_delivered_del_wamid_de_un_mensaje_del_agente_lo_deja_entregado(
    monkeypatch: pytest.MonkeyPatch, ruta: str
) -> None:
    montaje = await _montar(monkeypatch)

    respuesta = await _enviar(
        montaje, _cuerpo(WABA_A, _estado("wamid-agente-a", "delivered")), ruta
    )

    assert respuesta.status_code == 200
    assert _mensaje(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENTREGADO
    assert montaje.confirmadas == [EMPRESA_A]


@pytest.mark.parametrize("ruta", [RUTA_APP, f"{RUTA_APP}/{EMPRESA_A}"])
async def test_read_del_wamid_de_un_recordatorio_de_cobro_lo_deja_leido(
    monkeypatch: pytest.MonkeyPatch, ruta: str
) -> None:
    montaje = await _montar(monkeypatch)

    await _enviar(montaje, _cuerpo(WABA_A, _estado("wamid-cobro-a", "read")), ruta)

    assert _recordatorio_de(montaje, EMPRESA_A).estado_entrega is EstadoDeRecordatorio.LEIDO


# ------------------------------------------------------------------ caso 5 y 8


async def test_el_mismo_statuses_dos_veces_es_un_solo_efecto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await _montar(monkeypatch)
    cuerpo = _cuerpo(
        WABA_A, _estado("wamid-cobro-a", "failed", errors=[{"code": 131047, "title": "x"}])
    )

    await _enviar(montaje, cuerpo)
    await _enviar(montaje, cuerpo)

    recordatorio = _recordatorio_de(montaje, EMPRESA_A)
    assert recordatorio.estado_entrega is EstadoDeRecordatorio.FALLIDO
    assert recordatorio.ultimo_error == "131047"
    assert len(montaje.publicadores[EMPRESA_A].eventos) == 1


async def test_failed_deja_el_motivo_y_un_read_posterior_no_lo_cambia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await _montar(monkeypatch)

    await _enviar(
        montaje,
        _cuerpo(WABA_A, _estado("wamid-agente-a", "failed", errors=[{"code": 131047}])),
    )
    await _enviar(montaje, _cuerpo(WABA_A, _estado("wamid-agente-a", "read")))

    mensaje = _mensaje(montaje, EMPRESA_A)
    assert mensaje.estado_entrega is EstadoDeMensaje.FALLIDO
    assert mensaje.motivo_de_falla == "131047"


async def test_delivered_fuera_de_orden_despues_de_read_no_retrocede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await _montar(monkeypatch)

    await _enviar(
        montaje,
        _cuerpo(
            WABA_A,
            _estado("wamid-agente-a", "read"),
            _estado("wamid-agente-a", "delivered"),
            _estado("wamid-cobro-a", "read"),
            _estado("wamid-cobro-a", "delivered"),
        ),
    )

    assert _mensaje(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.LEIDO
    assert _recordatorio_de(montaje, EMPRESA_A).estado_entrega is EstadoDeRecordatorio.LEIDO


async def test_played_se_ignora_sin_error(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = await _montar(monkeypatch)

    respuesta = await _enviar(montaje, _cuerpo(WABA_A, _estado("wamid-agente-a", "played")))

    assert respuesta.status_code == 200
    assert _mensaje(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENVIADO
    assert montaje.confirmadas == []


# ------------------------------------------------------------------ caso 10, 11 y 12


async def test_el_wamid_de_un_recordatorio_de_b_por_la_url_de_a_no_cambia_nada_en_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 10. Con la WABA de A en el cuerpo, el estado se busca **en A**: el `wamid` de B no existe ahí."""
    montaje = await _montar(monkeypatch)

    respuesta = await _enviar(
        montaje,
        _cuerpo(WABA_A, _estado("wamid-cobro-b", "read"), _estado("wamid-agente-b", "read")),
        f"{RUTA_APP}/{EMPRESA_A}",
    )

    assert respuesta.status_code == 200
    assert _recordatorio_de(montaje, EMPRESA_B).estado_entrega is EstadoDeRecordatorio.ENVIADO
    assert _mensaje(montaje, EMPRESA_B).estado_entrega is EstadoDeMensaje.ENVIADO


async def test_una_waba_ajena_en_la_url_de_a_se_descarta_con_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 11: la URL no decide la empresa, y la WABA de B no es la de A."""
    montaje = await _montar(monkeypatch)

    with capture_logs() as registros:
        respuesta = await _enviar(
            montaje, _cuerpo(WABA_B, _estado("wamid-agente-b", "read")), f"{RUTA_APP}/{EMPRESA_A}"
        )

    assert respuesta.status_code == 200
    assert _mensaje(montaje, EMPRESA_B).estado_entrega is EstadoDeMensaje.ENVIADO
    assert montaje.confirmadas == []
    assert "whatsapp_estado_de_waba_ajena" in [uno["event"] for uno in registros]


async def test_la_ruta_de_la_app_rutea_cada_estado_a_la_empresa_dueña_de_su_waba(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 12."""
    montaje = await _montar(monkeypatch)

    await _enviar(
        montaje,
        {
            "entry": [
                {
                    "id": waba,
                    "changes": [
                        {"field": "messages", "value": {"statuses": [_estado(wamid, "read")]}}
                    ],
                }
                for waba, wamid in ((WABA_A, "wamid-agente-a"), (WABA_B, "wamid-cobro-b"))
            ]
        },
    )

    assert _mensaje(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.LEIDO
    assert _recordatorio_de(montaje, EMPRESA_B).estado_entrega is EstadoDeRecordatorio.LEIDO
    assert montaje.confirmadas == [EMPRESA_A, EMPRESA_B]  # una transacción por estado


@pytest.mark.parametrize("duenas", [[], [EMPRESA_A, EMPRESA_B]])
async def test_una_waba_sin_dueña_o_con_dos_se_registra_y_se_sigue(
    monkeypatch: pytest.MonkeyPatch, duenas: list[EmpresaId]
) -> None:
    montaje = await _montar(monkeypatch, {WABA_A: duenas})

    with capture_logs() as registros:
        respuesta = await _enviar(montaje, _cuerpo(WABA_A, _estado("wamid-agente-a", "read")))

    assert respuesta.status_code == 200
    assert _mensaje(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENVIADO
    assert "whatsapp_estado_de_waba_sin_una_sola_empresa" in [uno["event"] for uno in registros]


# ------------------------------------------------------------------ caso 13 y 14


async def test_un_wamid_desconocido_contesta_200_y_el_log_no_lleva_el_wamid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = await _montar(monkeypatch)
    desconocido = "wamid.HBgMNTQ5MTE1NTU1MDAwMBUCABIYFjNFQjAxMjM0NTY3ODlBQkNERUY"

    with capture_logs() as registros:
        respuesta = await _enviar(montaje, _cuerpo(WABA_A, _estado(desconocido, "sent")))

    assert respuesta.status_code == 200
    assert "whatsapp_estado_sin_destinatario" in [uno["event"] for uno in registros]
    assert desconocido not in repr(registros)
    assert "5491155550000" not in repr(registros)


async def test_si_el_segundo_estado_falla_el_primero_ya_quedo_aplicado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 14: una transacción por estado, no una para todo el lote."""
    montaje = await _montar(monkeypatch)

    with pytest.raises(RuntimeError):
        await _enviar(
            montaje,
            _cuerpo(WABA_A, _estado("wamid-agente-a", "delivered"), _estado("wamid-boom", "read")),
        )

    assert _mensaje(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENTREGADO
    assert montaje.confirmadas == [EMPRESA_A]  # el segundo se descartó: no hay confirmación


# ------------------------------------------------------------------ rutas y robustez


async def test_una_firma_invalida_no_procesa_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = await _montar(monkeypatch)
    crudo = json.dumps(_cuerpo(WABA_A, _estado("wamid-agente-a", "read"))).encode()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.post(
            RUTA_APP, content=crudo, headers={"x-hub-signature-256": "sha256=00"}
        )

    assert respuesta.status_code == 200
    assert _mensaje(montaje, EMPRESA_A).estado_entrega is EstadoDeMensaje.ENVIADO


async def test_un_payload_solo_de_estados_no_loguea_mensajes_en_la_url_de_la_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`hay_mensajes` era verdadero para cualquier `field=messages`: ahora mira `messages[]`."""
    montaje = await _montar(monkeypatch)

    with capture_logs() as registros:
        await _enviar(montaje, _cuerpo(WABA_A, _estado("wamid-agente-a", "read")))
        await _enviar(
            montaje,
            {
                "entry": [
                    {
                        "id": WABA_A,
                        "changes": [
                            {"field": "messages", "value": {"messages": [{"id": "m", "from": "1"}]}}
                        ],
                    }
                ]
            },
        )

    eventos = [uno["event"] for uno in registros]
    assert eventos.count("whatsapp_mensajes_en_la_url_de_la_app") == 1


async def test_ningun_log_de_los_estados_lleva_telefono_ni_wamid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 28 para los módulos nuevos: el `recipient_id` (un teléfono) y el `wamid` no se loguean."""
    montaje = await _montar(monkeypatch)
    cuerpo = _cuerpo(
        WABA_A,
        _estado(
            "wamid-agente-a", "failed", errors=[{"code": 131026}], recipient_id="5491155550000"
        ),
        _estado("wamid-nadie", "read", recipient_id="5491155550000"),
    )

    with capture_logs() as registros:
        await _enviar(montaje, cuerpo)
        await _enviar(
            montaje, _cuerpo(WABA_B, _estado("wamid-nadie", "read")), f"{RUTA_APP}/{EMPRESA_A}"
        )

    volcado = repr(registros)
    assert registros
    for dato in ("5491155550000", "wamid-nadie", "wamid-agente-a"):
        assert dato not in volcado
