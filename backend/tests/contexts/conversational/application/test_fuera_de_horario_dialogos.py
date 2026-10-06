"""HS-T2 RN-04 con un diálogo abierto — política (b), casos 27 a 30 del plan.

La respuesta a lo que el agente ofreció antes de cerrar («el primero», «sí») se sigue atendiendo
de noche **sin el modelo** y **termina con la oración de fuera de horario**: así todo saliente del
agente en el período informa el cierre, y la regla «ya avisado» (T9) es cierta. Aparte de
`test_fuera_de_horario.py` para que ningún archivo de tests pase de 400 líneas.

Fechas: el lunes 05/10/2026 (el 12/10 es lunes, el 13/10 martes, el 14/10 miércoles).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from cheatsheet.contexts.conversational.domain.conversacion import (
    INTENTOS_ANTES_DE_ESCALAR,
    MENSAJE_DERIVACION,
    Intencion,
)
from cheatsheet.contexts.conversational.domain.dialogo import PasoDelDialogo
from cheatsheet.contexts.conversational.domain.escalamiento import MOTIVO_BAJA_CONFIANZA
from cheatsheet.contexts.conversational.domain.fuera_de_horario import PoliticaFueraDeHorario
from cheatsheet.contexts.conversational.domain.pedido_de_turno import AccionDeTurno
from cheatsheet.contexts.conversational.domain.textos_de_turnos import MENSAJE_TURNO_CON_SENA
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

from tests.contexts.conversational.application.escena import (
    Escena,
    leyendo,
    para_manana,
    pidiendo,
)
from tests.contexts.conversational.application.horario_fijo import Cierre, HorarioFijo
from tests.contexts.conversational.application.test_cancelacion_por_whatsapp import un_turno

pytestmark = pytest.mark.asyncio

FIJO = PoliticaFueraDeHorario.MENSAJE_FIJO
OCTUBRE_6 = date(2026, 10, 6)


def _local(dia: int, hora: int, minuto: int = 0, segundo: int = 0) -> datetime:
    return datetime(2026, 10, dia, hora, minuto, segundo, tzinfo=ZONA_ARGENTINA)


NOCHE = Cierre(_local(5, 19), _local(6, 9))
ANTES_DE_CERRAR = _local(5, 18, 55)
POSDATA_DE_LA_NOCHE = (
    "Te recordamos que ahora estamos fuera del horario de atención; "
    "atendemos de nuevo mañana a las 09:00."
)


def _escena(*cierres: Cierre, ahora: datetime, **resto: object) -> Escena:
    escena = Escena(horario=HorarioFijo(FIJO, cierres), **resto)  # type: ignore[arg-type]
    escena.ahora = ahora
    return escena


async def _con_oferta(*cierres: Cierre, ahora: datetime = ANTES_DE_CERRAR) -> Escena:
    """Un cliente que pidió un turno para mañana y recibió la oferta antes de cerrar."""
    escena = _escena(
        *cierres,
        ahora=ahora,
        lectura=pidiendo(AccionDeTurno.RESERVAR, para_manana()),
        primer_dia=OCTUBRE_6,
    )
    await escena.procesar("Quiero un turno para mañana")
    assert escena.dialogo is not None
    assert escena.dialogo.paso is PasoDelDialogo.ELEGIR_HORARIO
    return escena


class TestRespuestaAUnaOfertaDeNoche:
    async def test_elegir_un_horario_reserva_sin_el_modelo_y_termina_con_la_oracion(self) -> None:
        """RED del caso 27: oferta a las 18:55, cierre a las 19:00, «el primero» a las 19:05."""
        escena = await _con_oferta(NOCHE)
        llamadas = len(escena.interprete.vistos)
        escena.ahora = _local(5, 19, 5)

        await escena.procesar("el primero")

        assert len(escena.agenda.reservados) == 1
        assert len(escena.textos) == 2  # la oferta y un solo saliente de la reserva
        assert escena.ultimo_texto == (
            "Listo, tu turno quedó reservado para el martes 06/10 a las 09:00."
            f"\n\n{POSDATA_DE_LA_NOCHE}"
        )
        assert len(escena.interprete.vistos) == llamadas

    async def test_despues_de_la_respuesta_con_oracion_el_agente_calla(self) -> None:
        """RED del caso 27: ya informó el cierre, así que «¿cuánto sale?» no recibe nada."""
        escena = await _con_oferta(NOCHE)
        escena.ahora = _local(5, 19, 5)
        await escena.procesar("el primero")
        enviados = len(escena.textos)
        llamadas = len(escena.interprete.vistos)

        escena.ahora = _local(5, 19, 10)
        await escena.procesar("¿cuánto sale?")

        assert len(escena.textos) == enviados
        assert len(escena.interprete.vistos) == llamadas
        assert escena.publicador.de_la_accion("responder_fuera_de_horario") == []

    async def test_un_mensaje_que_no_es_respuesta_recibe_el_fijo_y_el_dialogo_sigue(self) -> None:
        """Caso 28: el diálogo vigente no se cierra; si después llega la respuesta, se atiende."""
        escena = await _con_oferta(NOCHE)
        llamadas = len(escena.interprete.vistos)
        escena.ahora = _local(5, 19, 2)

        await escena.procesar("hola, ¿cuánto sale?")

        assert "fuera del horario de atención" in escena.ultimo_texto
        assert escena.hay_dialogo()
        assert len(escena.interprete.vistos) == llamadas
        escena.ahora = _local(5, 19, 4)

        await escena.procesar("el primero")

        assert len(escena.agenda.reservados) == 1
        assert escena.ultimo_texto.endswith(POSDATA_DE_LA_NOCHE)

    async def test_el_paso_que_pide_texto_libre_recibe_el_fijo(self) -> None:
        """Caso 28: `PEDIR_CUANDO` lo lee el intérprete, y de noche el modelo no se llama."""
        escena = _escena(
            NOCHE,
            ahora=_local(5, 18, 55),
            lectura=pidiendo(AccionDeTurno.RESERVAR),
            primer_dia=OCTUBRE_6,
        )
        await escena.procesar("quiero un turno")
        assert escena.dialogo is not None
        assert escena.dialogo.paso is PasoDelDialogo.PEDIR_CUANDO
        llamadas = len(escena.interprete.vistos)
        escena.ahora = _local(5, 19, 2)

        await escena.procesar("el jueves")

        assert "fuera del horario de atención" in escena.ultimo_texto
        assert len(escena.interprete.vistos) == llamadas
        assert escena.agenda.reservados == []

    async def test_confirmar_una_cancelacion_cancela_y_la_confirmacion_lleva_la_oracion(
        self,
    ) -> None:
        """Caso 28."""
        escena = _escena(
            NOCHE,
            ahora=_local(5, 18, 55),
            lectura=pidiendo(AccionDeTurno.CANCELAR),
            conocido=True,
        )
        turno = un_turno()
        escena.agenda.turnos = [turno]
        await escena.procesar("quiero cancelar mi turno")
        escena.ahora = _local(5, 19, 2)

        await escena.procesar("sí")

        assert escena.agenda.cancelados == [turno.id]
        assert escena.ultimo_texto == (
            "Listo, cancelamos tu turno de Consulta general del miércoles 14/10 a las 10:30."
            f"\n\n{POSDATA_DE_LA_NOCHE}"
        )

    async def test_una_oferta_vencida_se_reofrece_tambien_con_la_oracion(self) -> None:
        """U10 T14: un diálogo vencido se re-ofrece como de día, ahora con la oración."""
        escena = await _con_oferta(NOCHE)
        escena.ahora = _local(5, 19, 40)  # pasó la vigencia de 30 minutos

        await escena.procesar("el primero")

        assert escena.agenda.reservados == []
        assert escena.ultimo_texto.endswith(POSDATA_DE_LA_NOCHE)


class TestDialogoQueTerminaEnEscalamiento:
    async def test_la_tercera_eleccion_ambigua_escala_con_el_aviso_con_hora_sin_duplicar(
        self,
    ) -> None:
        """RED del caso 29: la oración no se duplica; el aviso de derivación trae la hora."""
        escena = await _con_oferta(NOCHE)
        escena.ahora = _local(5, 19, 5)

        for _ in range(INTENTOS_ANTES_DE_ESCALAR):
            respuesta = await escena.procesar("9")

        assert respuesta.escalado is True
        assert escena.ultimo_texto == (
            f"{MENSAJE_DERIVACION} Ahora estamos fuera del horario de atención: "
            "un asesor te va a responder a partir de mañana a las 09:00."
        )
        assert escena.ultimo_texto.count("fuera del horario") == 1
        [abierto] = await escena.escalamientos.listar_abiertos()
        assert abierto.motivo == MOTIVO_BAJA_CONFIANZA
        llamadas = len(escena.textos)

        escena.ahora = _local(5, 19, 10)
        await escena.procesar("¿hay alguien?")

        assert len(escena.textos) == llamadas  # escalamiento abierto: silencio

    async def test_cancelar_un_turno_con_sena_de_noche_manda_dos_salientes(self) -> None:
        """RED del caso 29: el de la seña lleva la oración y el aviso trae la hora."""
        escena = _escena(
            NOCHE,
            ahora=_local(5, 18, 55),
            lectura=pidiendo(AccionDeTurno.CANCELAR),
            conocido=True,
        )
        escena.agenda.turnos = [un_turno(), un_turno(sena=True)]
        await escena.procesar("quiero cancelar mi turno")
        escena.ahora = _local(5, 19, 5)

        respuesta = await escena.procesar("el segundo")

        assert respuesta.escalado is True
        assert escena.textos[-2] == f"{MENSAJE_TURNO_CON_SENA}\n\n{POSDATA_DE_LA_NOCHE}"
        assert escena.textos[-1].endswith("a partir de mañana a las 09:00.")
        assert len(await escena.escalamientos.listar_abiertos()) == 1


class TestBordesDelPeriodoDeCierre:
    async def test_una_respuesta_a_un_mensaje_procesado_antes_del_cierre_no_cuenta(self) -> None:
        """RED del caso 30: su `momento` es el `ahora` con que se decidió «abierto»."""
        escena = _escena(NOCHE, ahora=_local(5, 18, 59, 59), lectura=leyendo(Intencion.FAQ))
        await escena.procesar("¿cuánto sale?")  # abierto: contesta como de día
        assert len(escena.textos) == 1
        escena.ahora = _local(5, 19, 10)

        await escena.procesar("¿y los medios de pago?")

        assert len(escena.textos) == 2
        assert "fuera del horario de atención" in escena.ultimo_texto

    async def test_el_fin_de_semana_largo_es_un_solo_periodo(self) -> None:
        """RED del caso 30: el fijo del sábado a la noche silencia el lunes feriado."""
        largo = Cierre(_local(10, 14), _local(13, 9))  # sáb 14:00 → mar 13/10 09:00
        escena = _escena(largo, ahora=_local(10, 20))
        await escena.procesar("hola")
        assert len(escena.textos) == 1

        escena.ahora = _local(12, 10)  # lunes 12/10 sin atención
        await escena.procesar("¿hay alguien?")

        assert len(escena.textos) == 1

    async def test_una_respuesta_del_martes_no_silencia_el_miercoles_sin_atencion(self) -> None:
        """RED del caso 30: una FAQ del martes 18:30 es de otro período que el miércoles."""
        feriado = Cierre(_local(13, 19), _local(15, 9))  # mar 19:00 → jue 09:00 (mié sin atención)
        escena = _escena(feriado, ahora=_local(13, 18, 30), lectura=leyendo(Intencion.FAQ))
        await escena.procesar("¿cuánto sale?")
        assert len(escena.textos) == 1
        escena.ahora = _local(14, 10)

        await escena.procesar("¿hay alguien?")

        assert len(escena.textos) == 2
        assert "fuera del horario de atención" in escena.ultimo_texto
