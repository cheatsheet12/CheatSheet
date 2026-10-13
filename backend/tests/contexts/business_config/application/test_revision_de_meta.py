"""Editar una plantilla de WhatsApp: se manda a Meta antes de guardarla (U6, casos 1, 5 a 10, 20 y 23).

La respuesta de Meta decide si la edición existe: se llama dentro del caso de uso y, si Meta
refuta o no responde, **no se guarda nada**. Sin red: el puerto es un doble programable.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from cheatsheet.contexts.business_config.application.errors import (
    MetaNoConectada,
    MetaNoDisponible,
    MetaRechazoLaPlantilla,
)
from cheatsheet.contexts.business_config.application.plantillas import MOTIVO_SOLO_ADMIN
from cheatsheet.contexts.business_config.application.revision_de_meta import DETALLE_SIN_CONECTAR
from cheatsheet.contexts.business_config.domain.plantilla import (
    MENSAJE_BORDE_CON_VARIABLE,
    MENSAJE_EN_REVISION,
    MENSAJE_VARIABLE_INVALIDA,
    EstadoDeAprobacion,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.errors import EntradaInvalida, OperacionNoPermitida
from cheatsheet.shared.roles import RolUsuario

from .dobles_plantillas import RevisionDeMetaFalsa
from .escena_revision import (
    AHORA,
    APROBADA,
    CUERPO_NUEVO,
    CUERPO_VIEJO,
    PENDIENTE,
    Escena,
    una_plantilla,
)

pytestmark = pytest.mark.asyncio

# --- Caso 1: guardar manda la plantilla a Meta --------------------------------------------------


async def test_guardar_una_sin_enviar_la_crea_en_meta_con_un_ejemplo_por_variable_usada() -> None:
    escena = Escena(una_plantilla(), RevisionDeMetaFalsa(respuestas=[PENDIENTE]))

    resultado = await escena.editar()

    ((nombre, idioma, cuerpo, ejemplos),) = escena.revision.creaciones
    assert (nombre, idioma, cuerpo) == ("turno_confirmado", "es_AR", CUERPO_NUEVO)
    assert set(ejemplos) == {"nombre", "fecha", "hora", "recurso"}
    assert ejemplos["nombre"] == "Ana"
    assert resultado.estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert escena.guardada.cuerpo == CUERPO_NUEVO
    assert escena.guardada.meta_plantilla_id == "meta-9"
    assert escena.guardada.enviada_a_meta_en == AHORA
    assert escena.guardada.categoria_en_meta == "UTILITY"
    assert [e.accion for e in escena.publicador.eventos] == ["editar_plantilla"]  # type: ignore[attr-defined]


async def test_si_meta_aprueba_en_el_acto_queda_aprobada() -> None:
    escena = Escena(una_plantilla(), RevisionDeMetaFalsa(respuestas=[APROBADA]))

    resultado = await escena.editar()

    assert resultado.estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert resultado.puede_usarse


# --- Caso 23: solo las variables que el cuerpo usa ---------------------------------------------------


async def test_los_ejemplos_son_solo_los_de_las_variables_que_el_cuerpo_usa() -> None:
    escena = Escena(una_plantilla(), RevisionDeMetaFalsa(respuestas=[PENDIENTE]))

    await escena.editar("Hola {{nombre}}, te esperamos. Gracias.")

    assert set(escena.revision.creaciones[0][3]) == {"nombre"}


# --- Casos 5 y 6: edición admisible --------------------------------------------------------------------


async def test_editar_una_pendiente_se_rechaza_sin_llamar_a_meta() -> None:
    escena = Escena(una_plantilla(EstadoDeAprobacion.PENDIENTE, meta_plantilla_id="meta-9"))

    with pytest.raises(EntradaInvalida) as salida:
        await escena.editar()

    assert str(salida.value) == MENSAJE_EN_REVISION
    assert escena.revision.creaciones == []
    assert escena.revision.ediciones == []
    assert escena.guardada.cuerpo == CUERPO_VIEJO


async def test_editar_una_aprobada_enviada_hace_tres_horas_no_llama_a_meta() -> None:
    escena = Escena(
        una_plantilla(
            EstadoDeAprobacion.APROBADA,
            meta_plantilla_id="meta-9",
            enviada_a_meta_en=AHORA - timedelta(hours=3),
        )
    )

    with pytest.raises(EntradaInvalida, match="una vez cada 24 horas"):
        await escena.editar()

    assert escena.revision.ediciones == []


async def test_editar_una_aprobada_enviada_hace_veinticinco_horas_manda_los_componentes_completos() -> (
    None
):
    escena = Escena(
        una_plantilla(
            EstadoDeAprobacion.APROBADA,
            meta_plantilla_id="meta-9",
            enviada_a_meta_en=AHORA - timedelta(hours=25),
        ),
        RevisionDeMetaFalsa(respuestas=[PENDIENTE]),
    )

    resultado = await escena.editar()

    ((meta_id, cuerpo, ejemplos),) = escena.revision.ediciones
    assert (meta_id, cuerpo) == ("meta-9", CUERPO_NUEVO)
    assert set(ejemplos) == {"nombre", "fecha", "hora", "recurso"}
    assert escena.revision.creaciones == []
    assert resultado.estado_aprobacion is EstadoDeAprobacion.PENDIENTE
    assert resultado.enviada_a_meta_en == AHORA


# --- Caso 7 y 8: Meta refuta o no contesta -> nada guardado ------------------------------------------


async def test_si_meta_refuta_no_se_guarda_nada_y_el_error_lleva_su_texto() -> None:
    escena = Escena(
        una_plantilla(),
        RevisionDeMetaFalsa(respuestas=[MetaRechazoLaPlantilla("Texto de Meta sobre el cuerpo")]),
    )

    with pytest.raises(MetaRechazoLaPlantilla) as salida:
        await escena.editar()

    assert str(salida.value) == "Texto de Meta sobre el cuerpo"
    assert escena.guardada.cuerpo == CUERPO_VIEJO
    assert escena.guardada.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR
    assert escena.repositorio.guardados == 0
    assert escena.publicador.eventos == []


async def test_si_meta_no_responde_no_se_guarda_nada_y_hay_un_solo_pedido() -> None:
    escena = Escena(
        una_plantilla(), RevisionDeMetaFalsa(respuestas=[MetaNoDisponible("lento", incierto=True)])
    )

    with pytest.raises(MetaNoDisponible) as salida:
        await escena.editar()

    assert salida.value.incierto is True
    assert len(escena.revision.creaciones) == 1
    assert escena.repositorio.guardados == 0


# --- Caso 9: nombre en uso ---------------------------------------------------------------------------------


async def test_nombre_en_uso_reintenta_una_vez_con_el_nombre_versionado_y_lo_guarda() -> None:
    escena = Escena(
        una_plantilla(),
        RevisionDeMetaFalsa(
            respuestas=[MetaRechazoLaPlantilla("ya existe", nombre_en_uso=True), PENDIENTE]
        ),
    )

    await escena.editar()

    assert [pedido[0] for pedido in escena.revision.creaciones] == [
        "turno_confirmado",
        "turno_confirmado_v2",
    ]
    assert escena.guardada.nombre_en_meta == "turno_confirmado_v2"


async def test_nombre_en_uso_dos_veces_se_rinde_y_no_guarda() -> None:
    escena = Escena(
        una_plantilla(),
        RevisionDeMetaFalsa(
            respuestas=[
                MetaRechazoLaPlantilla("ya existe", nombre_en_uso=True),
                MetaRechazoLaPlantilla("ya existe v2", nombre_en_uso=True),
            ]
        ),
    )

    with pytest.raises(MetaRechazoLaPlantilla):
        await escena.editar()

    assert len(escena.revision.creaciones) == 2
    assert escena.repositorio.guardados == 0


# --- Caso 10: deshabilitada o borrada -> se crea de nuevo ---------------------------------------------------


async def test_una_deshabilitada_se_crea_de_nuevo_con_nombre_versionado_y_nunca_se_edita() -> None:
    escena = Escena(
        una_plantilla(EstadoDeAprobacion.DESHABILITADA, meta_plantilla_id="meta-viejo"),
        RevisionDeMetaFalsa(respuestas=[PENDIENTE]),
    )

    await escena.editar()

    assert escena.revision.ediciones == []
    assert escena.revision.creaciones[0][0] == "turno_confirmado_v2"
    assert escena.guardada.meta_plantilla_id == "meta-9"


async def test_una_borrada_en_meta_queda_sin_enviar_y_reenviarla_crea_con_nombre_versionado() -> (
    None
):
    plantilla = una_plantilla(
        EstadoDeAprobacion.APROBADA,
        meta_plantilla_id="meta-viejo",
        enviada_a_meta_en=AHORA - timedelta(days=5),
    )
    plantilla.aplicar_respuesta_de_meta(
        EstadoDeAprobacion.SIN_ENVIAR, motivo=None, detalle=None, momento=AHORA - timedelta(days=1)
    )
    escena = Escena(plantilla, RevisionDeMetaFalsa(respuestas=[PENDIENTE]))

    await escena.enviar()

    assert escena.revision.ediciones == []
    assert escena.revision.creaciones[0][0] == "turno_confirmado_v2"


# --- Caso 20: WhatsApp sin conectar ---------------------------------------------------------------------------


async def test_sin_whatsapp_conectado_guarda_el_texto_y_queda_sin_enviar_con_el_detalle() -> None:
    escena = Escena(
        una_plantilla(EstadoDeAprobacion.RECHAZADA, motivo_meta="SCAM"),
        RevisionDeMetaFalsa(respuestas=[MetaNoConectada("sin cuenta")]),
    )

    resultado = await escena.editar()

    assert resultado.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR
    assert resultado.detalle_meta == DETALLE_SIN_CONECTAR == "WhatsApp no está conectado"
    assert resultado.motivo_meta is None
    assert escena.guardada.cuerpo == CUERPO_NUEVO


# --- Validaciones de dominio y de rol ------------------------------------------------------------------------


async def test_una_variable_desconocida_se_rechaza_antes_de_llamar_a_meta() -> None:
    escena = Escena(una_plantilla())

    with pytest.raises(EntradaInvalida) as salida:
        await escena.editar("Hola {{nombre}}, tu saldo es {{saldo}}. Gracias.")

    assert str(salida.value) == MENSAJE_VARIABLE_INVALIDA
    assert escena.revision.creaciones == []


async def test_un_cuerpo_que_termina_en_variable_se_rechaza_antes_de_llamar_a_meta() -> None:
    escena = Escena(una_plantilla())

    with pytest.raises(EntradaInvalida) as salida:
        await escena.editar("Hola, tu turno es el {{fecha}}")

    assert str(salida.value) == MENSAJE_BORDE_CON_VARIABLE
    assert escena.revision.creaciones == []


async def test_una_plantilla_de_email_se_guarda_sin_tocar_meta() -> None:
    escena = Escena(una_plantilla(EstadoDeAprobacion.NO_APLICA, canal=CanalNotificacion.EMAIL))

    resultado = await escena.editar("{{nombre}}, te esperamos el {{fecha}}")

    assert resultado.cuerpo.startswith("{{nombre}}")
    assert escena.revision.creaciones == []
    assert escena.revision.ediciones == []
    assert escena.guardada.estado_aprobacion is EstadoDeAprobacion.NO_APLICA


async def test_solo_el_administrador_edita() -> None:
    escena = Escena(una_plantilla())

    with pytest.raises(OperacionNoPermitida) as salida:
        await escena.editar(rol=RolUsuario.OPERADOR)

    assert str(salida.value) == MOTIVO_SOLO_ADMIN
    assert escena.revision.creaciones == []


async def test_una_plantilla_inexistente_se_rechaza() -> None:
    escena = Escena(una_plantilla())
    escena.plantilla = una_plantilla()  # otro id: no está en el repositorio

    with pytest.raises(EntradaInvalida, match="no existe"):
        await escena.editar()
