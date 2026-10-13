"""`/plantillas` (U6): editar manda la plantilla a Meta antes de guardar (casos 1, 7 y 8).

Sin base de datos: la unidad de trabajo y los repositorios son dobles en memoria, y Meta es un doble
programable. Los casos de uso, el agregado y el mapeo de errores a HTTP son los reales. La prueba
contra PostgreSQL vive en `tests/integracion/test_api_conversacional.py`.

- Meta refuta → **422 con el texto de Meta** y la fila no cambió.
- Meta no contesta (timeout de lectura) → **503** y nada guardado, con **un solo** pedido.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.errors import registrar_manejadores
from cheatsheet.api.routers import plantillas
from cheatsheet.contexts.business_config.application.errors import (
    MetaNoDisponible,
    MetaRechazoLaPlantilla,
)
from cheatsheet.contexts.business_config.application.plantillas import DE_FABRICA
from cheatsheet.contexts.business_config.domain.plantilla import (
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import FastAPI, Request

from tests.conftest import INSTANTE_FIJO, settings_de_prueba
from tests.contexts.business_config.application.dobles_plantillas import (
    PublicadorFalso,
    RepositorioPlantillasEnMemoria,
    RevisionDeMetaFalsa,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
USUARIO = UsuarioId(uuid4())
CUERPO_VIEJO = "Hola {{nombre}}, te recordamos tu turno el {{fecha}} a las {{hora}}."
CUERPO_NUEVO = "Hola {{nombre}}, te esperamos el {{fecha}} a las {{hora}}. Gracias."


@dataclass(frozen=True)
class _Unidad:
    reloj: RelojFijo
    publicador: PublicadorFalso


@dataclass
class Montaje:
    app: FastAPI
    repositorio: RepositorioPlantillasEnMemoria
    revision: RevisionDeMetaFalsa
    plantilla: PlantillaDeNotificacion


def _plantilla(
    estado: EstadoDeAprobacion = EstadoDeAprobacion.SIN_ENVIAR, **extra: object
) -> PlantillaDeNotificacion:
    return PlantillaDeNotificacion(
        id=uuid4(),
        empresa_id=EMPRESA,
        codigo="recordatorio_de_turno",
        canal=CanalNotificacion.WHATSAPP,
        idioma="es_AR",
        cuerpo=CUERPO_VIEJO,
        estado_aprobacion=estado,
        nombre_en_meta="recordatorio_de_turno",
        **extra,  # type: ignore[arg-type]
    )


def _montar(
    monkeypatch: pytest.MonkeyPatch,
    plantilla: PlantillaDeNotificacion | None = None,
    revision: RevisionDeMetaFalsa | None = None,
    rol: RolUsuario = RolUsuario.ADMINISTRADOR,
) -> Montaje:
    plantilla = plantilla or _plantilla()
    repositorio = RepositorioPlantillasEnMemoria(plantilla)
    revision = revision or RevisionDeMetaFalsa()
    publicador = PublicadorFalso()

    class PiezasFalsas:
        def __init__(self) -> None:
            self.plantillas = repositorio

        @classmethod
        def armar(cls, _unidad: object) -> PiezasFalsas:
            return cls()

    async def unidad_de_trabajo(*_: Any) -> AsyncIterator[_Unidad]:
        yield _Unidad(RelojFijo(INSTANTE_FIJO), publicador)

    async def armar_revision(*_: Any, **__: Any) -> RevisionDeMetaFalsa:
        return revision

    monkeypatch.setattr(plantillas, "unidad_de_trabajo", unidad_de_trabajo)
    monkeypatch.setattr(plantillas, "ConfiguracionDeNegocio", PiezasFalsas)
    monkeypatch.setattr(plantillas, "armar_revision_de_meta", armar_revision)

    recursos = Recursos(
        settings=settings_de_prueba(),
        engine=None,  # type: ignore[arg-type]
        sesiones=None,  # type: ignore[arg-type]
        redis=None,  # type: ignore[arg-type]
        reloj=RelojFijo(INSTANTE_FIJO),
    )
    app = FastAPI()
    registrar_manejadores(app)
    app.add_exception_handler(MetaNoDisponible, plantillas.manejar_meta_no_disponible)

    @app.middleware("http")
    async def _actor(
        request: Request, siguiente: Callable[[Request], Awaitable[Any]]
    ) -> Any:  # el que autentica de verdad es `EmpresaMiddleware`; acá solo se declara quién es
        request.state.empresa_id = EMPRESA
        request.state.usuario_id = USUARIO
        request.state.rol = rol.value
        return await siguiente(request)

    app.include_router(plantillas.crear_router(recursos))
    return Montaje(app, repositorio, revision, plantilla)


async def _llamar(
    montaje: Montaje, metodo: str, ruta: str, cuerpo: dict[str, str] | None = None
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=montaje.app), base_url="http://test"
    ) as cliente:
        return await cliente.request(metodo, ruta, json=cuerpo)


async def test_el_listado_siembra_las_de_fabrica_sin_enviar_y_expone_el_estado_de_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _llamar(montaje, "GET", "/plantillas")

    assert respuesta.status_code == 200, respuesta.text
    listado = respuesta.json()["plantillas"]
    assert {una["codigo"] for una in listado} >= set(DE_FABRICA)
    sembrada = next(una for una in listado if una["codigo"] == "cobro_generado")
    assert sembrada["estado_aprobacion"] == "SIN_ENVIAR"
    assert sembrada["puede_usarse"] is False
    assert (sembrada["motivo_meta"], sembrada["detalle_meta"]) == (None, None)
    assert sembrada["editable_desde"] is None


async def test_el_listado_muestra_motivo_detalle_y_cuando_se_puede_editar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enviada = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
    montaje = _montar(
        monkeypatch,
        _plantilla(
            EstadoDeAprobacion.APROBADA,
            enviada_a_meta_en=enviada,
            categoria_en_meta="MARKETING",
            detalle_meta="Detalle de Meta",
        ),
    )

    respuesta = await _llamar(montaje, "GET", "/plantillas")

    una = next(
        una for una in respuesta.json()["plantillas"] if una["codigo"] == "recordatorio_de_turno"
    )
    assert una["categoria_en_meta"] == "MARKETING"
    assert una["detalle_meta"] == "Detalle de Meta"
    assert datetime.fromisoformat(una["editable_desde"]) == enviada + timedelta(hours=24)


async def test_guardar_una_plantilla_de_whatsapp_la_manda_a_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 1."""
    montaje = _montar(monkeypatch)

    respuesta = await _llamar(
        montaje, "PUT", f"/plantillas/{montaje.plantilla.id}", {"cuerpo": CUERPO_NUEVO}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_aprobacion"] == "APROBADA"
    assert respuesta.json()["cuerpo"] == CUERPO_NUEVO
    ((nombre, idioma, cuerpo, _),) = montaje.revision.creaciones
    assert (nombre, idioma, cuerpo) == ("recordatorio_de_turno", "es_AR", CUERPO_NUEVO)
    assert montaje.repositorio.filas[montaje.plantilla.id].cuerpo == CUERPO_NUEVO


async def test_si_meta_refuta_es_un_422_con_su_texto_y_la_fila_no_cambia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 7."""
    montaje = _montar(
        monkeypatch,
        revision=RevisionDeMetaFalsa(
            respuestas=[MetaRechazoLaPlantilla("Meta: el texto es promocional")]
        ),
    )

    respuesta = await _llamar(
        montaje, "PUT", f"/plantillas/{montaje.plantilla.id}", {"cuerpo": CUERPO_NUEVO}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detalle"] == "Meta: el texto es promocional"
    assert montaje.repositorio.filas[montaje.plantilla.id].cuerpo == CUERPO_VIEJO
    assert montaje.repositorio.guardados == 0


async def test_si_meta_no_responde_es_un_503_sin_guardar_y_con_un_solo_pedido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 8."""
    montaje = _montar(
        monkeypatch,
        revision=RevisionDeMetaFalsa(respuestas=[MetaNoDisponible("lento", incierto=True)]),
    )

    respuesta = await _llamar(
        montaje, "PUT", f"/plantillas/{montaje.plantilla.id}", {"cuerpo": CUERPO_NUEVO}
    )

    assert respuesta.status_code == 503, respuesta.text
    assert "volvé a intentarlo" in respuesta.json()["detalle"]
    assert len(montaje.revision.creaciones) == 1
    assert montaje.repositorio.filas[montaje.plantilla.id].cuerpo == CUERPO_VIEJO
    assert montaje.repositorio.guardados == 0


async def test_una_variable_desconocida_sigue_dando_el_422_de_la_historia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _llamar(
        montaje,
        "PUT",
        f"/plantillas/{montaje.plantilla.id}",
        {"cuerpo": "Hola {{nombre}}, tu saldo es {{saldo}}. Gracias."},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detalle"] == "La variable indicada no es válida para esta plantilla."
    assert montaje.revision.creaciones == []


async def test_editar_una_pendiente_es_un_422_sin_llamar_a_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 5."""
    montaje = _montar(
        monkeypatch, _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-1")
    )

    respuesta = await _llamar(
        montaje, "PUT", f"/plantillas/{montaje.plantilla.id}", {"cuerpo": CUERPO_NUEVO}
    )

    assert respuesta.status_code == 422
    assert "en revisión" in respuesta.json()["detalle"]
    assert montaje.revision.ediciones == []


async def test_el_operador_no_edita(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch, rol=RolUsuario.OPERADOR)

    respuesta = await _llamar(
        montaje, "PUT", f"/plantillas/{montaje.plantilla.id}", {"cuerpo": CUERPO_NUEVO}
    )

    assert respuesta.status_code == 403
    assert "Administrador" in respuesta.json()["detalle"]
    assert montaje.revision.creaciones == []


async def test_enviar_a_revision_reenvia_una_sin_enviar(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(monkeypatch)

    respuesta = await _llamar(montaje, "POST", f"/plantillas/{montaje.plantilla.id}/envio")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_aprobacion"] == "APROBADA"
    assert len(montaje.revision.creaciones) == 1


async def test_enviar_a_revision_una_aprobada_es_un_422(monkeypatch: pytest.MonkeyPatch) -> None:
    montaje = _montar(
        monkeypatch, _plantilla(EstadoDeAprobacion.APROBADA, meta_plantilla_id="meta-1")
    )

    respuesta = await _llamar(montaje, "POST", f"/plantillas/{montaje.plantilla.id}/envio")

    assert respuesta.status_code == 422
    assert montaje.revision.creaciones == []
    assert montaje.revision.ediciones == []


async def test_enviar_a_revision_solo_lo_hace_el_administrador(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    montaje = _montar(monkeypatch, rol=RolUsuario.OPERADOR)

    respuesta = await _llamar(montaje, "POST", f"/plantillas/{montaje.plantilla.id}/envio")

    assert respuesta.status_code == 403
    assert montaje.revision.creaciones == []
