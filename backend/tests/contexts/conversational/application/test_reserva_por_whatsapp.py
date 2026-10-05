"""Reservar un turno por WhatsApp (HU-E8-01, issue #68 «El agente no reserva el turno elegido»).

El flujo tiene dos mitades y los tests las siguen:

1. **Ofrecer.** El cliente dice qué quiere y para cuándo; el agente consulta la disponibilidad real
   y ofrece hasta cuatro horarios **repartidos en el día**. Lo que ofreció queda en el `Dialogo`.
2. **Elegir.** El cliente contesta («el primero», «el de las 16») y un analizador **determinista**
   —no el modelo— lo lee. Si resuelve, reserva el motor de `scheduling`, nunca el texto.

Lo que más importa probar es lo que **no** pasa: que el modelo no se entere de la elección, que un
«sí» suelto no reserve nada, que una hora que nadie ofreció no se reserve directo, y que un rechazo
del motor no le deje al cliente un silencio.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.application.errors import (
    HorarioEnElPasado,
    HorarioNoDisponible,
    MensajeYaProcesado,
)
from cheatsheet.contexts.conversational.application.ports import ServicioOfrecible
from cheatsheet.contexts.conversational.domain.conversacion import (
    INTENTOS_ANTES_DE_ESCALAR,
    MENSAJE_DERIVACION,
    MENSAJE_OFRECER_ASESOR,
    Intencion,
)
from cheatsheet.contexts.conversational.domain.dialogo import (
    VIGENCIA_DEL_DIALOGO,
    Dialogo,
    PasoDelDialogo,
)
from cheatsheet.contexts.conversational.domain.escalamiento import MOTIVO_BAJA_CONFIANZA
from cheatsheet.contexts.conversational.domain.pedido_de_turno import (
    AccionDeTurno,
    Cuando,
    MomentoDelDia,
    ReferenciaDeDia,
)
from cheatsheet.contexts.conversational.domain.textos_de_turnos import (
    MENSAJE_FECHA_PASADA,
    MENSAJE_HORARIO_OCUPADO,
    MENSAJE_HORARIO_PASADO,
    MENSAJE_NO_ENTENDI_LA_ELECCION,
    MENSAJE_OFERTA_VENCIDA,
    MENSAJE_PEDIR_CUANDO,
    MENSAJE_SIN_HORARIOS,
    MENSAJE_SIN_LO_PEDIDO,
)
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

from tests.contexts.conversational.application.dobles import (
    RECURSO_DE_PRUEBA,
    SERVICIO_DE_PRUEBA,
    grilla_de,
)
from tests.contexts.conversational.application.escena import (
    AHORA,
    MANANA,
    Escena,
    leyendo,
    para_manana,
    pidiendo,
)

pytestmark = pytest.mark.asyncio


def horas(dialogo: Dialogo | None) -> list[str]:
    assert dialogo is not None
    return [uno.inicio.astimezone(ZONA_ARGENTINA).strftime("%H:%M") for uno in dialogo.horarios]


def hora_de(inicio: datetime) -> str:
    return inicio.astimezone(ZONA_ARGENTINA).strftime("%H:%M")


async def con_oferta(escena: Escena | None = None) -> Escena:
    """Una escena donde el cliente ya pidió un turno para mañana y recibió la oferta."""
    escena = escena or Escena(lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()))
    await escena.procesar("Quiero un turno para mañana")
    assert escena.dialogo is not None
    assert escena.dialogo.paso is PasoDelDialogo.ELEGIR_HORARIO
    return escena


class TestOfrecer:
    async def test_ofrece_cuatro_horarios_repartidos_en_el_dia(self) -> None:
        """RED del caso 12: antes no se guardaba nada, y los horarios eran siempre 9:00-10:00."""
        escena = await con_oferta()

        assert horas(escena.dialogo) == ["09:00", "11:00", "13:30", "15:30"]
        texto = escena.ultimo_texto
        assert texto.splitlines()[0] == "Tengo estos horarios disponibles:"
        assert "1) miércoles 09/09 a las 09:00" in texto
        assert "4) miércoles 09/09 a las 15:30" in texto

    async def test_guarda_lo_ofrecido_con_su_vigencia(self) -> None:
        """RED del caso 12: el diálogo lleva las opciones, el servicio y el vencimiento."""
        escena = await con_oferta()

        dialogo = escena.dialogo
        assert dialogo is not None
        assert dialogo.abierto_en == AHORA
        assert dialogo.vence_en == AHORA + VIGENCIA_DEL_DIALOGO
        assert dialogo.servicio_id == SERVICIO_DE_PRUEBA.id
        assert [uno.recursos for uno in dialogo.horarios] == [(RECURSO_DE_PRUEBA,)] * 4

    async def test_el_intento_cuenta_como_entendido_y_nada_se_reserva(self) -> None:
        escena = await con_oferta()

        assert escena.hilo.contador == 0
        assert escena.agenda.reservados == []

    async def test_manana_es_el_de_argentina_y_no_el_de_utc(self) -> None:
        """RED del caso 8: a las 22:30 del 4/10 en Argentina, UTC ya es 5/10 01:30.

        Con `ahora + 1 día` en UTC, «mañana» daba el 6; es el 5.
        """
        octubre = date(2026, 10, 5)
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()),
            libres=grilla_de(octubre) + grilla_de(octubre + timedelta(days=1)),
        )
        escena.ahora = datetime(2026, 10, 5, 1, 30, tzinfo=UTC)

        await escena.procesar("quiero un turno para mañana")

        assert escena.agenda.consultas == [(SERVICIO_DE_PRUEBA.id, octubre)]
        assert "lunes 05/10" in escena.ultimo_texto

    async def test_sin_dia_ni_hora_pregunta_el_dia(self) -> None:
        """T8: como el prototipo, «¿Para qué día te queda cómodo?»."""
        escena = Escena(lectura=pidiendo(AccionDeTurno.RESERVAR), conocido=True)

        await escena.procesar("quiero un turno")

        assert escena.textos == [MENSAJE_PEDIR_CUANDO]
        assert escena.dialogo is not None
        assert escena.dialogo.paso is PasoDelDialogo.PEDIR_CUANDO
        assert escena.agenda.consultas == []

    async def test_un_turno_sin_pedido_tambien_pregunta_el_dia(self) -> None:
        escena = Escena(lectura=leyendo(Intencion.TURNO))

        await escena.procesar("necesito un turno")

        assert escena.textos == [MENSAJE_PEDIR_CUANDO]

    async def test_la_respuesta_con_un_cuando_continua_aunque_la_confianza_sea_baja(self) -> None:
        """T8 y caso 17: «el jueves a la tarde» es una lectura floja pero completa la reserva."""
        escena = Escena(lectura=pidiendo(AccionDeTurno.RESERVAR))
        escena.interprete.programar(
            pidiendo(AccionDeTurno.RESERVAR),
            leyendo(
                Intencion.TURNO,
                0.3,
                pedido=pidiendo(
                    AccionDeTurno.RESERVAR,
                    Cuando(ReferenciaDeDia.DIA_DE_SEMANA, dia_semana=3),
                    momento=MomentoDelDia.TARDE,
                ).pedido_de_turno,
            ),
        )

        await escena.procesar("quiero un turno")
        await escena.procesar("el jueves a la tarde")

        assert escena.dialogo is not None
        assert escena.dialogo.paso is PasoDelDialogo.ELEGIR_HORARIO
        jueves = date(2026, 9, 10)
        assert escena.agenda.consultas == [(SERVICIO_DE_PRUEBA.id, jueves)]
        assert all(
            time(13) <= time.fromisoformat(hora) < time(20) for hora in horas(escena.dialogo)
        )
        assert escena.hilo.contador == 0

    async def test_con_la_franja_de_la_tarde_ofrece_solo_tardes(self) -> None:
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana(), momento=MomentoDelDia.TARDE)
        )

        await escena.procesar("un turno mañana a la tarde")

        assert all(hora >= "13:00" for hora in horas(escena.dialogo))
        assert all(hora < "20:00" for hora in horas(escena.dialogo))

    async def test_con_una_hora_libre_ofrece_esa_hora_y_pide_confirmacion(self) -> None:
        escena = Escena(lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana(), hora=time(16)))

        await escena.procesar("un turno mañana a las 16")

        assert horas(escena.dialogo) == ["16:00"]
        assert "¿Te lo reservo?" in escena.ultimo_texto

    async def test_ofrece_dos_dias_repartiendo_el_cupo(self) -> None:
        escena = Escena(
            lectura=pidiendo(
                AccionDeTurno.RESERVAR,
                Cuando(ReferenciaDeDia.DIA_DE_SEMANA, dia_semana=2),
                Cuando(ReferenciaDeDia.DIA_DE_SEMANA, dia_semana=4),
            )
        )

        await escena.procesar("el miércoles o el viernes")

        dialogo = escena.dialogo
        assert dialogo is not None
        dias = [uno.inicio.astimezone(ZONA_ARGENTINA).date() for uno in dialogo.horarios]
        assert dias == [date(2026, 9, 9)] * 2 + [date(2026, 9, 11)] * 2


class TestAlternativasCercanas:
    async def test_sin_libres_ese_dia_ofrece_el_primer_dia_siguiente_y_lo_dice(self) -> None:
        """Caso 11, CA3: el día pedido no tiene nada, y el agente no se queda mudo."""
        viernes = date(2026, 9, 11)
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()), libres=grilla_de(viernes)
        )

        await escena.procesar("un turno para mañana")

        assert escena.ultimo_texto.splitlines()[0] == MENSAJE_SIN_LO_PEDIDO
        assert "viernes 11/09" in escena.ultimo_texto
        assert escena.dialogo is not None

    async def test_sin_nada_en_siete_dias_ofrece_un_asesor(self) -> None:
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()),
            libres=grilla_de(date(2026, 9, 30)),
        )

        await escena.procesar("un turno para mañana")

        assert escena.textos == [MENSAJE_SIN_HORARIOS]
        assert escena.dialogo is None
        assert len(escena.agenda.consultas) == 1 + 7

    async def test_una_fecha_que_ya_paso_lo_dice_y_ofrece_futuros(self) -> None:
        """RED del caso 19, CA6: «un turno para el 7/9» cuando hoy es 8/9."""
        ayer = Cuando(ReferenciaDeDia.FECHA, dia=7, mes=9)
        escena = Escena(lectura=pidiendo(AccionDeTurno.RESERVAR, ayer))

        await escena.procesar("un turno para el 7 de septiembre")

        assert escena.ultimo_texto.splitlines()[0] == MENSAJE_FECHA_PASADA
        assert "Tengo estos horarios disponibles:" in escena.ultimo_texto
        assert escena.dialogo is not None

    async def test_una_hora_de_hoy_que_ya_paso_lo_dice_y_ofrece_futuros(self) -> None:
        """RED del caso 19: «hoy a las 9» cuando son las 12 en Argentina."""
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, Cuando(ReferenciaDeDia.HOY), hora=time(9))
        )

        await escena.procesar("un turno hoy a las 9")

        assert escena.ultimo_texto.splitlines()[0] == MENSAJE_FECHA_PASADA
        assert escena.dialogo is not None
        assert escena.agenda.reservados == []


class TestElegir:
    async def test_prefiero_el_primero_reserva_y_no_llama_al_modelo(self) -> None:
        """RED del caso 13 (CA2): el cliente elige entre lo ofrecido y el motor reserva."""
        escena = await con_oferta()
        primero = escena.dialogo.horarios[0]  # type: ignore[union-attr]
        llamadas = len(escena.interprete.vistos)

        await escena.procesar("Prefiero el primero")

        [reservado] = escena.agenda.reservados
        assert (reservado.recurso_id, reservado.inicio) == (primero.recursos[0], primero.inicio)
        assert escena.ultimo_texto == (
            "Listo, tu turno quedó reservado para el miércoles 09/09 a las 09:00."
        )
        assert escena.dialogo is None
        # La elección no llegó al modelo: cero tokens y ningún dato al proveedor (T3).
        assert len(escena.interprete.vistos) == llamadas

    @pytest.mark.parametrize(
        ("texto", "hora"),
        [("2", "11:00"), ("el último", "15:30"), ("el de las 11", "11:00"), ("13:30", "13:30")],
    )
    async def test_elige_por_numero_o_por_hora(self, texto: str, hora: str) -> None:
        escena = await con_oferta()

        await escena.procesar(texto)

        assert [hora_de(uno.inicio) for uno in escena.agenda.reservados] == [hora]

    async def test_la_reserva_queda_en_la_bitacora_con_iniciador_ia(self) -> None:
        """T12 y HS-T2 RN-05: «Agente IA» ve la reserva en el panel de auditoría."""
        escena = await con_oferta()

        await escena.procesar("el primero")

        [evento] = escena.publicador.de_la_accion("reservar_turno_por_whatsapp")
        assert evento.entidad_afectada.startswith("Turno:")
        assert evento.resultado.value == "completado"
        assert evento.iniciador is not None
        assert evento.iniciador.value == "ia"

    async def test_una_hora_que_no_se_ofrecio_y_esta_libre_arma_una_oferta_nueva(self) -> None:
        """Caso 15: nunca reserva directo lo que nadie ofreció. Y si es una sola, «sí» la elige."""
        escena = await con_oferta()

        await escena.procesar("a las 10")

        assert escena.agenda.reservados == []
        assert horas(escena.dialogo) == ["10:00"]

        await escena.procesar("sí")

        assert [hora_de(uno.inicio) for uno in escena.agenda.reservados] == ["10:00"]
        assert escena.dialogo is None

    async def test_una_hora_que_no_se_ofrecio_y_esta_ocupada_ofrece_las_cercanas(self) -> None:
        escena = await con_oferta()
        escena.agenda.tomados.add(datetime.combine(MANANA, time(10), tzinfo=ZONA_ARGENTINA))

        await escena.procesar("a las 10")

        assert escena.agenda.reservados == []
        assert horas(escena.dialogo) == ["09:00", "09:30", "10:30", "11:00"]

    async def test_un_numero_fuera_de_rango_repregunta_y_suma_un_intento(self) -> None:
        escena = await con_oferta()

        await escena.procesar("7")

        assert escena.ultimo_texto == MENSAJE_NO_ENTENDI_LA_ELECCION
        assert escena.hilo.contador == 1
        assert escena.dialogo is not None
        assert escena.agenda.reservados == []

    async def test_tres_malentendidos_seguidos_escalan_y_cierran_el_dialogo(self) -> None:
        """Caso 16, CA5: «tras varios intentos» se deriva."""
        escena = await con_oferta()

        for _ in range(INTENTOS_ANTES_DE_ESCALAR):
            respuesta = await escena.procesar("9")

        assert respuesta.escalado
        assert escena.ultimo_texto == MENSAJE_DERIVACION
        [abierto] = await escena.escalamientos.listar_abiertos()
        assert abierto.motivo == MOTIVO_BAJA_CONFIANZA
        assert escena.dialogo is None
        assert escena.agenda.reservados == []

    async def test_una_hora_ambigua_repregunta(self) -> None:
        """«a las 5» con 05:00 y 17:00 ofrecidas no se adivina."""
        madrugada = grilla_de(MANANA, desde=5, hasta=6) + grilla_de(MANANA, desde=17, hasta=18)
        escena = Escena(lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()), libres=madrugada)
        await escena.procesar("un turno para mañana")

        await escena.procesar("a las 5")

        assert escena.ultimo_texto == MENSAJE_NO_ENTENDI_LA_ELECCION
        assert escena.agenda.reservados == []

    async def test_ninguno_pide_otro_dia_y_la_respuesta_continua_la_reserva(self) -> None:
        """Caso 17: «ninguno» vuelve a preguntar el día."""
        escena = await con_oferta()

        await escena.procesar("ninguno")

        assert escena.ultimo_texto == MENSAJE_PEDIR_CUANDO
        assert escena.dialogo is not None
        assert escena.dialogo.paso is PasoDelDialogo.PEDIR_CUANDO
        assert escena.dialogo.servicio_id == SERVICIO_DE_PRUEBA.id

    async def test_un_si_sin_dialogo_no_reserva_nada(self) -> None:
        """Caso 29: sin una oferta vigente, «sí» y «el primero» no son nada."""
        escena = Escena(lectura=leyendo(Intencion.FAQ))

        await escena.procesar("sí")
        await escena.procesar("el primero")

        assert escena.agenda.reservados == []
        assert escena.agenda.cancelados == []

    async def test_el_mismo_mensaje_entregado_dos_veces_reserva_una_sola_vez(self) -> None:
        """Caso 26: Meta reintenta. El segundo intento no reserva dos turnos."""
        escena = await con_oferta()

        await escena.procesar("el primero", externo_id="wamid-reintento")
        with pytest.raises(MensajeYaProcesado):
            await escena.procesar("el primero", externo_id="wamid-reintento")

        assert len(escena.agenda.reservados) == 1


class TestElMotorRechaza:
    async def test_se_ocupo_entretanto_lo_dice_y_ofrece_alternativas_vigentes(self) -> None:
        """RED del caso 18, CA4: dos clientes eligieron el mismo horario y el motor eligió uno."""
        escena = await con_oferta()
        escena.agenda.rechazos[RECURSO_DE_PRUEBA] = HorarioNoDisponible("ocupado")

        await escena.procesar("el primero")

        assert escena.ultimo_texto.splitlines()[0] == MENSAJE_HORARIO_OCUPADO
        assert escena.agenda.reservados == []
        # Alternativas **vigentes**, cerca del que se perdió, y sin repetir el que falló.
        assert escena.dialogo is not None
        assert escena.dialogo.paso is PasoDelDialogo.ELEGIR_HORARIO
        assert "09:00" not in horas(escena.dialogo)
        assert horas(escena.dialogo)[0] == "09:30"

    async def test_el_rechazo_queda_en_la_bitacora_como_error(self) -> None:
        escena = await con_oferta()
        escena.agenda.rechazos[RECURSO_DE_PRUEBA] = HorarioNoDisponible("ocupado")

        await escena.procesar("el primero")

        [evento] = escena.publicador.de_la_accion("reservar_turno_por_whatsapp")
        assert evento.resultado.value == "error"
        assert evento.entidad_afectada.startswith("Conversacion:")

    async def test_si_el_primer_recurso_falla_prueba_el_siguiente_sin_molestar(self) -> None:
        """Caso 18, segunda mitad: dos recursos con el mismo inicio, el primero se ocupó."""
        otro = uuid4()
        libres = grilla_de(MANANA) + grilla_de(MANANA, recurso_id=otro)
        escena = Escena(lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()), libres=libres)
        await escena.procesar("un turno para mañana")
        assert escena.dialogo.horarios[0].recursos == (RECURSO_DE_PRUEBA, otro)  # type: ignore[union-attr]
        escena.agenda.rechazos[RECURSO_DE_PRUEBA] = HorarioNoDisponible("ocupado")

        await escena.procesar("el primero")

        [reservado] = escena.agenda.reservados
        assert reservado.recurso_id == otro
        assert escena.ultimo_texto.startswith("Listo, tu turno quedó reservado")

    async def test_ya_paso_lo_dice_y_ofrece_alternativas(self) -> None:
        """Caso 20, CA7: el motor re-verifica y rechaza lo que se venció mientras el cliente dudaba."""
        escena = await con_oferta()
        escena.agenda.rechazos[RECURSO_DE_PRUEBA] = HorarioEnElPasado("ya pasó")

        await escena.procesar("el primero")

        assert escena.ultimo_texto.splitlines()[0] == MENSAJE_HORARIO_PASADO
        assert escena.agenda.reservados == []
        assert escena.dialogo is not None


class TestLaOfertaVence:
    async def test_elegir_con_el_dialogo_vencido_no_reserva_y_vuelve_a_ofrecer(self) -> None:
        """RED del caso 20, T14: pasados 30 minutos, «el primero» ya no reserva."""
        escena = await con_oferta()
        escena.ahora = AHORA + VIGENCIA_DEL_DIALOGO + timedelta(seconds=1)
        consultas = len(escena.agenda.consultas)

        await escena.procesar("el primero")

        assert escena.agenda.reservados == []
        assert escena.ultimo_texto.splitlines()[0] == MENSAJE_OFERTA_VENCIDA
        # Se volvió a consultar la disponibilidad, y el diálogo nuevo vence 30 minutos después.
        assert len(escena.agenda.consultas) > consultas
        assert escena.dialogo is not None
        assert escena.dialogo.vence_en == escena.ahora + VIGENCIA_DEL_DIALOGO

    async def test_justo_antes_de_vencer_todavia_reserva(self) -> None:
        escena = await con_oferta()
        escena.ahora = AHORA + VIGENCIA_DEL_DIALOGO - timedelta(seconds=1)

        await escena.procesar("el primero")

        assert len(escena.agenda.reservados) == 1


def un_servicio(nombre: str) -> ServicioOfrecible:
    return ServicioOfrecible(id=uuid4(), nombre=nombre)


class TestServicio:
    """T7 y Pregunta 2: sin servicio no hay duración, y reservar la equivocada sería en silencio."""

    async def test_con_un_solo_servicio_no_se_pregunta(self) -> None:
        escena = await con_oferta()

        assert escena.dialogo.servicio_id == SERVICIO_DE_PRUEBA.id  # type: ignore[union-attr]
        assert "¿Para qué servicio?" not in "\n".join(escena.textos)

    async def test_un_nombre_del_catalogo_en_el_texto_elige_ese_servicio(self) -> None:
        corte, color = un_servicio("Corte"), un_servicio("Color")
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana(), servicio="un turno para corte"),
            servicios=[corte, color],
        )

        await escena.procesar("un turno para corte mañana")

        assert escena.dialogo is not None
        assert escena.dialogo.servicio_id == corte.id
        assert {servicio for servicio, _ in escena.agenda.consultas} == {corte.id}

    async def test_varios_sin_nombrar_ninguno_pregunta_con_un_listado_numerado(self) -> None:
        corte, color = un_servicio("Corte"), un_servicio("Color")
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()),
            servicios=[corte, color],
        )

        await escena.procesar("un turno para mañana")

        assert escena.textos == ["¿Para qué servicio?\n1) Corte\n2) Color"]
        assert escena.dialogo is not None
        assert escena.dialogo.paso is PasoDelDialogo.ELEGIR_SERVICIO
        assert escena.agenda.consultas == []

    async def test_elegir_el_servicio_por_numero_sigue_la_reserva(self) -> None:
        corte, color = un_servicio("Corte"), un_servicio("Color")
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()),
            servicios=[corte, color],
        )
        await escena.procesar("un turno para mañana")
        llamadas = len(escena.interprete.vistos)

        await escena.procesar("2")

        assert escena.dialogo is not None
        assert escena.dialogo.paso is PasoDelDialogo.ELEGIR_HORARIO
        assert escena.dialogo.servicio_id == color.id
        # El pedido «para mañana» se recordó: no hubo que volver a preguntarlo ni al modelo.
        assert len(escena.interprete.vistos) == llamadas

    async def test_dos_nombres_que_coinciden_tambien_preguntan(self) -> None:
        corte, color = un_servicio("Corte"), un_servicio("Color")
        escena = Escena(
            lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana(), servicio="corte y color"),
            servicios=[corte, color],
        )

        await escena.procesar("corte y color mañana")

        assert escena.dialogo is not None
        assert escena.dialogo.paso is PasoDelDialogo.ELEGIR_SERVICIO

    async def test_sin_servicios_ofrece_un_asesor(self) -> None:
        escena = Escena(lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()), servicios=[])

        await escena.procesar("un turno para mañana")

        assert "asesor" in escena.ultimo_texto


class TestReprogramar:
    async def test_reprogramar_ofrece_un_asesor_y_no_toca_la_agenda(self) -> None:
        """Caso 39: ninguna HU lo pide, así que el agente no improvisa."""
        escena = Escena(lectura=pidiendo(AccionDeTurno.REPROGRAMAR))

        await escena.procesar("quiero mover mi turno")

        assert escena.textos == [MENSAJE_OFRECER_ASESOR]
        assert escena.agenda.consultas == []
        assert escena.agenda.reservados == []
        assert escena.agenda.cancelados == []
