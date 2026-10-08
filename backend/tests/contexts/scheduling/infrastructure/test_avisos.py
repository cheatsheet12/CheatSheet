"""`AvisoPorWhatsApp`: los avisos de turno por el canal real, sin red (U5, HU-E7-02, HU-E7-06).

Qué se prueba, y casi todo es sobre lo que el adaptador **no** hace:

1. **Nunca levanta.** Un turno cancelado sigue cancelado aunque Meta esté caída (D33): cualquier
   excepción del canal es un log, no un error.
2. **No registra datos personales.** Ni el teléfono, ni el nombre, ni el texto (`CLAUDE.md` §5).
3. **La hora sale en la zona de la agenda** (H3). Un turno leído de la base llega en UTC: sin
   convertir, el cliente leería una hora tres horas corrida.
4. La reprogramación **dice el horario viejo además del nuevo**.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.scheduling.application.ports import DatosDeAviso
from cheatsheet.contexts.scheduling.infrastructure.avisos import (
    AvisoPorWhatsApp,
    ResultadoLocal,
    texto_de_cancelacion,
    texto_de_reprogramacion,
    texto_de_reserva,
)
from structlog.testing import capture_logs

from .canal_de_avisos_falso import CanalDeAvisosFalso

pytestmark = pytest.mark.asyncio

TELEFONO = "5491112345678"
NOMBRE = "Ana Diaz"
CLIENTE = uuid4()

# 13:30 UTC es 10:30 en Buenos Aires (UTC-3, sin horario de verano).
DATOS = DatosDeAviso(
    cliente_id=CLIENTE,
    telefono=TELEFONO,
    nombre_del_cliente=NOMBRE,
    servicio="Corte",
    recurso="Consultorio 1",
    inicio=datetime(2026, 10, 15, 13, 30, tzinfo=UTC),
)


class SinPlantillas:
    """`PlantillasAprobadas` sin ninguna aprobada: el adaptador manda su texto de fábrica."""

    async def para(self, codigo: str, variables: object) -> None:
        del codigo, variables
        return


async def test_los_tres_textos_nombran_el_servicio_el_nombre_y_el_horario() -> None:
    for texto in (
        texto_de_reserva(DATOS),
        texto_de_cancelacion(DATOS),
        texto_de_reprogramacion(DATOS),
    ):
        assert "Corte" in texto
        assert "15/10/2026" in texto
        assert NOMBRE in texto


async def test_la_hora_sale_en_la_zona_de_la_agenda_y_no_en_utc() -> None:
    """**Caso 33 (H3).** Antes salía «13:30»."""
    movido = DatosDeAviso(
        cliente_id=CLIENTE,
        telefono=TELEFONO,
        nombre_del_cliente=NOMBRE,
        servicio="Corte",
        recurso="Consultorio 1",
        inicio=DATOS.inicio,
        inicio_anterior=datetime(2026, 10, 14, 13, 30, tzinfo=UTC),
    )

    for texto in (
        texto_de_reserva(DATOS),
        texto_de_cancelacion(DATOS),
        texto_de_reprogramacion(movido),
    ):
        assert "15/10/2026 a las 10:30" in texto
        assert "13:30" not in texto
    assert "(antes 14/10/2026 a las 10:30)" in texto_de_reprogramacion(movido)


async def test_cerca_de_medianoche_la_fecha_tambien_se_convierte() -> None:
    # 02:30 UTC del 16 es las 23:30 del 15 en Buenos Aires: cambia el día, no sólo la hora.
    tarde = DatosDeAviso(
        cliente_id=CLIENTE,
        telefono=TELEFONO,
        nombre_del_cliente=NOMBRE,
        servicio="Corte",
        recurso="Consultorio 1",
        inicio=datetime(2026, 10, 16, 2, 30, tzinfo=UTC),
    )

    assert "15/10/2026 a las 23:30" in texto_de_reserva(tarde)


async def test_la_reprogramacion_dice_el_horario_viejo_ademas_del_nuevo() -> None:
    movido = DatosDeAviso(
        cliente_id=CLIENTE,
        telefono=TELEFONO,
        nombre_del_cliente=NOMBRE,
        servicio="Corte",
        recurso="Consultorio 1",
        inicio=datetime(2026, 9, 9, 18, 0, tzinfo=UTC),
        inicio_anterior=datetime(2026, 9, 8, 18, 0, tzinfo=UTC),
    )

    texto = texto_de_reprogramacion(movido)

    assert "09/09/2026" in texto
    assert "08/09/2026" in texto


async def test_sin_horario_anterior_el_texto_no_dice_nada_de_antes() -> None:
    # Un turno reprogramado por primera vez desde otro canal puede no traer el dato; el texto
    # tiene que quedar bien igual y no con un «(antes None)».
    assert "antes" not in texto_de_reprogramacion(DATOS)


class TestAvisoPorWhatsApp:
    async def test_reserva_cancelacion_y_reprogramacion_mandan_su_texto_al_cliente(self) -> None:
        """**Caso 24.**"""
        canal = CanalDeAvisosFalso()
        aviso = AvisoPorWhatsApp(canal, SinPlantillas())
        movido = DatosDeAviso(
            cliente_id=CLIENTE,
            telefono=TELEFONO,
            nombre_del_cliente=NOMBRE,
            servicio="Corte",
            recurso="Consultorio 1",
            inicio=datetime(2026, 10, 16, 13, 30, tzinfo=UTC),
            inicio_anterior=DATOS.inicio,
        )

        await aviso.avisar_reserva(DATOS)
        await aviso.avisar_cancelacion(DATOS)
        await aviso.avisar_reprogramacion(movido)

        assert [telefono for telefono, _ in canal.textos] == [TELEFONO] * 3
        assert [texto for _, texto in canal.textos] == [
            texto_de_reserva(DATOS),
            texto_de_cancelacion(DATOS),
            texto_de_reprogramacion(movido),
        ]
        assert "16/10/2026 a las 10:30" in canal.textos[2][1]
        assert "(antes 15/10/2026 a las 10:30)" in canal.textos[2][1]

    @pytest.mark.parametrize("falla", [RuntimeError("explotó"), ValueError("raro"), OSError("red")])
    async def test_un_canal_que_levanta_no_hace_levantar_al_aviso(self, falla: Exception) -> None:
        """**Caso 23.** El turno sigue cancelado aunque el aviso no salga."""
        aviso = AvisoPorWhatsApp(CanalDeAvisosFalso(falla=falla), SinPlantillas())

        await aviso.avisar_reserva(DATOS)
        await aviso.avisar_cancelacion(DATOS)
        await aviso.avisar_reprogramacion(DATOS)

    async def test_el_log_trae_la_clase_de_aviso_y_la_excepcion_y_nada_personal(self) -> None:
        """**Caso 27.**"""
        aviso = AvisoPorWhatsApp(
            CanalDeAvisosFalso(falla=RuntimeError(f"falló {TELEFONO} {NOMBRE}")), SinPlantillas()
        )

        with capture_logs() as registros:
            await aviso.avisar_cancelacion(DATOS)

        fallidos = [r for r in registros if r["event"] == "aviso_de_turno_fallido"]
        assert len(fallidos) == 1
        assert fallidos[0]["clase"] == "cancelacion"
        assert fallidos[0]["causa"] == "RuntimeError"
        volcado = repr(registros)
        for dato in (TELEFONO, NOMBRE, texto_de_cancelacion(DATOS), "Consultorio 1"):
            assert dato not in volcado

    async def test_un_aviso_enviado_tampoco_registra_datos_personales(self) -> None:
        aviso = AvisoPorWhatsApp(CanalDeAvisosFalso(), SinPlantillas())

        with capture_logs() as registros:
            await aviso.avisar_reserva(DATOS)

        volcado = repr(registros)
        for dato in (TELEFONO, NOMBRE, texto_de_reserva(DATOS)):
            assert dato not in volcado


class TestElRegistroDelAviso:
    """U7, D-U7-4: el aviso se guarda en la conversación del cliente (por el `CanalDeAvisos`)."""

    async def test_el_aviso_viaja_con_el_cliente_del_turno(self) -> None:
        canal = CanalDeAvisosFalso()

        await AvisoPorWhatsApp(canal, SinPlantillas()).avisar_cancelacion(DATOS)

        (notificacion,) = canal.notificaciones
        assert notificacion.cliente_id == CLIENTE
        assert notificacion.telefono == TELEFONO
        assert notificacion.texto == texto_de_cancelacion(DATOS)

    async def test_si_el_mensaje_no_se_pudo_guardar_se_deja_constancia_y_no_levanta(self) -> None:
        """**Caso 25.** El turno queda cancelado; el log dice qué clase de aviso no se registró."""
        canal = CanalDeAvisosFalso(resultado=ResultadoLocal(enviado=True, sin_registrar=True))

        with capture_logs() as registros:
            await AvisoPorWhatsApp(canal, SinPlantillas()).avisar_cancelacion(DATOS)

        sin_registrar = [r for r in registros if r["event"] == "aviso_de_turno_sin_registrar"]
        assert len(sin_registrar) == 1
        assert sin_registrar[0]["clase"] == "cancelacion"
        volcado = repr(registros)
        for dato in (TELEFONO, NOMBRE, texto_de_cancelacion(DATOS)):
            assert dato not in volcado

    async def test_un_aviso_que_fallo_deja_el_motivo_corto_en_el_log(self) -> None:
        """**Caso 24 (log).** El hilo muestra el aviso `FALLIDO`; el log, sólo el motivo."""
        canal = CanalDeAvisosFalso(resultado=ResultadoLocal(enviado=False, falla="131047"))

        with capture_logs() as registros:
            await AvisoPorWhatsApp(canal, SinPlantillas()).avisar_cancelacion(DATOS)

        fallidos = [r for r in registros if r["event"] == "aviso_de_turno_fallido"]
        assert [(r["clase"], r["causa"]) for r in fallidos] == [("cancelacion", "131047")]
        assert not [r for r in registros if r["event"] == "aviso_de_turno_sin_registrar"]

    async def test_un_aviso_enviado_y_guardado_no_deja_ningun_aviso_de_falla(self) -> None:
        with capture_logs() as registros:
            await AvisoPorWhatsApp(CanalDeAvisosFalso(), SinPlantillas()).avisar_reserva(DATOS)

        assert registros == []
