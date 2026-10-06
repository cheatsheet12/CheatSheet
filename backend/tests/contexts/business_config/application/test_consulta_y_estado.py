"""`ConsultarPlantillaParaEnviar` y `ActualizarEstadoDesdeMeta` (U6, casos 11 a 13, 18, 23 y 25)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.business_config.application import plantillas as modulo_plantillas
from cheatsheet.contexts.business_config.application.plantillas import (
    ActualizarEstadoDesdeMeta,
    ConsultarPlantillaParaEnviar,
)
from cheatsheet.contexts.business_config.domain.plantilla import (
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.empresa import EmpresaId
from structlog.testing import capture_logs

from tests.logs import logger_nuevo

from .dobles_plantillas import RepositorioPlantillasEnMemoria

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
AHORA = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
CUERPO = "Hola {{nombre}}, te esperamos el {{fecha}} a las {{hora}} en {{recurso}}. Gracias."


def _plantilla(
    estado: EstadoDeAprobacion = EstadoDeAprobacion.APROBADA,
    *,
    cuerpo: str = CUERPO,
    canal: CanalNotificacion = CanalNotificacion.WHATSAPP,
    **extra: object,
) -> PlantillaDeNotificacion:
    return PlantillaDeNotificacion(
        id=uuid4(),
        empresa_id=EMPRESA,
        codigo="turno_confirmado",
        canal=canal,
        idioma="es_AR",
        cuerpo=cuerpo,
        estado_aprobacion=estado,
        nombre_en_meta="turno_confirmado",
        **extra,  # type: ignore[arg-type]
    )


VARIABLES = {
    "nombre": "Ana",
    "servicio": "Consulta",
    "recurso": "Sala 1",
    "fecha": "15/10/2026",
    "hora": "10:30",
}


# --- ConsultarPlantillaParaEnviar -------------------------------------------------------------------


async def test_una_aprobada_devuelve_nombre_idioma_parametros_y_texto() -> None:
    caso = ConsultarPlantillaParaEnviar(RepositorioPlantillasEnMemoria(_plantilla()))

    resultado = await caso.ejecutar("turno_confirmado", VARIABLES)

    assert resultado is not None
    assert resultado.nombre_en_meta == "turno_confirmado"
    assert resultado.idioma == "es_AR"
    assert resultado.parametros == {
        "nombre": "Ana",
        "fecha": "15/10/2026",
        "hora": "10:30",
        "recurso": "Sala 1",
    }
    assert resultado.texto == "Hola Ana, te esperamos el 15/10/2026 a las 10:30 en Sala 1. Gracias."


async def test_solo_se_mandan_los_parametros_que_el_cuerpo_usa() -> None:
    """Caso 23: un cuerpo editado sin `{{recurso}}` no lo manda (Meta contesta 132000)."""
    plantilla = _plantilla(cuerpo="Hola {{nombre}}, te esperamos el {{fecha}}. Gracias.")
    caso = ConsultarPlantillaParaEnviar(RepositorioPlantillasEnMemoria(plantilla))

    resultado = await caso.ejecutar("turno_confirmado", VARIABLES)

    assert resultado is not None
    assert set(resultado.parametros) == {"nombre", "fecha"}


async def test_un_salto_de_linea_o_tabulacion_en_un_valor_se_reemplaza_por_un_espacio() -> None:
    """Caso 25."""
    caso = ConsultarPlantillaParaEnviar(RepositorioPlantillasEnMemoria(_plantilla()))

    resultado = await caso.ejecutar(
        "turno_confirmado", {**VARIABLES, "nombre": "Ana\nMaría\t", "recurso": "Sala\r\n1"}
    )

    assert resultado is not None
    assert resultado.parametros["nombre"] == "Ana María"
    assert resultado.parametros["recurso"] == "Sala 1"
    assert "\n" not in resultado.texto


@pytest.mark.parametrize(
    "estado",
    [
        EstadoDeAprobacion.SIN_ENVIAR,
        EstadoDeAprobacion.PENDIENTE,
        EstadoDeAprobacion.RECHAZADA,
        EstadoDeAprobacion.PAUSADA,
        EstadoDeAprobacion.DESHABILITADA,
    ],
)
async def test_una_plantilla_no_aprobada_no_se_usa(estado: EstadoDeAprobacion) -> None:
    caso = ConsultarPlantillaParaEnviar(RepositorioPlantillasEnMemoria(_plantilla(estado)))

    assert await caso.ejecutar("turno_confirmado", VARIABLES) is None


async def test_sin_plantilla_o_de_otro_canal_devuelve_none() -> None:
    email = _plantilla(EstadoDeAprobacion.NO_APLICA, canal=CanalNotificacion.EMAIL)

    assert (
        await ConsultarPlantillaParaEnviar(RepositorioPlantillasEnMemoria(email)).ejecutar(
            "turno_confirmado", VARIABLES
        )
        is None
    )
    assert (
        await ConsultarPlantillaParaEnviar(RepositorioPlantillasEnMemoria()).ejecutar(
            "turno_confirmado", VARIABLES
        )
        is None
    )


async def test_una_variable_usada_sin_valor_devuelve_none() -> None:
    caso = ConsultarPlantillaParaEnviar(RepositorioPlantillasEnMemoria(_plantilla()))

    assert await caso.ejecutar("turno_confirmado", {"nombre": "Ana"}) is None


# --- ActualizarEstadoDesdeMeta ----------------------------------------------------------------------------


def _con(
    plantilla: PlantillaDeNotificacion,
) -> tuple[RepositorioPlantillasEnMemoria, ActualizarEstadoDesdeMeta]:
    repositorio = RepositorioPlantillasEnMemoria(plantilla)
    return repositorio, ActualizarEstadoDesdeMeta(repositorio)


async def test_un_evento_aprobado_deja_la_plantilla_usable() -> None:
    """Caso 11."""
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-9")
    repositorio, caso = _con(plantilla)

    cambio = await caso.ejecutar(
        estado="APPROVED", momento=AHORA, es_evento=True, meta_plantilla_id="meta-9"
    )

    assert cambio is True
    guardada = repositorio.filas[plantilla.id]
    assert guardada.estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert guardada.puede_usarse


async def test_un_evento_rechazado_guarda_motivo_y_detalle() -> None:
    """Caso 12."""
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-9")
    repositorio, caso = _con(plantilla)

    await caso.ejecutar(
        estado="REJECTED",
        momento=AHORA,
        es_evento=True,
        meta_plantilla_id="meta-9",
        motivo="PROMOTIONAL",
        detalle="Quitá el tono comercial.",
    )

    guardada = repositorio.filas[plantilla.id]
    assert guardada.estado_aprobacion is EstadoDeAprobacion.RECHAZADA
    assert guardada.motivo_meta == "PROMOTIONAL"
    assert guardada.detalle_meta == "Quitá el tono comercial."


async def test_el_mismo_evento_dos_veces_es_un_solo_efecto() -> None:
    """Caso 13."""
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-9")
    _, caso = _con(plantilla)

    primera = await caso.ejecutar(
        estado="APPROVED", momento=AHORA, es_evento=True, meta_plantilla_id="meta-9"
    )
    segunda = await caso.ejecutar(
        estado="APPROVED", momento=AHORA, es_evento=True, meta_plantilla_id="meta-9"
    )

    assert (primera, segunda) == (True, False)


async def test_un_pending_anterior_al_approved_aplicado_se_ignora() -> None:
    """Caso 13."""
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-9")
    repositorio, caso = _con(plantilla)
    await caso.ejecutar(
        estado="APPROVED", momento=AHORA, es_evento=True, meta_plantilla_id="meta-9"
    )

    cambio = await caso.ejecutar(
        estado="PENDING",
        momento=AHORA - timedelta(minutes=10),
        es_evento=True,
        meta_plantilla_id="meta-9",
    )

    assert cambio is False
    assert repositorio.filas[plantilla.id].estado_aprobacion is EstadoDeAprobacion.APROBADA


async def test_se_encuentra_por_nombre_e_idioma_y_se_vincula_el_id_de_meta() -> None:
    plantilla = _plantilla(EstadoDeAprobacion.SIN_ENVIAR)
    repositorio, caso = _con(plantilla)

    await caso.ejecutar(
        estado="APPROVED",
        momento=AHORA,
        es_evento=True,
        meta_plantilla_id="meta-77",
        nombre="turno_confirmado",
        idioma="es_AR",
    )

    guardada = repositorio.filas[plantilla.id]
    assert guardada.meta_plantilla_id == "meta-77"
    assert guardada.estado_aprobacion is EstadoDeAprobacion.APROBADA


async def test_una_plantilla_que_no_es_nuestra_no_cambia_nada() -> None:
    repositorio, caso = _con(_plantilla(meta_plantilla_id="meta-9"))

    cambio = await caso.ejecutar(
        estado="APPROVED", momento=AHORA, es_evento=True, meta_plantilla_id="otra"
    )

    assert cambio is False
    assert repositorio.guardados == 0


async def test_un_valor_desconocido_no_cambia_nada_y_deja_un_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caso 18."""
    logger_nuevo(monkeypatch, modulo_plantillas)
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-9")
    repositorio, caso = _con(plantilla)

    with capture_logs() as registros:
        cambio = await caso.ejecutar(
            estado="INVENTADO", momento=AHORA, es_evento=True, meta_plantilla_id="meta-9"
        )

    assert cambio is False
    assert repositorio.filas[plantilla.id].estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert any(r["event"] == "plantilla_estado_meta_desconocido" for r in registros)


async def test_unarchived_no_decide_un_estado() -> None:
    plantilla = _plantilla(EstadoDeAprobacion.SIN_ENVIAR, meta_plantilla_id="meta-9")
    repositorio, caso = _con(plantilla)

    cambio = await caso.ejecutar(
        estado="UNARCHIVED", momento=AHORA, es_evento=True, meta_plantilla_id="meta-9"
    )

    assert cambio is False
    assert repositorio.guardados == 0


async def test_un_borrado_en_meta_deja_sin_enviar_y_olvida_el_id() -> None:
    plantilla = _plantilla(EstadoDeAprobacion.APROBADA, meta_plantilla_id="meta-9")
    repositorio, caso = _con(plantilla)

    await caso.ejecutar(estado="DELETED", momento=AHORA, es_evento=True, meta_plantilla_id="meta-9")

    guardada = repositorio.filas[plantilla.id]
    assert guardada.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR
    assert guardada.meta_plantilla_id is None


async def test_un_estado_del_nodo_se_traduce_con_su_propio_vocabulario() -> None:
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-9")
    repositorio, caso = _con(plantilla)

    await caso.ejecutar(estado="PAUSED", momento=AHORA, es_evento=False, meta_plantilla_id="meta-9")

    assert repositorio.filas[plantilla.id].estado_aprobacion is EstadoDeAprobacion.PAUSADA


async def test_mismo_nombre_pero_otro_id_de_meta_no_es_nuestra_plantilla() -> None:
    """Una plantilla de Meta con el mismo nombre e idioma y otro id no se confunde con la vinculada."""
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-9")
    repositorio, caso = _con(plantilla)

    cambio = await caso.ejecutar(
        estado="APPROVED",
        momento=AHORA,
        es_evento=True,
        meta_plantilla_id="otro-id",
        nombre="turno_confirmado",
        idioma="es_AR",
    )

    assert cambio is False
    assert repositorio.filas[plantilla.id].meta_plantilla_id == "meta-9"
    assert repositorio.filas[plantilla.id].estado_aprobacion is EstadoDeAprobacion.PENDIENTE
