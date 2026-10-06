"""`ConciliarPlantillasConMeta` (U6, casos 8, 16 y 17): la columna vertebral de la sincronización.

El webhook de plantillas no admite override por cuenta, así que la conciliación es la red de
seguridad: siembra, manda lo que falta, lee `estados()` y aplica cada una. Sin red.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.business_config.application.conciliacion import (
    DETALLE_DIVERGENTE,
    ConciliarPlantillasConMeta,
    ResumenDeConciliacion,
)
from cheatsheet.contexts.business_config.application.errors import (
    MetaNoConectada,
    MetaNoDisponible,
    MetaRechazoLaPlantilla,
)
from cheatsheet.contexts.business_config.application.plantillas import DE_FABRICA
from cheatsheet.contexts.business_config.application.ports import EstadoEnMeta, RespuestaDeMeta
from cheatsheet.contexts.business_config.application.revision_de_meta import DETALLE_SIN_CONECTAR
from cheatsheet.contexts.business_config.domain.plantilla import (
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.empresa import EmpresaId
from structlog.testing import capture_logs

from .dobles_plantillas import RepositorioPlantillasEnMemoria, RevisionDeMetaFalsa

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
AHORA = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
CUERPO = "Hola {{nombre}}, te recordamos tu turno de {{servicio}} el {{fecha}} a las {{hora}}."


def _plantilla(
    estado: EstadoDeAprobacion = EstadoDeAprobacion.SIN_ENVIAR,
    *,
    codigo: str = "recordatorio_de_turno",
    cuerpo: str = CUERPO,
    **extra: object,
) -> PlantillaDeNotificacion:
    return PlantillaDeNotificacion(
        id=uuid4(),
        empresa_id=EMPRESA,
        codigo=codigo,
        canal=CanalNotificacion.WHATSAPP,
        idioma="es_AR",
        cuerpo=cuerpo,
        estado_aprobacion=estado,
        nombre_en_meta=codigo,
        **extra,  # type: ignore[arg-type]
    )


def _en_meta(
    meta_id: str,
    nombre: str = "recordatorio_de_turno",
    estado: str = "APPROVED",
    **extra: object,
) -> EstadoEnMeta:
    return EstadoEnMeta(
        meta_plantilla_id=meta_id,
        nombre=nombre,
        idioma="es_AR",
        estado=estado,
        cuerpo=extra.pop("cuerpo", CUERPO),  # type: ignore[arg-type]
        **extra,  # type: ignore[arg-type]
    )


async def _conciliar(
    repositorio: RepositorioPlantillasEnMemoria, revision: RevisionDeMetaFalsa
) -> ResumenDeConciliacion:
    return await ConciliarPlantillasConMeta(repositorio, revision).ejecutar(
        empresa_id=EMPRESA, ahora=AHORA
    )


# --- Caso 16 ----------------------------------------------------------------------------------------------


async def test_una_empresa_sin_plantillas_se_siembra_y_se_crean_en_meta() -> None:
    repositorio = RepositorioPlantillasEnMemoria()
    revision = RevisionDeMetaFalsa()

    resumen = await _conciliar(repositorio, revision)

    assert resumen.sembradas == len(DE_FABRICA)
    assert resumen.enviadas == len(DE_FABRICA)
    assert resumen.interrumpida is None
    assert {pedido[0] for pedido in revision.creaciones} == set(DE_FABRICA)
    for plantilla in repositorio.filas.values():
        assert plantilla.estado_aprobacion is EstadoDeAprobacion.APROBADA
        assert plantilla.meta_plantilla_id is not None
        assert plantilla.puede_usarse


async def test_se_aplican_los_estados_que_meta_informa_a_las_ya_enviadas() -> None:
    aprobada = _plantilla(
        EstadoDeAprobacion.PENDIENTE, codigo="turno_confirmado", meta_plantilla_id="1"
    )
    rechazada = _plantilla(
        EstadoDeAprobacion.PENDIENTE, codigo="turno_cancelado", meta_plantilla_id="2"
    )
    repositorio = RepositorioPlantillasEnMemoria(aprobada, rechazada)
    revision = RevisionDeMetaFalsa(
        estados=[
            _en_meta("1", "turno_confirmado", cuerpo=aprobada.cuerpo),
            _en_meta(
                "2",
                "turno_cancelado",
                "REJECTED",
                motivo="PROMOTIONAL",
                cuerpo=rechazada.cuerpo,
            ),
        ]
    )

    resumen = await _conciliar(repositorio, revision)

    assert resumen.actualizadas == 2
    assert repositorio.filas[aprobada.id].estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert repositorio.filas[rechazada.id].estado_aprobacion is EstadoDeAprobacion.RECHAZADA
    assert repositorio.filas[rechazada.id].motivo_meta == "PROMOTIONAL"


async def test_correr_dos_veces_con_lo_mismo_no_cambia_nada() -> None:
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="1")
    repositorio = RepositorioPlantillasEnMemoria(plantilla)
    revision = RevisionDeMetaFalsa(estados=[_en_meta("1")])
    await _conciliar(repositorio, revision)

    segunda = await _conciliar(repositorio, revision)

    assert segunda.actualizadas == 0
    assert segunda.enviadas == 0


# --- Caso 17: Meta caída -----------------------------------------------------------------------------------


async def test_con_meta_caida_ninguna_fila_cambia_y_no_levanta() -> None:
    repositorio = RepositorioPlantillasEnMemoria()
    revision = RevisionDeMetaFalsa(estados=MetaNoDisponible("503"))

    resumen = await _conciliar(repositorio, revision)

    assert resumen.interrumpida == "meta_no_disponible"
    assert repositorio.filas == {}
    assert revision.creaciones == []


async def test_la_corrida_siguiente_recupera_lo_que_la_caida_dejo_pendiente() -> None:
    repositorio = RepositorioPlantillasEnMemoria()
    await _conciliar(repositorio, RevisionDeMetaFalsa(estados=MetaNoDisponible("503")))

    resumen = await _conciliar(repositorio, RevisionDeMetaFalsa())

    assert resumen.enviadas == len(DE_FABRICA)


async def test_sin_whatsapp_conectado_no_se_toca_nada() -> None:
    repositorio = RepositorioPlantillasEnMemoria()

    resumen = await _conciliar(repositorio, RevisionDeMetaFalsa(estados=MetaNoConectada("x")))

    assert resumen.interrumpida == "no_conectada"
    assert repositorio.filas == {}


async def test_si_meta_cae_a_mitad_de_las_creaciones_se_corta_y_lo_hecho_se_conserva() -> None:
    repositorio = RepositorioPlantillasEnMemoria()
    revision = RevisionDeMetaFalsa(
        respuestas=[
            RespuestaDeMeta(meta_plantilla_id="meta-a", estado="APPROVED"),  # la primera sale bien
            MetaNoDisponible("503"),
        ]
    )

    resumen = await _conciliar(repositorio, revision)

    assert resumen.enviadas == 1
    assert resumen.interrumpida == "meta_no_disponible"
    assert len(revision.creaciones) == 2  # la segunda falló y no se siguió con el resto


# --- Caso 8: creación que se perdió ---------------------------------------------------------------------------


async def test_una_creacion_cuya_respuesta_se_perdio_se_encuentra_por_nombre_sin_crear_otra() -> (
    None
):
    plantilla = _plantilla(EstadoDeAprobacion.SIN_ENVIAR)
    repositorio = RepositorioPlantillasEnMemoria(plantilla)
    revision = RevisionDeMetaFalsa(estados=[_en_meta("55", estado="PENDING")])

    resumen = await _conciliar(repositorio, revision)

    assert all(pedido[0] != "recordatorio_de_turno" for pedido in revision.creaciones)
    guardada = repositorio.filas[plantilla.id]
    assert guardada.meta_plantilla_id == "55"
    assert guardada.estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert resumen.actualizadas >= 1


async def test_un_texto_divergente_en_meta_deja_el_detalle_y_no_pisa_el_cuerpo() -> None:
    plantilla = _plantilla(EstadoDeAprobacion.APROBADA, meta_plantilla_id="1")
    repositorio = RepositorioPlantillasEnMemoria(plantilla)
    revision = RevisionDeMetaFalsa(estados=[_en_meta("1", cuerpo="Otro texto que aceptó Meta.")])

    resumen = await _conciliar(repositorio, revision)

    guardada = repositorio.filas[plantilla.id]
    assert resumen.divergentes == 1
    assert guardada.detalle_meta == DETALLE_DIVERGENTE
    assert guardada.cuerpo == CUERPO
    assert guardada.estado_aprobacion is EstadoDeAprobacion.APROBADA


async def test_cuando_el_texto_vuelve_a_coincidir_el_aviso_desaparece() -> None:
    plantilla = _plantilla(
        EstadoDeAprobacion.APROBADA, meta_plantilla_id="1", detalle_meta=DETALLE_DIVERGENTE
    )
    repositorio = RepositorioPlantillasEnMemoria(plantilla)

    await _conciliar(repositorio, RevisionDeMetaFalsa(estados=[_en_meta("1")]))

    assert repositorio.filas[plantilla.id].detalle_meta is None


async def test_la_conciliacion_no_pisa_el_detalle_que_dejo_el_webhook() -> None:
    plantilla = _plantilla(
        EstadoDeAprobacion.RECHAZADA,
        meta_plantilla_id="1",
        motivo_meta="PROMOTIONAL",
        detalle_meta="Quitá el tono comercial.",
    )
    repositorio = RepositorioPlantillasEnMemoria(plantilla)

    await _conciliar(repositorio, RevisionDeMetaFalsa(estados=[_en_meta("1", estado="REJECTED")]))

    guardada = repositorio.filas[plantilla.id]
    assert guardada.detalle_meta == "Quitá el tono comercial."
    assert guardada.motivo_meta == "PROMOTIONAL"


# --- Rechazos y casos de borde -----------------------------------------------------------------------------------


async def test_si_meta_refuta_una_la_deja_sin_enviar_con_su_texto_y_sigue_con_las_demas() -> None:
    repositorio = RepositorioPlantillasEnMemoria()
    revision = RevisionDeMetaFalsa(respuestas=[MetaRechazoLaPlantilla("Texto de Meta")])

    resumen = await _conciliar(repositorio, revision)

    assert resumen.enviadas == len(DE_FABRICA) - 1
    rechazadas = [una for una in repositorio.filas.values() if una.detalle_meta == "Texto de Meta"]
    assert len(rechazadas) == 1
    assert rechazadas[0].estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR


async def test_una_sin_enviar_refutada_antes_no_se_reintenta_cada_corrida() -> None:
    plantilla = _plantilla(detalle_meta="Texto de Meta")
    repositorio = RepositorioPlantillasEnMemoria(plantilla)
    revision = RevisionDeMetaFalsa()

    await _conciliar(repositorio, revision)

    assert all(pedido[0] != "recordatorio_de_turno" for pedido in revision.creaciones)


async def test_una_sin_enviar_por_no_estar_conectado_se_reintenta() -> None:
    plantilla = _plantilla(detalle_meta=DETALLE_SIN_CONECTAR)
    repositorio = RepositorioPlantillasEnMemoria(plantilla)
    revision = RevisionDeMetaFalsa()

    await _conciliar(repositorio, revision)

    assert any(pedido[0] == "recordatorio_de_turno" for pedido in revision.creaciones)
    assert repositorio.filas[plantilla.id].detalle_meta is None


async def test_una_con_texto_viejo_que_termina_en_variable_no_se_manda() -> None:
    plantilla = _plantilla(cuerpo="Pagá acá: {{fecha}}")
    repositorio = RepositorioPlantillasEnMemoria(plantilla)
    revision = RevisionDeMetaFalsa()

    await _conciliar(repositorio, revision)

    assert all(pedido[0] != "recordatorio_de_turno" for pedido in revision.creaciones)
    assert repositorio.filas[plantilla.id].estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR


async def test_una_plantilla_con_id_que_meta_ya_no_lista_queda_como_esta() -> None:
    plantilla = _plantilla(EstadoDeAprobacion.APROBADA, meta_plantilla_id="1")
    repositorio = RepositorioPlantillasEnMemoria(plantilla)

    await _conciliar(repositorio, RevisionDeMetaFalsa(estados=[]))

    assert repositorio.filas[plantilla.id].estado_aprobacion is EstadoDeAprobacion.APROBADA


async def test_un_estado_desconocido_no_cambia_nada_y_deja_un_log() -> None:
    plantilla = _plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="1")
    repositorio = RepositorioPlantillasEnMemoria(plantilla)

    with capture_logs() as registros:
        await _conciliar(
            repositorio, RevisionDeMetaFalsa(estados=[_en_meta("1", estado="INVENTADO")])
        )

    assert repositorio.filas[plantilla.id].estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert any(r["event"] == "plantilla_estado_meta_desconocido" for r in registros)
