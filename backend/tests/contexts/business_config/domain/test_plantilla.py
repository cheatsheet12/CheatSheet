"""`PlantillaDeNotificacion` ante Meta (U6): bordes del texto, edición admisible y estado.

El agregado no habla con Meta: decide **qué ediciones se le pueden mandar** y **qué respuesta
aplica**. Sin red, sin base.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.business_config.domain.plantilla import (
    MENSAJE_BORDE_CON_VARIABLE,
    MENSAJE_EN_REVISION,
    VARIABLES_POR_CODIGO,
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
    ejemplos_de,
    variables_de,
)
from cheatsheet.contexts.business_config.domain.regla import CanalNotificacion
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

AHORA = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
CUERPO = "Hola {{nombre}}, te recordamos tu turno de {{servicio}} el {{fecha}} a las {{hora}}."


def _plantilla(
    *,
    canal: CanalNotificacion = CanalNotificacion.WHATSAPP,
    estado: EstadoDeAprobacion = EstadoDeAprobacion.SIN_ENVIAR,
    cuerpo: str = CUERPO,
    codigo: str = "recordatorio_de_turno",
    **extra: object,
) -> PlantillaDeNotificacion:
    return PlantillaDeNotificacion(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        codigo=codigo,
        canal=canal,
        idioma="es_AR",
        cuerpo=cuerpo,
        estado_aprobacion=estado,
        **extra,  # type: ignore[arg-type]
    )


def _nueva(cuerpo: str, canal: CanalNotificacion = CanalNotificacion.WHATSAPP) -> object:
    return PlantillaDeNotificacion.nueva(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        codigo="recordatorio_de_turno",
        canal=canal,
        idioma="es_AR",
        cuerpo=cuerpo,
        ahora=AHORA,
    )


# --- Nueva ---------------------------------------------------------------------------------


def test_una_plantilla_nueva_de_whatsapp_nace_sin_enviar_con_el_codigo_como_nombre() -> None:
    plantilla = _nueva(CUERPO)

    assert isinstance(plantilla, PlantillaDeNotificacion)
    assert plantilla.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR
    assert plantilla.nombre_en_meta == "recordatorio_de_turno"
    assert plantilla.meta_plantilla_id is None


def test_una_plantilla_nueva_de_email_no_pide_aprobacion_ni_nombre_en_meta() -> None:
    plantilla = _nueva("{{nombre}}, te esperamos.", CanalNotificacion.EMAIL)

    assert isinstance(plantilla, PlantillaDeNotificacion)
    assert plantilla.estado_aprobacion is EstadoDeAprobacion.NO_APLICA
    assert plantilla.nombre_en_meta is None


# --- Caso 4: bordes del texto ----------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        "{{nombre}}, te esperamos el {{fecha}}.",
        "Te esperamos el {{fecha}} a las {{hora}}",
        "  {{nombre}} te esperamos.",
    ],
)
def test_un_cuerpo_de_whatsapp_que_empieza_o_termina_con_variable_se_rechaza(cuerpo: str) -> None:
    with pytest.raises(EntradaInvalida, match="empiece o termine con una variable"):
        _nueva(cuerpo)
    with pytest.raises(EntradaInvalida) as salida:
        _plantilla().editar(cuerpo, AHORA)
    assert str(salida.value) == MENSAJE_BORDE_CON_VARIABLE


def test_un_cuerpo_de_email_puede_empezar_con_variable() -> None:
    plantilla = _plantilla(canal=CanalNotificacion.EMAIL, estado=EstadoDeAprobacion.NO_APLICA)

    plantilla.editar("{{nombre}}, te esperamos el {{fecha}}", AHORA)

    assert plantilla.cuerpo.startswith("{{nombre}}")


def test_cargar_una_fila_vieja_que_termina_en_variable_no_levanta() -> None:
    """Una editada antes de U6 sigue leyéndose: la pantalla le muestra el motivo de Meta."""
    plantilla = _plantilla(cuerpo="Pagá acá: {{link}}", codigo="cobro_generado")

    assert plantilla.cuerpo.endswith("{{link}}")


# --- Casos 5 y 6: edición admisible ante Meta ---------------------------------------------------


def test_editar_una_pendiente_se_rechaza_con_la_frase() -> None:
    plantilla = _plantilla(estado=EstadoDeAprobacion.PENDIENTE)

    with pytest.raises(EntradaInvalida) as salida:
        plantilla.editar("Hola {{nombre}}, cambió el texto.", AHORA)

    assert str(salida.value) == MENSAJE_EN_REVISION
    assert plantilla.cuerpo == CUERPO


def test_editar_una_aprobada_enviada_hace_tres_horas_se_rechaza_con_la_hora() -> None:
    plantilla = _plantilla(
        estado=EstadoDeAprobacion.APROBADA, enviada_a_meta_en=AHORA - timedelta(hours=3)
    )

    with pytest.raises(EntradaInvalida) as salida:
        plantilla.editar("Hola {{nombre}}, cambió el texto.", AHORA)

    # 13:00Z - 3 h + 24 h = 10:00Z del 16/10 = 07:00 en Argentina.
    assert "16/10/2026" in str(salida.value)
    assert "07:00" in str(salida.value)
    assert plantilla.cuerpo == CUERPO


def test_editar_una_aprobada_enviada_hace_veinticinco_horas_se_puede() -> None:
    plantilla = _plantilla(
        estado=EstadoDeAprobacion.APROBADA, enviada_a_meta_en=AHORA - timedelta(hours=25)
    )

    plantilla.editar("Hola {{nombre}}, cambió el texto.", AHORA)

    assert plantilla.cuerpo == "Hola {{nombre}}, cambió el texto."
    assert plantilla.updated_at == AHORA


@pytest.mark.parametrize(
    "estado",
    [
        EstadoDeAprobacion.SIN_ENVIAR,
        EstadoDeAprobacion.RECHAZADA,
        EstadoDeAprobacion.PAUSADA,
        EstadoDeAprobacion.DESHABILITADA,
    ],
)
def test_editar_en_los_demas_estados_no_tiene_limite_y_no_toca_el_estado(
    estado: EstadoDeAprobacion,
) -> None:
    plantilla = _plantilla(estado=estado, enviada_a_meta_en=AHORA - timedelta(minutes=1))

    plantilla.editar("Hola {{nombre}}, cambió el texto.", AHORA)

    assert plantilla.estado_aprobacion is estado


def test_editable_desde_solo_existe_para_una_aprobada_enviada() -> None:
    enviada = AHORA - timedelta(hours=3)

    assert _plantilla(
        estado=EstadoDeAprobacion.APROBADA, enviada_a_meta_en=enviada
    ).editable_desde == enviada + timedelta(hours=24)
    assert _plantilla(estado=EstadoDeAprobacion.APROBADA).editable_desde is None
    assert _plantilla(enviada_a_meta_en=enviada).editable_desde is None


# --- Respuesta de Meta ---------------------------------------------------------------------------


def test_aplicar_una_respuesta_de_meta_guarda_estado_motivo_detalle_y_categoria() -> None:
    plantilla = _plantilla(estado=EstadoDeAprobacion.PENDIENTE)

    cambio = plantilla.aplicar_respuesta_de_meta(
        EstadoDeAprobacion.RECHAZADA,
        motivo="PROMOTIONAL",
        detalle="Quitá el tono comercial.",
        momento=AHORA,
        categoria="MARKETING",
    )

    assert cambio is True
    assert plantilla.estado_aprobacion is EstadoDeAprobacion.RECHAZADA
    assert plantilla.motivo_meta == "PROMOTIONAL"
    assert plantilla.detalle_meta == "Quitá el tono comercial."
    assert plantilla.categoria_en_meta == "MARKETING"
    assert plantilla.estado_meta_en == AHORA


def test_el_mismo_estado_dos_veces_es_un_solo_efecto() -> None:
    plantilla = _plantilla(estado=EstadoDeAprobacion.PENDIENTE)
    plantilla.aplicar_respuesta_de_meta(
        EstadoDeAprobacion.APROBADA, motivo=None, detalle=None, momento=AHORA
    )

    de_nuevo = plantilla.aplicar_respuesta_de_meta(
        EstadoDeAprobacion.APROBADA, motivo=None, detalle=None, momento=AHORA
    )

    assert de_nuevo is False
    assert plantilla.estado_aprobacion is EstadoDeAprobacion.APROBADA


def test_un_estado_mas_viejo_que_el_aplicado_se_ignora() -> None:
    plantilla = _plantilla(estado=EstadoDeAprobacion.PENDIENTE)
    plantilla.aplicar_respuesta_de_meta(
        EstadoDeAprobacion.APROBADA, motivo=None, detalle=None, momento=AHORA
    )

    cambio = plantilla.aplicar_respuesta_de_meta(
        EstadoDeAprobacion.PENDIENTE,
        motivo=None,
        detalle=None,
        momento=AHORA - timedelta(minutes=5),
    )

    assert cambio is False
    assert plantilla.estado_aprobacion is EstadoDeAprobacion.APROBADA
    assert plantilla.estado_meta_en == AHORA


def test_aprobar_limpia_el_motivo_del_rechazo_anterior() -> None:
    plantilla = _plantilla(
        estado=EstadoDeAprobacion.RECHAZADA, motivo_meta="PROMOTIONAL", detalle_meta="viejo"
    )

    plantilla.aplicar_respuesta_de_meta(
        EstadoDeAprobacion.APROBADA, motivo=None, detalle=None, momento=AHORA
    )

    assert plantilla.motivo_meta is None
    assert plantilla.detalle_meta is None


def test_sin_enviar_olvida_el_id_de_meta_para_que_la_proxima_creacion_version_el_nombre() -> None:
    plantilla = _plantilla(
        estado=EstadoDeAprobacion.APROBADA,
        meta_plantilla_id="555",
        enviada_a_meta_en=AHORA - timedelta(days=2),
    )

    plantilla.aplicar_respuesta_de_meta(
        EstadoDeAprobacion.SIN_ENVIAR, motivo=None, detalle=None, momento=AHORA
    )

    assert plantilla.meta_plantilla_id is None
    assert plantilla.nombre_para_crear() == "recordatorio_de_turno_v2"


def test_registrar_el_envio_guarda_id_nombre_y_momento() -> None:
    plantilla = _plantilla()

    plantilla.registrar_envio_a_meta(
        meta_plantilla_id="555", nombre_en_meta="recordatorio_de_turno_v2", momento=AHORA
    )

    assert plantilla.meta_plantilla_id == "555"
    assert plantilla.nombre_en_meta == "recordatorio_de_turno_v2"
    assert plantilla.enviada_a_meta_en == AHORA


def test_marcar_sin_enviar_deja_el_detalle_a_la_vista() -> None:
    plantilla = _plantilla(estado=EstadoDeAprobacion.RECHAZADA, motivo_meta="SCAM")

    plantilla.marcar_sin_enviar("WhatsApp no está conectado", AHORA)

    assert plantilla.estado_aprobacion is EstadoDeAprobacion.SIN_ENVIAR
    assert plantilla.detalle_meta == "WhatsApp no está conectado"
    assert plantilla.motivo_meta is None


# --- Nombre en Meta ---------------------------------------------------------------------------------


def test_la_primera_creacion_usa_el_nombre_guardado() -> None:
    assert _plantilla(nombre_en_meta="recordatorio_de_turno").nombre_para_crear() == (
        "recordatorio_de_turno"
    )


def test_una_deshabilitada_se_vuelve_a_crear_con_nombre_versionado() -> None:
    plantilla = _plantilla(
        estado=EstadoDeAprobacion.DESHABILITADA,
        nombre_en_meta="recordatorio_de_turno",
        meta_plantilla_id="555",
    )

    assert plantilla.nombre_para_crear() == "recordatorio_de_turno_v2"


@pytest.mark.parametrize(
    ("actual", "siguiente"),
    [
        ("recordatorio_de_turno", "recordatorio_de_turno_v2"),
        ("recordatorio_de_turno_v2", "recordatorio_de_turno_v3"),
        ("recordatorio_de_turno_v9", "recordatorio_de_turno_v10"),
    ],
)
def test_siguiente_nombre_incrementa_el_sufijo(actual: str, siguiente: str) -> None:
    assert _plantilla(nombre_en_meta=actual).siguiente_nombre() == siguiente


# --- Ejemplos ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", sorted(VARIABLES_POR_CODIGO))
def test_hay_un_ejemplo_ficticio_por_cada_variable_de_cada_codigo(codigo: str) -> None:
    ejemplos = ejemplos_de(codigo)

    assert set(ejemplos) == VARIABLES_POR_CODIGO[codigo]
    assert all(valor.strip() for valor in ejemplos.values())


def test_ejemplos_de_un_codigo_desconocido_es_vacio() -> None:
    assert ejemplos_de("no_existe") == {}


def test_los_ejemplos_son_datos_ficticios() -> None:
    texto = " ".join(ejemplos_de("recordatorio_de_cobro").values())

    assert "example.com" in texto
    assert variables_de("{{x}}") == frozenset({"x"})


# --- RN-04 -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estado", "usable"),
    [
        (EstadoDeAprobacion.APROBADA, True),
        (EstadoDeAprobacion.SIN_ENVIAR, False),
        (EstadoDeAprobacion.PENDIENTE, False),
        (EstadoDeAprobacion.RECHAZADA, False),
        (EstadoDeAprobacion.PAUSADA, False),
        (EstadoDeAprobacion.DESHABILITADA, False),
    ],
)
def test_solo_una_aprobada_se_puede_usar_por_whatsapp(
    estado: EstadoDeAprobacion, usable: bool
) -> None:
    assert _plantilla(estado=estado).puede_usarse is usable
