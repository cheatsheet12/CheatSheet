"""HS-T2 RN-04 — los textos de fuera de horario y la regla «ya avisado» (casos 34, T9)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cheatsheet.contexts.conversational.domain.conversacion import (
    MENSAJE_DERIVACION,
    DireccionMensaje,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.fuera_de_horario import (
    AtencionDelNegocio,
    PoliticaFueraDeHorario,
    aviso_de_derivacion,
    cuando_se_atiende,
    mensaje_fuera_de_horario,
    posdata_fuera_de_horario,
    ya_avisado,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA


def _local(dia: int, hora: int, minuto: int = 0, mes: int = 10) -> datetime:
    return datetime(2026, mes, dia, hora, minuto, tzinfo=ZONA_ARGENTINA)


def _cerrada(apertura: datetime | None) -> AtencionDelNegocio:
    return AtencionDelNegocio(
        abierto=False,
        politica=PoliticaFueraDeHorario.MENSAJE_FIJO,
        proxima_apertura=apertura,
        cerrado_desde=_local(5, 19),
    )


# --------------------------------------------------------------------- caso 34


def test_el_domingo_a_la_noche_la_apertura_del_lunes_es_manana_no_hoy() -> None:
    # Domingo 04/10 22:30 en Argentina = lunes 05/10 01:30Z: en UTC ya es «hoy».
    ahora = datetime(2026, 10, 5, 1, 30, tzinfo=UTC)

    assert cuando_se_atiende(_local(5, 9), ahora) == "mañana a las 09:00"


def test_el_mismo_dia_es_hoy_tambien_en_el_hueco_de_un_horario_cortado() -> None:
    assert cuando_se_atiende(_local(5, 9), _local(5, 8)) == "hoy a las 09:00"
    assert cuando_se_atiende(_local(5, 16), _local(5, 13, 30)) == "hoy a las 16:00"


def test_cualquier_otra_fecha_lleva_el_dia_y_la_fecha() -> None:
    assert cuando_se_atiende(_local(12, 9), _local(9, 20)) == "el lunes 12/10 a las 09:00"
    # Con el 12/10 sin atención, la apertura salta al martes.
    assert cuando_se_atiende(_local(13, 9), _local(10, 20)) == "el martes 13/10 a las 09:00"


def test_aunque_falte_mas_de_una_semana_la_fecha_desambigua() -> None:
    assert cuando_se_atiende(_local(26, 9), _local(5, 20)) == "el lunes 26/10 a las 09:00"


def test_la_apertura_se_dice_en_hora_argentina_aunque_llegue_en_utc() -> None:
    apertura = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)  # lunes 09:00 en Argentina

    assert cuando_se_atiende(apertura, _local(9, 20)) == "el lunes 12/10 a las 09:00"


def test_el_aviso_de_derivacion_agrega_desde_cuando_atiende_un_asesor() -> None:
    texto = aviso_de_derivacion(_cerrada(_local(12, 9)), _local(9, 20))

    assert texto == (
        f"{MENSAJE_DERIVACION} Ahora estamos fuera del horario de atención: "
        "un asesor te va a responder a partir del lunes 12/10 a las 09:00."
    )


def test_el_aviso_de_derivacion_con_hoy_y_con_manana() -> None:
    assert aviso_de_derivacion(_cerrada(_local(5, 16)), _local(5, 13, 30)).endswith(
        "a partir de hoy a las 16:00."
    )
    assert aviso_de_derivacion(_cerrada(_local(6, 9)), _local(5, 20)).endswith(
        "a partir de mañana a las 09:00."
    )


def test_el_mensaje_fijo_dice_cuando_se_atiende_de_nuevo() -> None:
    texto = mensaje_fuera_de_horario(_cerrada(_local(6, 9)), _local(5, 20))

    assert texto == (
        "Hola, gracias por escribirnos. En este momento estamos fuera del horario de atención. "
        "Atendemos de nuevo mañana a las 09:00: escribinos a partir de ese momento y te "
        "respondemos."
    )


def test_la_posdata_de_una_respuesta_a_un_dialogo() -> None:
    texto = posdata_fuera_de_horario(_cerrada(_local(6, 9)), _local(5, 20))

    assert texto == (
        "Te recordamos que ahora estamos fuera del horario de atención; "
        "atendemos de nuevo mañana a las 09:00."
    )


def test_sin_apertura_cada_texto_usa_su_variante_sin_fecha() -> None:
    atencion, ahora = _cerrada(None), _local(5, 20)

    assert aviso_de_derivacion(atencion, ahora) == (
        f"{MENSAJE_DERIVACION} Ahora estamos fuera del horario de atención: "
        "un asesor te va a responder cuando retomemos la atención."
    )
    assert mensaje_fuera_de_horario(atencion, ahora) == (
        "Hola, gracias por escribirnos. En este momento estamos fuera del horario de atención "
        "y todavía no tenemos fecha de regreso. Escribinos más adelante y te respondemos."
    )
    assert posdata_fuera_de_horario(atencion, ahora) == (
        "Te recordamos que ahora estamos fuera del horario de atención."
    )


# --------------------------------------------------------------------- T9: ya avisado


def _saliente(momento: datetime, origen: OrigenDelMensaje) -> Mensaje:
    return Mensaje(
        id=uuid4(),
        conversacion_id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        direccion=DireccionMensaje.SALIENTE,
        tipo_contenido=TipoContenido.TEXTO,
        contenido="texto",
        momento=momento,
        origen=origen,
    )


def _entrante(momento: datetime) -> Mensaje:
    return Mensaje(
        id=uuid4(),
        conversacion_id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        direccion=DireccionMensaje.ENTRANTE,
        tipo_contenido=TipoContenido.TEXTO,
        contenido="hola",
        momento=momento,
    )


def test_ya_avisado_cuenta_un_saliente_del_agente_desde_el_cierre() -> None:
    cierre = _local(5, 19)

    assert ya_avisado([_saliente(_local(5, 19, 5), OrigenDelMensaje.AGENTE)], cierre)
    # En el borde exacto cuenta (`>=`).
    assert ya_avisado([_saliente(cierre, OrigenDelMensaje.AGENTE)], cierre)


def test_ya_avisado_ignora_lo_anterior_al_cierre_y_lo_que_no_es_del_agente() -> None:
    cierre = _local(5, 19)

    assert not ya_avisado([], cierre)
    assert not ya_avisado([_saliente(_local(5, 18, 59), OrigenDelMensaje.AGENTE)], cierre)
    assert not ya_avisado([_saliente(_local(5, 20), OrigenDelMensaje.SISTEMA)], cierre)
    assert not ya_avisado([_saliente(_local(5, 20), OrigenDelMensaje.OPERADOR)], cierre)
    assert not ya_avisado([_entrante(_local(5, 20))], cierre)


def test_un_aviso_que_no_salio_no_cuenta_como_ya_avisado() -> None:
    """Si WhatsApp rechazó el mensaje, el cliente nunca se enteró: el próximo reintenta."""
    fallido = _saliente(_local(5, 20), OrigenDelMensaje.AGENTE)
    fallido.estado_entrega = EstadoEntrega.FALLIDO
    enviado = _saliente(_local(5, 20), OrigenDelMensaje.AGENTE)
    enviado.estado_entrega = EstadoEntrega.ENVIADO

    assert not ya_avisado([fallido], _local(5, 19))
    assert ya_avisado([fallido, enviado], _local(5, 19))
