"""HS-T2 RN-04 y HU-E8-05 RN-04 — el agente fuera de horario, sin diálogos (casos 18 a 26, 31 a 35).

El horario lo calcula `business_config`; acá entra ya resuelto por el puerto (`HorarioFijo`). Lo
que se prueba es la **política**: (a) el agente responde siempre y sólo cambia el aviso de
derivación; (b) el agente no contesta, el modelo **no se llama** y sale un mensaje fijo por
período de cierre.

Fechas: el lunes 05/10/2026 (el 12/10 es lunes, el 13/10 martes). Hora de Argentina.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.application.errors import MensajeYaProcesado
from cheatsheet.contexts.conversational.domain.conversacion import (
    INTENTOS_ANTES_DE_ESCALAR,
    MENSAJE_DERIVACION,
    Conversacion,
    DireccionMensaje,
    Intencion,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    MOTIVO_BAJA_CONFIANZA,
    Escalamiento,
)
from cheatsheet.contexts.conversational.domain.fuera_de_horario import PoliticaFueraDeHorario
from cheatsheet.contexts.conversational.domain.pedido_de_turno import AccionDeTurno
from cheatsheet.contexts.conversational.domain.textos_de_turnos import MENSAJE_TURNO_CON_SENA
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

from tests.contexts.conversational.application.escena import (
    EMPRESA,
    TELEFONO,
    Escena,
    leyendo,
    pidiendo,
)
from tests.contexts.conversational.application.horario_fijo import Cierre, HorarioFijo
from tests.contexts.conversational.application.test_cancelacion_por_whatsapp import un_turno

pytestmark = pytest.mark.asyncio

PERSONA = "quiero hablar con una persona"
FIJO = PoliticaFueraDeHorario.MENSAJE_FIJO
RESPONDE = PoliticaFueraDeHorario.AGENTE_RESPONDE


def _local(dia: int, hora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 10, dia, hora, minuto, tzinfo=ZONA_ARGENTINA)


#: La noche del lunes 05/10: cerrado de 19:00 a 09:00 del martes.
NOCHE = Cierre(_local(5, 19), _local(6, 9))


def _escena(
    politica: PoliticaFueraDeHorario,
    *cierres: Cierre,
    ahora: datetime,
    **resto: object,
) -> Escena:
    escena = Escena(horario=HorarioFijo(politica, cierres), **resto)  # type: ignore[arg-type]
    escena.ahora = ahora
    return escena


def _aviso(cuando: str) -> str:
    return (
        f"{MENSAJE_DERIVACION} Ahora estamos fuera del horario de atención: "
        f"un asesor te va a responder a partir {cuando}."
    )


def _entrantes(escena: Escena) -> list[Mensaje]:
    return [
        uno
        for uno in escena.mensajes.mensajes.values()
        if uno.direccion is DireccionMensaje.ENTRANTE
    ]


# --------------------------------------------------------------------- (a) responde siempre


class TestPoliticaAgenteResponde:
    async def test_pedir_una_persona_de_noche_avisa_desde_cuando_atiende_un_asesor(self) -> None:
        """RED del caso 18: antes el cliente leía «Lo derivo…» sin saber que nadie lo iba a leer."""
        cierre = Cierre(_local(10, 14), _local(12, 9))  # el fin de semana, hasta el lunes
        escena = _escena(RESPONDE, cierre, ahora=_local(10, 20))

        respuesta = await escena.procesar(PERSONA)

        assert respuesta.escalado is True
        assert escena.textos == [_aviso("del lunes 12/10 a las 09:00")]
        assert len(escena.escalamientos.escalamientos) == 1

    async def test_los_otros_motivos_de_derivacion_dicen_lo_mismo(self) -> None:
        """Caso 19: baja confianza agotada y turno con seña, fuera de horario."""
        escena = _escena(RESPONDE, NOCHE, ahora=_local(5, 22), lectura=leyendo(Intencion.FAQ, 0.1))
        for _ in range(INTENTOS_ANTES_DE_ESCALAR):
            await escena.procesar("asdf")

        assert escena.ultimo_texto == _aviso("de mañana a las 09:00")
        [escalamiento] = escena.escalamientos.escalamientos.values()
        assert escalamiento.motivo == MOTIVO_BAJA_CONFIANZA

        con_sena = _escena(
            RESPONDE,
            NOCHE,
            ahora=_local(5, 22),
            lectura=pidiendo(AccionDeTurno.CANCELAR),
            conocido=True,
        )
        con_sena.agenda.turnos = [un_turno(sena=True)]
        await con_sena.procesar("quiero cancelar mi turno")

        assert con_sena.textos == [MENSAJE_TURNO_CON_SENA, _aviso("de mañana a las 09:00")]

    async def test_dentro_de_horario_el_aviso_es_exactamente_el_de_siempre(self) -> None:
        """Caso 19: dentro de horario no cambia ni una coma."""
        escena = _escena(RESPONDE, NOCHE, ahora=_local(5, 10))

        await escena.procesar(PERSONA)

        assert escena.textos == [MENSAJE_DERIVACION]

    async def test_el_dia_sin_atencion_y_el_hueco_del_mediodia_y_sin_apertura(self) -> None:
        """RED del caso 20: `{cuando}` en los bordes nuevos."""
        feriado = _escena(
            RESPONDE, Cierre(_local(10, 14), _local(13, 9)), ahora=_local(12, 10)
        )  # lunes 12/10 sin atención
        await feriado.procesar(PERSONA)
        # El martes es «mañana» del lunes; la fecha completa sólo hace falta si es más lejos.
        assert feriado.textos == [_aviso("de mañana a las 09:00")]

        sabado = _escena(RESPONDE, Cierre(_local(10, 14), _local(13, 9)), ahora=_local(10, 20))
        await sabado.procesar(PERSONA)
        assert sabado.textos == [_aviso("del martes 13/10 a las 09:00")]

        hueco = _escena(RESPONDE, Cierre(_local(5, 13), _local(5, 16)), ahora=_local(5, 13, 30))
        await hueco.procesar(PERSONA)
        assert hueco.textos == [_aviso("de hoy a las 16:00")]

        sin_regreso = _escena(RESPONDE, Cierre(_local(5, 19), None), ahora=_local(5, 22))
        await sin_regreso.procesar(PERSONA)
        assert sin_regreso.textos == [
            f"{MENSAJE_DERIVACION} Ahora estamos fuera del horario de atención: "
            "un asesor te va a responder cuando retomemos la atención."
        ]

    async def test_una_pregunta_de_noche_se_interpreta_y_se_contesta_como_de_dia(self) -> None:
        """Caso 21: en (a) el agente sigue atendiendo."""
        escena = _escena(RESPONDE, NOCHE, ahora=_local(5, 22), lectura=leyendo(Intencion.FAQ))

        await escena.procesar("¿cuánto sale?")

        assert len(escena.interprete.vistos) == 1
        assert len(escena.textos) == 1
        assert escena.escalamientos.escalamientos == {}


# --------------------------------------------------------------------- (b) mensaje fijo


class TestPoliticaMensajeFijo:
    async def test_el_primer_mensaje_de_la_noche_recibe_el_fijo_y_nada_mas(self) -> None:
        """RED del caso 22."""
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22), lectura=leyendo(Intencion.FAQ))

        respuesta = await escena.procesar("hola, ¿cuánto sale?")

        assert escena.textos == [
            "Hola, gracias por escribirnos. En este momento estamos fuera del horario de "
            "atención. Atendemos de nuevo mañana a las 09:00: escribinos a partir de ese "
            "momento y te respondemos."
        ]
        assert respuesta.escalado is False
        [entrante] = _entrantes(escena)
        assert entrante.contenido == "hola, ¿cuánto sale?"
        assert entrante.intencion is None
        # El modelo y los embeddings no se llamaron, y no se escaló.
        assert escena.interprete.vistos == []
        assert escena.embeddings.pedidos == []
        assert escena.escalamientos.escalamientos == {}
        [evento] = escena.publicador.de_la_accion("responder_fuera_de_horario")
        assert evento.entidad_afectada == f"Conversacion:{escena.hilo.id}"
        assert evento.iniciador is not None
        assert evento.iniciador.value == "ia"

    async def test_el_saliente_queda_en_el_hilo_como_del_agente(self) -> None:
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22))

        await escena.procesar("hola")

        [saliente] = escena.mensajes.salientes
        assert saliente.origen is OrigenDelMensaje.AGENTE
        assert saliente.momento == _local(5, 22)

    async def test_los_mensajes_siguientes_del_mismo_cierre_se_guardan_y_no_se_contestan(
        self,
    ) -> None:
        """RED del caso 23 (Pregunta 3): un solo aviso por período de cierre."""
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22), lectura=leyendo(Intencion.FAQ))

        await escena.procesar("hola")
        escena.ahora = _local(5, 22, 5)
        await escena.procesar("¿hay alguien?")
        escena.ahora = _local(5, 23)
        await escena.procesar("¿cuánto sale?")

        assert len(escena.textos) == 1
        assert len(_entrantes(escena)) == 3
        assert escena.interprete.vistos == []
        assert len(escena.publicador.de_la_accion("responder_fuera_de_horario")) == 1

    async def test_otro_periodo_de_cierre_vuelve_a_avisar(self) -> None:
        """Caso 24: la noche siguiente, y el hueco de un horario cortado."""
        martes = Cierre(_local(6, 19), _local(7, 9))
        escena = _escena(FIJO, NOCHE, martes, ahora=_local(5, 22))
        await escena.procesar("hola")
        escena.ahora = _local(6, 22)
        await escena.procesar("hola de nuevo")
        assert len(escena.textos) == 2

        mediodia = Cierre(_local(5, 13), _local(5, 16))
        noche = Cierre(_local(5, 20), _local(6, 9))
        cortado = _escena(FIJO, mediodia, noche, ahora=_local(5, 13, 30))
        await cortado.procesar("hola")
        cortado.ahora = _local(5, 20, 30)
        await cortado.procesar("hola otra vez")
        assert len(cortado.textos) == 2
        assert "hoy a las 16:00" in cortado.textos[0]
        assert "mañana a las 09:00" in cortado.textos[1]

    async def test_un_aviso_del_sistema_o_del_operador_no_cuenta_como_ya_avisado(self) -> None:
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22), conocido=True)
        hilo = Conversacion(
            id=uuid4(), empresa_id=EMPRESA, cliente_id=escena.cliente_id, created_at=_local(5, 9)
        )
        escena.conversaciones.hilos[hilo.id] = hilo
        for origen in (OrigenDelMensaje.SISTEMA, OrigenDelMensaje.OPERADOR):
            await escena.mensajes.agregar(
                Mensaje(
                    id=uuid4(),
                    conversacion_id=hilo.id,
                    empresa_id=EMPRESA,
                    direccion=DireccionMensaje.SALIENTE,
                    tipo_contenido=TipoContenido.TEXTO,
                    contenido="un aviso",
                    momento=_local(5, 20),
                    origen=origen,
                )
            )

        await escena.procesar("hola")

        assert len(escena.textos) == 1

    async def test_pedir_una_persona_de_noche_recibe_el_fijo_y_no_escala(self) -> None:
        """Caso 25 (Pregunta 4 i)."""
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22))

        respuesta = await escena.procesar(PERSONA)

        assert respuesta.escalado is False
        assert "fuera del horario de atención" in escena.ultimo_texto
        assert escena.escalamientos.escalamientos == {}
        assert escena.interprete.vistos == []

    async def test_con_un_escalamiento_abierto_el_agente_calla_del_todo(self) -> None:
        """Caso 26: manda el operador (HU-E9-01 RN-02), ni el mensaje fijo sale."""
        hilo = Conversacion(
            id=uuid4(), empresa_id=EMPRESA, cliente_id=uuid4(), created_at=_local(5, 9)
        )
        abierto = Escalamiento(
            id=uuid4(),
            conversacion_id=hilo.id,
            empresa_id=EMPRESA,
            motivo=MOTIVO_BAJA_CONFIANZA,
            created_at=_local(5, 9),
            updated_at=_local(5, 9),
        )
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22), hilos=(hilo,), escalamientos=(abierto,))
        escena.clientes.conocidos[TELEFONO] = (hilo.cliente_id, "Ana")

        await escena.procesar("hola")

        assert escena.textos == []
        assert len(_entrantes(escena)) == 1

    async def test_un_audio_de_noche_se_transcribe_se_guarda_y_no_se_interpreta(self) -> None:
        """Caso 31: el audio no se guarda (HS-T7 RN-03), así que se transcribe igual."""
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22))

        await escena.procesar("", audio="audio-1")

        [entrante] = _entrantes(escena)
        assert entrante.contenido == "quiero un turno"
        assert entrante.tipo_contenido is TipoContenido.AUDIO
        assert escena.interprete.vistos == []
        assert len(escena.textos) == 1

    async def test_una_transcripcion_pobre_de_noche_recibe_el_fijo_y_no_escala(self) -> None:
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22), calidad_del_audio=0.2)

        respuesta = await escena.procesar("", audio="audio-1")

        assert respuesta.escalado is False
        assert escena.escalamientos.escalamientos == {}
        assert "fuera del horario de atención" in escena.ultimo_texto

    async def test_dentro_de_horario_es_el_flujo_de_siempre(self) -> None:
        """Caso 32, también en la franja de la tarde de un horario cortado."""
        mediodia = Cierre(_local(5, 13), _local(5, 16))
        for ahora in (_local(5, 10), _local(5, 17)):
            escena = _escena(FIJO, mediodia, ahora=ahora, lectura=leyendo(Intencion.FAQ))

            await escena.procesar("¿cuánto sale?")

            assert len(escena.interprete.vistos) == 1
            assert "fuera del horario" not in escena.ultimo_texto
            assert escena.publicador.de_la_accion("responder_fuera_de_horario") == []

    async def test_el_mismo_mensaje_entregado_dos_veces_deja_un_solo_fijo(self) -> None:
        """Caso 35: Meta reintenta por diseño."""
        escena = _escena(FIJO, NOCHE, ahora=_local(5, 22))
        await escena.procesar("hola", externo_id="wamid-repetido")

        with pytest.raises(MensajeYaProcesado):
            await escena.procesar("hola", externo_id="wamid-repetido")

        assert len(escena.textos) == 1


# --------------------------------------------------------------------- sin horario


class TestSinHorarioConfigurado:
    async def test_derivar_dice_lo_de_siempre_a_cualquier_hora(self) -> None:
        """Caso 33: «siempre abierto» no cambia nada."""
        escena = Escena()
        escena.ahora = _local(5, 3)

        await escena.procesar(PERSONA)

        assert escena.textos == [MENSAJE_DERIVACION]

    async def test_se_consulta_el_horario_una_vez_por_mensaje(self) -> None:
        escena = _escena(RESPONDE, NOCHE, ahora=_local(5, 22))

        await escena.procesar(PERSONA)

        assert escena.horario.consultas == [_local(5, 22)]
