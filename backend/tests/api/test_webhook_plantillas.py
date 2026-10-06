"""El webhook `message_template_status_update` (U6, casos 11 a 15).

**No admite override por cuenta** [WH-OVR]: el estado de una plantilla llega a la URL de la app
(`/webhooks/whatsapp`) y se rutea por el **WABA id** del `entry[].id`, nunca por la URL. Sin base de
datos: la resolución de la empresa, la unidad de trabajo y los repositorios son dobles; el parser,
los casos de uso y el agregado son los reales.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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

pytestmark = pytest.mark.asyncio

EMPRESA_A = EmpresaId(uuid4())
EMPRESA_B = EmpresaId(uuid4())
WABA_A = "100200300"
WABA_B = "400500600"
T0 = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _Unidad:
    reloj: RelojFijo
    empresa: EmpresaId


@dataclass
class Montaje:
    app: FastAPI
    repos: dict[EmpresaId, RepositorioPlantillasEnMemoria]
    plantillas: dict[EmpresaId, PlantillaDeNotificacion]


def _plantilla(empresa: EmpresaId) -> PlantillaDeNotificacion:
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


def _montar(
    monkeypatch: pytest.MonkeyPatch, duenos: dict[str, list[EmpresaId]] | None = None
) -> Montaje:
    plantillas = {EMPRESA_A: _plantilla(EMPRESA_A), EMPRESA_B: _plantilla(EMPRESA_B)}
    repos = {empresa: RepositorioPlantillasEnMemoria(una) for empresa, una in plantillas.items()}
    duenos = duenos if duenos is not None else {WABA_A: [EMPRESA_A], WABA_B: [EMPRESA_B]}

    class _SesionSinEmpresa:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_: object) -> None:
            return None

    async def empresas_de_la_cuenta(_sesion: object, waba_id: str) -> list[EmpresaId]:
        return duenos.get(waba_id, [])

    async def unidad_de_trabajo(_recursos: object, empresa_id: EmpresaId) -> AsyncIterator[_Unidad]:
        yield _Unidad(RelojFijo(INSTANTE_FIJO), empresa_id)

    class _Piezas:
        def __init__(self, unidad: _Unidad) -> None:
            self.plantillas = repos[unidad.empresa]

        @classmethod
        def armar(cls, unidad: _Unidad) -> _Piezas:
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


def _evento(
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


def _firmar(crudo: bytes) -> str:
    secreto = settings_de_prueba().whatsapp_webhook_secret
    return "sha256=" + hmac.new(secreto.encode(), crudo, hashlib.sha256).hexdigest()


async def _enviar(
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
            ruta, content=crudo, headers={"x-hub-signature-256": firma or _firmar(crudo)}
        )


def _estado(montaje: Montaje, empresa: EmpresaId) -> PlantillaDeNotificacion:
    return montaje.repos[empresa].filas[montaje.plantillas[empresa].id]


def _id_de(empresa: EmpresaId) -> str:
    return f"meta-{empresa}"


# --- Caso 11 ----------------------------------------------------------------------------------------------


async def test_approved_por_la_waba_de_a_deja_aprobada_la_plantilla_de_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _enviar(
        montaje, _evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_A), reason="NONE")
    )

    assert respuesta.status_code == 200
    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert _estado(montaje, EMPRESA_A).puede_usarse
    assert _estado(montaje, EMPRESA_B).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


# --- Caso 12 ----------------------------------------------------------------------------------------------


async def test_rejected_guarda_el_motivo_y_la_recomendacion_de_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)

    await _enviar(
        montaje,
        _evento(
            WABA_A,
            "REJECTED",
            meta_id=_id_de(EMPRESA_A),
            reason="PROMOTIONAL",
            rejection_info={"reason": "PROMOTIONAL", "recommendation": "Quitá el tono comercial."},
        ),
    )

    guardada = _estado(montaje, EMPRESA_A)
    assert guardada.estado_aprobacion is EstadoDeAprobacion.RECHAZADA
    assert guardada.motivo_meta == "PROMOTIONAL"
    assert guardada.detalle_meta == "Quitá el tono comercial."


async def test_flagged_sigue_usable_y_deja_el_detalle_de_other_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)

    await _enviar(
        montaje,
        _evento(
            WABA_A,
            "FLAGGED",
            meta_id=_id_de(EMPRESA_A),
            other_info={"title": "FLAGGED", "description": "Calidad baja: revisá el texto."},
        ),
    )

    guardada = _estado(montaje, EMPRESA_A)
    assert guardada.estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert guardada.detalle_meta == "Calidad baja: revisá el texto."


async def test_el_id_de_meta_puede_venir_como_numero(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)
    montaje.repos[EMPRESA_A].filas[montaje.plantillas[EMPRESA_A].id].meta_plantilla_id = "9876"

    await _enviar(montaje, _evento(WABA_A, "APPROVED", meta_id=9876))

    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA


async def test_sin_id_se_encuentra_por_nombre_e_idioma(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)

    await _enviar(montaje, _evento(WABA_A, "APPROVED"))

    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA


# --- Caso 13 ----------------------------------------------------------------------------------------------


async def test_el_mismo_evento_dos_veces_es_un_solo_efecto(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)
    evento = _evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_A))

    primera = await _enviar(montaje, evento)
    despues_de_la_primera = _estado(montaje, EMPRESA_A).updated_at
    segunda = await _enviar(montaje, evento)

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert _estado(montaje, EMPRESA_A).updated_at == despues_de_la_primera


async def test_un_pending_anterior_al_approved_aplicado_no_retrocede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)
    await _enviar(montaje, _evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_A), momento=T0))

    await _enviar(
        montaje,
        _evento(WABA_A, "PENDING", meta_id=_id_de(EMPRESA_A), momento=T0 - timedelta(minutes=10)),
    )

    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA


# --- Caso 14: se rutea por WABA, nunca por la URL ----------------------------------------------------------


async def test_un_evento_de_la_waba_de_a_por_la_url_de_b_actualiza_a_y_nunca_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _enviar(
        montaje,
        _evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_A)),
        ruta=f"/webhooks/whatsapp/{EMPRESA_B}",
    )

    assert respuesta.status_code == 200
    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert _estado(montaje, EMPRESA_B).estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert montaje.repos[EMPRESA_B].guardados == 0


async def test_una_waba_desconocida_es_200_sin_efecto(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _enviar(montaje, _evento("999", "APPROVED", meta_id=_id_de(EMPRESA_A)))

    assert respuesta.status_code == 200
    assert montaje.repos[EMPRESA_A].guardados == 0
    assert montaje.repos[EMPRESA_B].guardados == 0


async def test_una_waba_con_dos_duenos_no_se_adivina(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch, {WABA_A: [EMPRESA_A, EMPRESA_B]})

    respuesta = await _enviar(montaje, _evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_A)))

    assert respuesta.status_code == 200
    assert montaje.repos[EMPRESA_A].guardados == 0
    assert montaje.repos[EMPRESA_B].guardados == 0


async def test_un_id_de_meta_de_otra_empresa_no_toca_la_plantilla_de_esta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La WABA dice A, el id de plantilla es de B: se busca **dentro de A** y no existe."""
    montaje = _montar(monkeypatch)

    await _enviar(montaje, _evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_B)))

    assert _estado(montaje, EMPRESA_B).estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


# --- Caso 15: firma y verificación ----------------------------------------------------------------------------


async def test_una_firma_invalida_es_200_sin_efecto(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _enviar(
        montaje,
        _evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_A)),
        firma="sha256=" + "0" * 64,
    )

    assert respuesta.status_code == 200
    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


async def test_sin_firma_la_ruta_de_la_app_no_aplica_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)
    crudo = json.dumps(_evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_A))).encode()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        respuesta = await cliente.post("/webhooks/whatsapp", content=crudo)

    assert respuesta.status_code == 200
    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


async def _verificar(montaje: Montaje, **params: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        return await cliente.get("/webhooks/whatsapp", params=params)


async def test_la_verificacion_de_la_url_de_la_app_devuelve_el_desafio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)
    token = settings_de_prueba().whatsapp_webhook_verify_token

    respuesta = await _verificar(
        montaje,
        **{"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "12345"},
    )

    assert respuesta.status_code == 200
    assert respuesta.text == "12345"


async def test_la_verificacion_con_otro_token_es_404(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _verificar(
        montaje,
        **{"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "12345"},
    )

    assert respuesta.status_code == 404


# --- Robustez del parser ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        b"no es json",
        b"[]",
        b'{"entry": "basura"}',
        b'{"entry": [{"changes": [{"field": "message_template_status_update", "value": 7}]}]}',
        b'{"entry": [{"id": 5, "changes": [{"field": "message_template_status_update", "value": {}}]}]}',
        b'{"entry": [{"id": "1", "changes": [{"field": "otro", "value": {"event": "APPROVED"}}]}]}',
    ],
)
async def test_un_cuerpo_con_forma_inesperada_es_200_sin_efecto(
    monkeypatch: pytest.MonkeyPatch, cuerpo: bytes
) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _enviar(montaje, cuerpo)

    assert respuesta.status_code == 200
    assert montaje.repos[EMPRESA_A].guardados == 0


async def test_un_estado_desconocido_es_200_y_no_cambia_nada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _enviar(montaje, _evento(WABA_A, "INVENTADO", meta_id=_id_de(EMPRESA_A)))

    assert respuesta.status_code == 200
    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.PENDIENTE


async def test_un_evento_por_cada_cambio_de_la_notificacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)
    cuerpo = _evento(WABA_A, "APPROVED", meta_id=_id_de(EMPRESA_A))
    otra_entrada = _evento(WABA_B, "REJECTED", meta_id=_id_de(EMPRESA_B), reason="SCAM")
    cuerpo["entry"].extend(otra_entrada["entry"])

    await _enviar(montaje, cuerpo)

    assert _estado(montaje, EMPRESA_A).estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert _estado(montaje, EMPRESA_B).estado_aprobacion is EstadoDeAprobacion.RECHAZADA
